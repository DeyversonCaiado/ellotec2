"""
Regra de negócio da expedição: separação e conferência de um pedido.

Os dois processos têm exatamente o mesmo ciclo de vida (abre → item a item →
fecha), só mudam a tabela e o nome da coluna de quantidade. Por isso existe
`_TIPOS` logo abaixo, em vez de dois blocos gêmeos de ~200 linhas cada: a
regra mora num lugar só, e uma correção não precisa ser feita duas vezes.

Fronteiras com outros domínios: este arquivo só conversa com `pedidos`,
`clientes`, `produtos` e `usuarios` pelos respectivos `*_publico.py`
(ver ARCHITECTURE.md → "Regras de import entre domínios").
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.clientes import cliente_publico
from app.domains.empresas import empresa_publico
from app.domains.expedicao.expedicao_contrato import (
    AtribuicaoSchema,
    AtribuirSchema,
    BiparSchema,
    EmpresaFiltroSchema,
    CredencialGerenteSchema,
    FinalizarItemSchema,
    ItemPedidoExpedicaoSchema,
    ItemProcessoRespostaSchema,
    OperadorSchema,
    PedidoExpedicaoDetalheSchema,
    PedidoExpedicaoListaPaginadaSchema,
    PedidoExpedicaoListaSchema,
    ProcessoRespostaSchema,
    SituacaoProcessoSchema,
    TipoProcesso,
)
from app.domains.expedicao.expedicao_model import (
    Conferencia,
    ConferenciaItem,
    ExpedicaoAtribuicao,
    ExpedicaoPedidoStatus,
    Separacao,
    SeparacaoItem,
)
from app.domains.pedidos import pedido_publico
from app.domains.produtos import produto_publico
from app.domains.usuarios import usuario_publico
from app.shared.sync_helpers import incrementar_versao, marcar_apagado

# Só quem tem esse cargo pode autorizar reset ou fechamento com falta.
CARGO_AUTORIZADOR = "Gerente"


@dataclass(frozen=True)
class _TipoConfig:
    capa: type
    item: type
    campo_quantidade: str
    rotulo: str


# `campo_quantidade` existe porque as duas tabelas de item nomeiam a coluna de
# forma diferente (`quantidade_separada` / `quantidade_conferida`). É o único
# ponto onde este arquivo usa getattr/setattr, e é de propósito: renomear as
# colunas pra um nome comum só pra simplificar este código mudaria o schema
# do banco por conveniência de implementação.
_TIPOS: dict[str, _TipoConfig] = {
    "separacao": _TipoConfig(
        capa=Separacao,
        item=SeparacaoItem,
        campo_quantidade="quantidade_separada",
        rotulo="separação",
    ),
    "conferencia": _TipoConfig(
        capa=Conferencia,
        item=ConferenciaItem,
        campo_quantidade="quantidade_conferida",
        rotulo="conferência",
    ),
}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Status do pedido dentro do galpão
#
# Mora em `expedicao_pedido_status`, não em `pedidos.status_id`: aquele campo é
# da integração e seria sobrescrito no próximo PUT do ERP. O catálogo de status
# é o mesmo dos pedidos — só o dono da escrita muda.
# --------------------------------------------------------------------------

# Qual chave gravar em cada marco. Uma tabela em vez de quatro chamadas
# espalhadas: a ordem das etapas fica legível num lugar só.
_STATUS_AO_INICIAR: dict[str, str] = {
    "separacao": pedido_publico.STATUS_EM_SEPARACAO,
    "conferencia": pedido_publico.STATUS_EM_CONFERENCIA,
}
_STATUS_AO_FINALIZAR: dict[str, str] = {
    "separacao": pedido_publico.STATUS_SEPARADO,
    "conferencia": pedido_publico.STATUS_CONFERIDO,
}


def _linha_status(
    sessao_db: Session, pedido_id: str, incluir_apagada: bool = False
) -> ExpedicaoPedidoStatus | None:
    """`incluir_apagada` existe para a escrita: o unique de `pedido_id` vale
    também para linha soft-deletada, então quem grava precisa reviver a que já
    está lá em vez de inserir uma segunda."""
    consulta = sessao_db.query(ExpedicaoPedidoStatus).filter(
        ExpedicaoPedidoStatus.pedido_id == pedido_id
    )
    if not incluir_apagada:
        consulta = consulta.filter(ExpedicaoPedidoStatus.sync_deleted_at.is_(None))
    return consulta.first()


def _gravar_status(sessao_db: Session, pedido_id: str, chave: str) -> None:
    """Uma linha por pedido: a primeira etapa cria, as seguintes atualizam.

    Não faz commit — quem chama já está no meio de uma transação (abrir
    processo, finalizar item) e o status precisa subir junto com ela, ou não
    subir de jeito nenhum.
    """
    status_id = pedido_publico.obter_status_id(sessao_db, chave)
    if status_id is None:
        # Catálogo sem a chave = migration não aplicada. Não é motivo para
        # derrubar uma separação em andamento: o andamento real está nas
        # tabelas de processo, este status é leitura derivada.
        return

    linha = _linha_status(sessao_db, pedido_id, incluir_apagada=True)
    if linha is None:
        sessao_db.add(ExpedicaoPedidoStatus(pedido_id=pedido_id, status_id=status_id))
        return
    if linha.status_id != status_id or linha.sync_deleted_at is not None:
        linha.status_id = status_id
        linha.sync_deleted_at = None
        incrementar_versao(linha)


def _limpar_status(sessao_db: Session, pedido_id: str) -> None:
    """Reset da separação devolve o pedido ao estado de quem nunca entrou no
    galpão — sem linha de status, como antes da primeira etapa."""
    linha = _linha_status(sessao_db, pedido_id)
    if linha is not None:
        marcar_apagado(linha)


def _mapa_status(sessao_db: Session, pedido_ids: list[str]) -> dict[str, str]:
    """pedido_id -> chave do status, numa consulta só para a listagem inteira."""
    if not pedido_ids:
        return {}
    # Duas etapas em vez de um join: `pedido_status` é tabela de outro domínio,
    # e este arquivo só a alcança pelo pedido_publico (ver ARCHITECTURE.md →
    # "Regras de import entre domínios").
    linhas = (
        sessao_db.query(ExpedicaoPedidoStatus.pedido_id, ExpedicaoPedidoStatus.status_id)
        .filter(
            ExpedicaoPedidoStatus.pedido_id.in_(pedido_ids),
            ExpedicaoPedidoStatus.sync_deleted_at.is_(None),
        )
        .all()
    )
    chaves = pedido_publico.obter_chaves_status(sessao_db, [status_id for _, status_id in linhas])
    return {
        pedido_id: chaves[status_id] for pedido_id, status_id in linhas if status_id in chaves
    }


def _config(tipo: TipoProcesso) -> _TipoConfig:
    configuracao = _TIPOS.get(tipo)
    if configuracao is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tipo de processo inválido — use 'separacao' ou 'conferencia'.",
        )
    return configuracao


def _quantidade(item, configuracao: _TipoConfig) -> int:
    return getattr(item, configuracao.campo_quantidade) or 0


def _situacao_item(item) -> str:
    if item.data_fim is not None:
        return "finalizado"
    if item.data_inicio is not None:
        return "em_andamento"
    return "pendente"


# --------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------


def _processo_vivo(sessao_db: Session, tipo: TipoProcesso, pedido_id: str):
    configuracao = _config(tipo)
    return (
        sessao_db.query(configuracao.capa)
        .filter(
            configuracao.capa.pedido_id == pedido_id,
            configuracao.capa.sync_deleted_at.is_(None),
        )
        .order_by(configuracao.capa.sync_created_at.desc())
        .first()
    )


def _situacao(sessao_db: Session, tipo: TipoProcesso, pedido_id: str, total_itens: int) -> SituacaoProcessoSchema:
    configuracao = _config(tipo)
    processo = _processo_vivo(sessao_db, tipo, pedido_id)
    if processo is None:
        return SituacaoProcessoSchema(
            id=None,
            status="nao_iniciada",
            usuario_id=None,
            usuario_nome=None,
            itens_finalizados=0,
            itens_total=total_itens,
            tem_divergencia=False,
        )

    itens_vivos = [item for item in processo.itens if item.sync_deleted_at is None]
    return SituacaoProcessoSchema(
        id=processo.id,
        status=processo.status,
        usuario_id=processo.usuario_inicio_id,
        usuario_nome=usuario_publico.obter_nome(sessao_db, processo.usuario_inicio_id),
        itens_finalizados=sum(1 for item in itens_vivos if item.data_fim is not None),
        itens_total=total_itens,
        tem_divergencia=any(item.divergente for item in itens_vivos),
        data_primeiro_bipe=processo.data_primeiro_bipe,
        data_fim=processo.data_fim,
    )


def _situacoes_da_pagina(
    sessao_db: Session, tipo: TipoProcesso, pedidos: list[pedido_publico.PedidoResumo]
) -> dict[str, SituacaoProcessoSchema]:
    """pedido_id -> situação, para a página inteira em duas consultas.

    A versão de uma linha só (`_situacao`) faz uma consulta por pedido, mais uma
    por nome de operador. Numa listagem paginada isso vira dezenas de idas ao
    banco por página — aqui os processos e os nomes vêm de uma vez.
    """
    configuracao = _config(tipo)
    ids = [pedido.id for pedido in pedidos]
    if not ids:
        return {}

    processos = (
        sessao_db.query(configuracao.capa)
        .filter(
            configuracao.capa.pedido_id.in_(ids),
            configuracao.capa.sync_deleted_at.is_(None),
        )
        .order_by(configuracao.capa.sync_created_at.desc())
        .all()
    )
    # Ordenado do mais novo para o mais velho: o primeiro de cada pedido é o
    # que vale, mesma regra do `_processo_vivo`.
    por_pedido: dict[str, object] = {}
    for processo in processos:
        por_pedido.setdefault(processo.pedido_id, processo)

    nomes = usuario_publico.obter_nomes(
        sessao_db, [processo.usuario_inicio_id for processo in por_pedido.values()]
    )

    situacoes: dict[str, SituacaoProcessoSchema] = {}
    for pedido in pedidos:
        processo = por_pedido.get(pedido.id)
        if processo is None:
            situacoes[pedido.id] = SituacaoProcessoSchema(
                id=None,
                status="nao_iniciada",
                usuario_id=None,
                usuario_nome=None,
                itens_finalizados=0,
                itens_total=len(pedido.itens),
                tem_divergencia=False,
            )
            continue

        itens_vivos = [item for item in processo.itens if item.sync_deleted_at is None]
        situacoes[pedido.id] = SituacaoProcessoSchema(
            id=processo.id,
            status=processo.status,
            usuario_id=processo.usuario_inicio_id,
            usuario_nome=nomes.get(processo.usuario_inicio_id),
            itens_finalizados=sum(1 for item in itens_vivos if item.data_fim is not None),
            itens_total=len(pedido.itens),
            tem_divergencia=any(item.divergente for item in itens_vivos),
            data_primeiro_bipe=processo.data_primeiro_bipe,
            data_fim=processo.data_fim,
        )
    return situacoes


# ---------------------------------------------------------------------------
# Atribuição: quem responde por cada etapa, e quem enxerga o quê
# ---------------------------------------------------------------------------

# Quem tem esta permissão distribui o trabalho e enxerga a fila inteira. Quem
# não tem enxerga só o que foi atribuído a ele — inclusive nada, se não houver
# atribuição nenhuma. É decisão de negócio deliberada: aqui o trabalho é
# empurrado pelo coordenador, não puxado de uma fila aberta.
PERMISSAO_ATRIBUIR = "expedicao.atribuir"

# A permissão de executar cada etapa, usada para montar o seletor de
# responsável: não se atribui separação a quem não pode separar.
_PERMISSAO_EXECUTAR = {
    "separacao": "expedicao.separacao.executar",
    "conferencia": "expedicao.conferencia.executar",
}


def pode_atribuir(ctx_permissoes) -> bool:
    """Recebe as permissões do usuário do contexto e diz se ele distribui
    trabalho. Fica aqui, e não no router, porque a mesma resposta decide duas
    coisas: se o POST é aceito e o que o GET devolve."""
    return any(permissao.chave == PERMISSAO_ATRIBUIR for permissao in ctx_permissoes)


def _atribuicoes_vivas(sessao_db: Session, pedido_ids: list[str]) -> dict[tuple[str, str], ExpedicaoAtribuicao]:
    """(pedido_id, tipo) -> atribuição viva, numa consulta só para a página."""
    if not pedido_ids:
        return {}
    linhas = (
        sessao_db.query(ExpedicaoAtribuicao)
        .filter(
            ExpedicaoAtribuicao.pedido_id.in_(pedido_ids),
            ExpedicaoAtribuicao.sync_deleted_at.is_(None),
        )
        .all()
    )
    return {(linha.pedido_id, linha.tipo): linha for linha in linhas}


def _para_schema_atribuicao(
    atribuicao: ExpedicaoAtribuicao | None, nomes: dict[str, str]
) -> AtribuicaoSchema | None:
    if atribuicao is None:
        return None
    return AtribuicaoSchema(
        usuario_id=atribuicao.usuario_id,
        usuario_nome=nomes.get(atribuicao.usuario_id, ""),
        atribuido_por_nome=nomes.get(atribuicao.atribuido_por_id),
        data_atribuicao=atribuicao.data_atribuicao,
    )


def _pedidos_atribuidos_a(sessao_db: Session, usuario_id: str) -> list[str]:
    """Ids de pedido em que o usuário é responsável por alguma etapa. Alimenta
    o filtro de visibilidade da listagem."""
    linhas = (
        sessao_db.query(ExpedicaoAtribuicao.pedido_id)
        .filter(
            ExpedicaoAtribuicao.usuario_id == usuario_id,
            ExpedicaoAtribuicao.sync_deleted_at.is_(None),
        )
        .distinct()
        .all()
    )
    return [pedido_id for (pedido_id,) in linhas]


# ---------------------------------------------------------------------------
# Recortes por dado da expedição, resolvidos como conjuntos de pedido_id
#
# Situação e operador vivem nas tabelas DESTE domínio, mas o filtro precisa
# valer sobre a base inteira, não sobre a página carregada. A saída é a
# expedição resolver o recorte aqui e entregar os ids a `pedido_publico`, que
# aplica na mesma consulta paginada do resto — nenhum dos dois domínios precisa
# conhecer as tabelas do outro (ver ARCHITECTURE.md → "Regras de import").
#
# Filtrar na página carregada, que era o que a tela fazia, devolvia 3 linhas de
# 50 e um total que não batia com o que estava na tela. Pior: o pedido que
# atendia o filtro e estava na página 7 simplesmente não existia para quem
# procurava.
# ---------------------------------------------------------------------------

# As situações que a tela oferece, traduzidas para conjuntos de pedido_id.
# `incluir` são conjuntos dos quais o pedido precisa fazer parte (todos eles);
# `excluir` é o conjunto do qual ele precisa ficar de fora.
SITUACOES_VALIDAS = (
    "todos",
    "nao_iniciados",
    "em_separacao",
    "aguardando_conferencia",
    "em_conferencia",
    "concluidos",
    "divergentes",
)


@dataclass(frozen=True)
class _Recorte:
    incluir: list[list[str]]
    excluir: list[str]


def _pedidos_com_processo(
    sessao_db: Session, tipo: TipoProcesso, status: str | None = None
) -> list[str]:
    """Ids de pedido com processo vivo do tipo — opcionalmente só num status."""
    capa = _config(tipo).capa
    consulta = sessao_db.query(capa.pedido_id).filter(capa.sync_deleted_at.is_(None))
    if status is not None:
        consulta = consulta.filter(capa.status == status)
    return [pedido_id for (pedido_id,) in consulta.distinct().all()]


def _pedidos_com_divergencia(sessao_db: Session) -> list[str]:
    """Ids de pedido em que alguma etapa fechou algum item com falta.

    Une as duas etapas: divergência é do pedido, não da separação ou da
    conferência isolada — quem filtra por isso quer o pedido que deu problema."""
    ids: set[str] = set()
    for tipo in _TIPOS:
        configuracao = _config(tipo)
        linhas = (
            sessao_db.query(configuracao.capa.pedido_id)
            # Pelo relationship, e não por uma coluna nomeada: as duas tabelas
            # de item chamam a FK de forma diferente (`separacao_id` /
            # `conferencia_id`), como as colunas de quantidade.
            .join(configuracao.capa.itens)
            .filter(
                configuracao.capa.sync_deleted_at.is_(None),
                configuracao.item.sync_deleted_at.is_(None),
                configuracao.item.divergente.is_(True),
            )
            .distinct()
            .all()
        )
        ids.update(pedido_id for (pedido_id,) in linhas)
    return list(ids)


def _pedidos_do_operador(sessao_db: Session, usuario_id: str) -> list[str]:
    """Ids de pedido em que o usuário abriu alguma etapa.

    É quem EXECUTA, não quem foi designado: a coluna da tela mostra o operador
    do processo, e o filtro tem que concordar com o que está escrito na linha.
    Para "o que designaram para mim" existe a visibilidade por atribuição, que é
    outra regra (ver `_pedidos_atribuidos_a`)."""
    ids: set[str] = set()
    for tipo in _TIPOS:
        capa = _config(tipo).capa
        linhas = (
            sessao_db.query(capa.pedido_id)
            .filter(capa.usuario_inicio_id == usuario_id, capa.sync_deleted_at.is_(None))
            .distinct()
            .all()
        )
        ids.update(pedido_id for (pedido_id,) in linhas)
    return list(ids)


def _recorte_da_situacao(sessao_db: Session, situacao: str) -> _Recorte:
    """A situação escolhida, virada em conjuntos de pedido_id.

    "Não iniciados" e "aguardando conferência" são perguntas pela AUSÊNCIA de um
    processo — por isso `excluir` existe. Não dá para listar "pedidos sem
    separação" sem varrer a base; dá para listar os que têm, e tirá-los.
    """
    if situacao == "nao_iniciados":
        return _Recorte(incluir=[], excluir=_pedidos_com_processo(sessao_db, "separacao"))
    if situacao == "em_separacao":
        return _Recorte(
            incluir=[_pedidos_com_processo(sessao_db, "separacao", "em_andamento")], excluir=[]
        )
    if situacao == "aguardando_conferencia":
        return _Recorte(
            incluir=[_pedidos_com_processo(sessao_db, "separacao", "finalizada")],
            excluir=_pedidos_com_processo(sessao_db, "conferencia"),
        )
    if situacao == "em_conferencia":
        return _Recorte(
            incluir=[_pedidos_com_processo(sessao_db, "conferencia", "em_andamento")], excluir=[]
        )
    if situacao == "concluidos":
        return _Recorte(
            incluir=[
                _pedidos_com_processo(sessao_db, "separacao", "finalizada"),
                _pedidos_com_processo(sessao_db, "conferencia", "finalizada"),
            ],
            excluir=[],
        )
    if situacao == "divergentes":
        return _Recorte(incluir=[_pedidos_com_divergencia(sessao_db)], excluir=[])
    return _Recorte(incluir=[], excluir=[])


# Empresa sem cadastro vivo na página: acontece com pedido cuja empresa foi
# apagada depois. A listagem não pode parar por causa disso — a linha aparece
# sem o nome, que é a informação honesta.
_EMPRESA_PADRAO = empresa_publico.EmpresaResumo(id="", nome="", apelido=None)


def _empresa(
    empresas: dict[str, empresa_publico.EmpresaResumo], empresa_id: str
) -> empresa_publico.EmpresaResumo:
    return empresas.get(empresa_id, _EMPRESA_PADRAO)


def listar_status_pedido(sessao_db: Session) -> list[str]:
    """Chaves de status do ERP, para o filtro da listagem.

    Existe em vez de a tela chamar `GET /pedidos/status` direto: aquele
    endpoint exige `pedidos.acessar`, que o operador de galpão não tem — e o
    403 resultante derrubava a tela inteira, porque o interceptor do front
    trata 403 como "suas permissões mudaram" e volta para o início."""
    return pedido_publico.listar_chaves_status(sessao_db)


def listar_operadores(sessao_db: Session, tipo: TipoProcesso) -> list[OperadorSchema]:
    """Quem pode ser responsável por essa etapa. Pergunta ao domínio dono das
    permissões em vez de consultar `usuario_permissoes` daqui."""
    return [
        OperadorSchema(id=usuario.id, nome=usuario.nome)
        for usuario in usuario_publico.listar_por_permissao(sessao_db, _PERMISSAO_EXECUTAR[tipo])
    ]


def listar_operadores_do_filtro(sessao_db: Session) -> list[OperadorSchema]:
    """Quem pode executar QUALQUER etapa da expedição — a lista do filtro por
    operador da listagem.

    Diferente de `listar_operadores`, que recebe uma etapa: aqui não há etapa a
    considerar, porque o filtro pergunta "onde esta pessoa está envolvida?" e a
    resposta pode ser separação, conferência ou as duas.

    Também diferente da lista que a tela montava antes, tirada dos pedidos da
    página: quem ainda não pegou nenhum pedido não aparecia, e era justamente
    quem o coordenador queria procurar.
    """
    por_id: dict[str, OperadorSchema] = {}
    for chave in _PERMISSAO_EXECUTAR.values():
        for usuario in usuario_publico.listar_por_permissao(sessao_db, chave):
            por_id[usuario.id] = OperadorSchema(id=usuario.id, nome=usuario.nome)
    return sorted(por_id.values(), key=lambda operador: operador.nome)


def listar_empresas(sessao_db: Session) -> list[EmpresaFiltroSchema]:
    """As empresas do filtro da listagem — o cadastro inteiro, não as que por
    acaso apareceram na página carregada.

    Pergunta ao domínio dono (`empresa_publico`) em vez de a tela chamar
    GET /empresas: aquele endpoint exige `empresas.acessar`, chave que o
    operador de galpão não tem. Mesmo motivo do catálogo de status ter um
    espelho aqui (ver `listar_status_pedido`).
    """
    return [
        EmpresaFiltroSchema(id=empresa.id, nome=empresa.nome)
        for empresa in empresa_publico.listar_resumo(sessao_db)
    ]


def atribuir(
    sessao_db: Session, dados: AtribuirSchema, atribuido_por_id: str
) -> None:
    """Define (ou remove) o responsável por uma etapa em vários pedidos.

    `usuario_id` nulo remove — é o valor "sem responsável", não uma operação
    separada. Em ambos os casos a atribuição anterior é soft-deletada primeiro:
    é isso que mantém no máximo uma atribuição viva por `(pedido_id, tipo)`,
    já que a tabela não tem unique (ver expedicao_model.py).
    """
    for pedido_id in dados.pedido_ids:
        # Confirma que o pedido existe antes de gravar — 404 aqui é mais claro
        # que um IntegrityError virando 422 lá na frente.
        _obter_pedido(sessao_db, pedido_id)

        # Conferência só depois da separação fechar — a mesma regra que
        # `iniciar_processo` aplica. Sem isto aqui, o coordenador conseguiria
        # designar uma conferência que o operador veria na tela dele e não
        # conseguiria abrir: o pedido apareceria na fila da pessoa só para dar
        # 409 no clique. Atribuir trabalho impossível é pior que recusar agora.
        #
        # Só vale para ATRIBUIR. Remover (`usuario_id` nulo) passa direto: se
        # uma atribuição indevida existir, tem que dar para desfazer.
        if dados.tipo == "conferencia" and dados.usuario_id is not None:
            separacao = _processo_vivo(sessao_db, "separacao", pedido_id)
            if separacao is None or separacao.status != "finalizada":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "A separação deste pedido precisa ser finalizada antes de "
                        "atribuir a conferência."
                    ),
                )

        # Tirar o responsável de uma etapa que já começou deixaria um processo
        # vivo sem dono, e o operador continuaria travado nele. O caminho certo
        # nesse caso é resetar o processo (que exige senha de gerente) e só
        # depois redistribuir.
        processo = _processo_vivo(sessao_db, dados.tipo, pedido_id)
        if processo is not None and processo.status == "em_andamento":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"A {_config(dados.tipo).rotulo} do pedido já está em andamento. "
                    "Resete o processo antes de mudar o responsável."
                ),
            )

        anterior = (
            sessao_db.query(ExpedicaoAtribuicao)
            .filter(
                ExpedicaoAtribuicao.pedido_id == pedido_id,
                ExpedicaoAtribuicao.tipo == dados.tipo,
                ExpedicaoAtribuicao.sync_deleted_at.is_(None),
            )
            .first()
        )
        if anterior is not None:
            marcar_apagado(anterior)

        if dados.usuario_id is not None:
            sessao_db.add(
                ExpedicaoAtribuicao(
                    pedido_id=pedido_id,
                    tipo=dados.tipo,
                    usuario_id=dados.usuario_id,
                    atribuido_por_id=atribuido_por_id,
                    data_atribuicao=_agora(),
                )
            )

    sessao_db.commit()


def listar_pedidos(
    sessao_db: Session,
    data_inicio: date,
    data_fim: date,
    termo: str | None,
    page: int,
    per_page: int,
    status_chaves: list[str] | None = None,
    usuario_id: str | None = None,
    ver_tudo: bool = True,
    empresa_id: str | None = None,
    operador_id: str | None = None,
    situacao: str | None = None,
    sort: str = "sync_updated_at",
    sort_type: str = "desc",
) -> PedidoExpedicaoListaPaginadaSchema:
    """Uma página de pedidos, de qualquer status, ordenada por data de
    alteração. Quem monta a consulta é o domínio `pedidos` (ver
    pedido_publico.listar_para_expedicao); aqui entra o que é da expedição:
    situação de cada etapa, status do galpão e dados de apoio das telas.

    Todo dado auxiliar é resolvido em lote para a página — nenhuma consulta
    dentro do laço.

    `ver_tudo` é falso para quem não tem `expedicao.atribuir`: essa pessoa só
    enxerga pedido em que ela é a responsável por alguma etapa, e enxerga uma
    lista vazia enquanto nada tiver sido atribuído a ela. É regra de acesso, e
    por isso é aplicada aqui na consulta — o front esconder linha seria só UX.

    `empresa_id`, `operador_id` e `situacao` são os filtros da tela, e TODOS os
    três são resolvidos na consulta paginada, nunca na página já carregada. Com
    ~230 mil pedidos, filtrar depois de paginar responde "não achei" para um
    pedido que existe na página 7 — e mostra um total que não corresponde às
    linhas na tela.
    """
    # Cada entrada é um conjunto do qual o pedido PRECISA fazer parte; a
    # interseção de todos é o que sobra. Visibilidade e filtros entram na mesma
    # lista de propósito: são a mesma operação, e combiná-los num só lugar evita
    # a ordem de aplicação virar regra escondida.
    conjuntos_obrigatorios: list[list[str]] = []
    ids_excluidos: list[str] = []

    if not ver_tudo:
        conjuntos_obrigatorios.append(
            _pedidos_atribuidos_a(sessao_db, usuario_id) if usuario_id else []
        )

    if operador_id:
        conjuntos_obrigatorios.append(_pedidos_do_operador(sessao_db, operador_id))

    if situacao and situacao != "todos":
        if situacao not in SITUACOES_VALIDAS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Situação inválida. Use uma destas: {', '.join(SITUACOES_VALIDAS)}.",
            )
        recorte = _recorte_da_situacao(sessao_db, situacao)
        conjuntos_obrigatorios.extend(recorte.incluir)
        ids_excluidos.extend(recorte.excluir)

    pedido_ids_visiveis: list[str] | None = None
    if conjuntos_obrigatorios:
        interseccao = set(conjuntos_obrigatorios[0])
        for conjunto in conjuntos_obrigatorios[1:]:
            interseccao &= set(conjunto)
        pedido_ids_visiveis = list(interseccao)
        if not pedido_ids_visiveis:
            # Nenhum pedido atende: a lista é vazia, e nem vale ir ao banco de
            # pedidos. Vale tanto para "nada atribuído a mim" quanto para um
            # filtro que não casou com nada.
            return PedidoExpedicaoListaPaginadaSchema(
                items=[], total=0, page=page, per_page=per_page, sort=sort, sort_type=sort_type
            )

    try:
        pedidos, total = pedido_publico.listar_para_expedicao(
            sessao_db,
            data_inicio,
            data_fim,
            termo,
            page,
            per_page,
            status_chaves,
            pedido_ids_visiveis,
            ids_excluidos or None,
            empresa_id,
            sort,
            sort_type,
        )
    except ValueError as erro:
        # A fronteira não conhece HTTP (é regra do arquivo `_publico`), então a
        # tradução do erro para status code acontece aqui.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(erro)
        ) from erro
    separacoes = _situacoes_da_pagina(sessao_db, "separacao", pedidos)
    conferencias = _situacoes_da_pagina(sessao_db, "conferencia", pedidos)
    cidades = cliente_publico.obter_cidades(sessao_db, [pedido.cliente_id for pedido in pedidos])
    empresas = empresa_publico.obter_resumos(sessao_db, [pedido.empresa_id for pedido in pedidos])
    status_expedicao = _mapa_status(sessao_db, [pedido.id for pedido in pedidos])
    atribuicoes = _atribuicoes_vivas(sessao_db, [pedido.id for pedido in pedidos])
    # Nomes de responsável e de quem atribuiu, numa consulta só para a página.
    nomes = usuario_publico.obter_nomes(
        sessao_db,
        [linha.usuario_id for linha in atribuicoes.values()]
        + [linha.atribuido_por_id for linha in atribuicoes.values()],
    )
    itens = [
        PedidoExpedicaoListaSchema(
            pedido_id=pedido.id,
            numero=pedido.numero,
            sistema_origem_id=pedido.sistema_origem_id,
            data_pedido=pedido.data_pedido,
            status_pedido=pedido.status_chave,
            pode_iniciar=pedido_publico.pode_iniciar_expedicao(pedido.status_chave),
            cliente_nome_fantasia=pedido.cliente_nome_fantasia,
            cliente_cnpj=pedido.cliente_cnpj,
            cliente_cidade_nome=cidades[pedido.cliente_id].nome if pedido.cliente_id in cidades else "",
            cliente_cidade_uf=cidades[pedido.cliente_id].uf if pedido.cliente_id in cidades else "",
            empresa_id=pedido.empresa_id,
            empresa_nome=_empresa(empresas, pedido.empresa_id).nome,
            empresa_apelido=_empresa(empresas, pedido.empresa_id).apelido,
            quantidade_itens=len(pedido.itens),
            quantidade_total=sum(item.quantidade for item in pedido.itens),
            alterado_em=pedido.alterado_em,
            liberado_em=pedido.liberado_em,
            expedicao_status=status_expedicao.get(pedido.id),
            separacao=separacoes[pedido.id],
            conferencia=conferencias[pedido.id],
            atribuicao_separacao=_para_schema_atribuicao(
                atribuicoes.get((pedido.id, "separacao")), nomes
            ),
            atribuicao_conferencia=_para_schema_atribuicao(
                atribuicoes.get((pedido.id, "conferencia")), nomes
            ),
        )
        for pedido in pedidos
    ]
    return PedidoExpedicaoListaPaginadaSchema(
        items=itens,
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


def _obter_pedido(sessao_db: Session, pedido_id: str) -> pedido_publico.PedidoResumo:
    pedido = pedido_publico.obter_resumo(sessao_db, pedido_id)
    if pedido is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    return pedido


def _mapa_itens_processados(sessao_db: Session, tipo: TipoProcesso, pedido_id: str) -> dict[str, tuple[str, int]]:
    """pedido_item_id -> (situação, quantidade já processada)."""
    configuracao = _config(tipo)
    processo = _processo_vivo(sessao_db, tipo, pedido_id)
    if processo is None:
        return {}
    return {
        item.pedido_item_id: (_situacao_item(item), _quantidade(item, configuracao))
        for item in processo.itens
        if item.sync_deleted_at is None
    }


def _produtos_do_pedido(
    sessao_db: Session, pedido: pedido_publico.PedidoResumo
) -> dict[str, produto_publico.ProdutoExpedicao]:
    """produto_id -> cadastro (unidade e múltiplo de venda), numa consulta só
    para o pedido inteiro. Sem isso seriam N consultas numa tela que lista
    todos os itens."""
    return produto_publico.obter_para_expedicao(
        sessao_db, [item.produto_id for item in pedido.itens]
    )


# Usado quando o produto do item não tem mais cadastro vivo — a expedição do
# pedido não pode parar por causa disso.
_PRODUTO_PADRAO = produto_publico.ProdutoExpedicao(
    unidade="",
    quantidade_multipla_venda=1,
    marca_nome="",
    codigo_barra_notas=None,
    codigos_barras_logistica=(),
    dun_14=None,
)


# As duas telas montam o item a partir das mesmas três fontes — o snapshot do
# pedido, o cadastro vivo do produto e o andamento do processo. Cada uma virou
# uma função pra que a origem de cada campo continue óbvia depois de somar
# marca e códigos de barras ao que já vinha do cadastro.
def _item_do_pedido(
    item,
    produto: produto_publico.ProdutoExpedicao,
    separacao: tuple[str, int],
    conferencia: tuple[str, int],
) -> ItemPedidoExpedicaoSchema:
    return ItemPedidoExpedicaoSchema(
        pedido_item_id=item.id,
        produto_id=item.produto_id,
        produto_codigo=item.produto_codigo,
        produto_descricao=item.produto_descricao,
        produto_marca_nome=produto.marca_nome,
        produto_codigo_barra_notas=produto.codigo_barra_notas,
        produto_codigos_barras_logistica=list(produto.codigos_barras_logistica),
        produto_dun_14=produto.dun_14,
        endereco_produto=item.endereco_produto,
        lote=item.lote,
        quantidade=item.quantidade,
        quantidade_multipla_venda=produto.quantidade_multipla_venda,
        separacao_situacao=separacao[0],
        separacao_quantidade=separacao[1],
        conferencia_situacao=conferencia[0],
        conferencia_quantidade=conferencia[1],
    )


def _item_do_processo(
    item,
    item_pedido,
    produto: produto_publico.ProdutoExpedicao,
    configuracao,
) -> ItemProcessoRespostaSchema:
    return ItemProcessoRespostaSchema(
        pedido_item_id=item.pedido_item_id,
        produto_id=item_pedido.produto_id,
        produto_codigo=item_pedido.produto_codigo,
        produto_descricao=item_pedido.produto_descricao,
        produto_unidade=produto.unidade,
        produto_marca_nome=produto.marca_nome,
        produto_codigo_barra_notas=produto.codigo_barra_notas,
        produto_codigos_barras_logistica=list(produto.codigos_barras_logistica),
        produto_dun_14=produto.dun_14,
        endereco_produto=item_pedido.endereco_produto,
        lote=item_pedido.lote,
        quantidade_pedida=item_pedido.quantidade,
        quantidade_processada=_quantidade(item, configuracao),
        quantidade_multipla_venda=produto.quantidade_multipla_venda,
        data_inicio=item.data_inicio,
        data_fim=item.data_fim,
        divergente=item.divergente,
        situacao=_situacao_item(item),
    )


def obter_pedido(sessao_db: Session, pedido_id: str) -> PedidoExpedicaoDetalheSchema:
    pedido = _obter_pedido(sessao_db, pedido_id)
    cliente = cliente_publico.obter_resumo(sessao_db, pedido.cliente_id)

    separacao = _situacao(sessao_db, "separacao", pedido.id, len(pedido.itens))
    conferencia = _situacao(sessao_db, "conferencia", pedido.id, len(pedido.itens))
    atribuicoes = _atribuicoes_vivas(sessao_db, [pedido.id])
    nomes_atribuicao = usuario_publico.obter_nomes(
        sessao_db,
        [linha.usuario_id for linha in atribuicoes.values()]
        + [linha.atribuido_por_id for linha in atribuicoes.values()],
    )
    itens_separacao = _mapa_itens_processados(sessao_db, "separacao", pedido.id)
    itens_conferencia = _mapa_itens_processados(sessao_db, "conferencia", pedido.id)
    produtos = _produtos_do_pedido(sessao_db, pedido)

    # Separação primeiro, sempre. A conferência só é oferecida quando a
    # separação fechou — é a mesma regra que `iniciar_processo` aplica, aqui
    # só para o front saber qual botão desenhar no rodapé.
    if separacao.status != "finalizada":
        proxima_etapa: TipoProcesso | None = "separacao"
    elif conferencia.status != "finalizada":
        proxima_etapa = "conferencia"
    else:
        proxima_etapa = None

    return PedidoExpedicaoDetalheSchema(
        pedido_id=pedido.id,
        numero=pedido.numero,
        sistema_origem_id=pedido.sistema_origem_id,
        data_pedido=pedido.data_pedido,
        status_pedido=pedido.status_chave,
        pode_iniciar=pedido_publico.pode_iniciar_expedicao(pedido.status_chave),
        observacoes=pedido.observacoes,
        vendedor_nome=(
            usuario_publico.obter_nome(sessao_db, pedido.vendedor_id) if pedido.vendedor_id else None
        ),
        cliente_codigo=cliente.codigo if cliente else None,
        cliente_razao_social=cliente.razao_social if cliente else pedido.cliente_nome_fantasia,
        # Nome e CNPJ vêm do snapshot do pedido, não do cadastro: é o que
        # valia na emissão. O endereço vem do cadastro vivo, porque é pra lá
        # que a mercadoria vai hoje.
        cliente_nome_fantasia=pedido.cliente_nome_fantasia,
        cliente_cnpj=pedido.cliente_cnpj,
        cliente_endereco=cliente.endereco if cliente else "",
        cliente_bairro=cliente.bairro if cliente else None,
        cliente_cep=cliente.cep if cliente else None,
        cliente_cidade_nome=cliente.cidade_nome if cliente else "",
        cliente_cidade_uf=cliente.cidade_uf if cliente else "",
        quantidade_itens=len(pedido.itens),
        quantidade_total=sum(item.quantidade for item in pedido.itens),
        expedicao_status=_mapa_status(sessao_db, [pedido.id]).get(pedido.id),
        separacao=separacao,
        conferencia=conferencia,
        proxima_etapa=proxima_etapa,
        atribuicao_separacao=_para_schema_atribuicao(
            atribuicoes.get((pedido.id, "separacao")), nomes_atribuicao
        ),
        atribuicao_conferencia=_para_schema_atribuicao(
            atribuicoes.get((pedido.id, "conferencia")), nomes_atribuicao
        ),
        itens=[
            _item_do_pedido(
                item,
                produtos.get(item.produto_id, _PRODUTO_PADRAO),
                itens_separacao.get(item.id, ("pendente", 0)),
                itens_conferencia.get(item.id, ("pendente", 0)),
            )
            for item in pedido.itens
        ],
    )


def _para_resposta_processo(
    sessao_db: Session, tipo: TipoProcesso, processo, pedido: pedido_publico.PedidoResumo
) -> ProcessoRespostaSchema:
    configuracao = _config(tipo)
    itens_pedido = {item.id: item for item in pedido.itens}
    produtos = _produtos_do_pedido(sessao_db, pedido)
    return ProcessoRespostaSchema(
        id=processo.id,
        tipo=tipo,
        pedido_id=processo.pedido_id,
        pedido_numero=pedido.sistema_origem_id or pedido.numero,
        status=processo.status,
        usuario_inicio_id=processo.usuario_inicio_id,
        usuario_inicio_nome=usuario_publico.obter_nome(sessao_db, processo.usuario_inicio_id),
        usuario_fim_id=processo.usuario_fim_id,
        data_inicio=processo.data_inicio,
        data_fim=processo.data_fim,
        itens=[
            _item_do_processo(
                item,
                itens_pedido[item.pedido_item_id],
                produtos.get(itens_pedido[item.pedido_item_id].produto_id, _PRODUTO_PADRAO),
                configuracao,
            )
            for item in processo.itens
            if item.sync_deleted_at is None and item.pedido_item_id in itens_pedido
        ],
    )


def obter_processo(sessao_db: Session, tipo: TipoProcesso, processo_id: str) -> ProcessoRespostaSchema:
    processo = _carregar_processo(sessao_db, tipo, processo_id)
    pedido = _obter_pedido(sessao_db, processo.pedido_id)
    return _para_resposta_processo(sessao_db, tipo, processo, pedido)


# --------------------------------------------------------------------------
# Escrita
# --------------------------------------------------------------------------


def _carregar_processo(sessao_db: Session, tipo: TipoProcesso, processo_id: str):
    configuracao = _config(tipo)
    processo = (
        sessao_db.query(configuracao.capa)
        .filter(
            configuracao.capa.id == processo_id,
            configuracao.capa.sync_deleted_at.is_(None),
        )
        .first()
    )
    if processo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{configuracao.rotulo.capitalize()} não encontrada.",
        )
    return processo


def _exigir_processo_em_andamento(processo, configuracao: _TipoConfig):
    if processo.status != "em_andamento":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Esta {configuracao.rotulo} já foi finalizada.",
        )


def _exigir_mesmo_usuario(processo, usuario_id: str, configuracao: _TipoConfig) -> None:
    """Quem começou termina. Sem isso, dois operadores bipando o mesmo pedido
    produzem uma contagem que não é de ninguém — e o tempo por item, que é o
    motivo de existir `data_inicio`/`data_fim`, deixa de significar coisa
    alguma."""
    if processo.usuario_inicio_id != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Esta {configuracao.rotulo} foi iniciada por outro usuário — só ele pode continuá-la.",
        )


def _autorizar_gerente(sessao_db: Session, usuario_gerente: str | None, senha: str | None) -> str:
    """
    Recusa com 422, não 401/403, e isso é deliberado: a credencial do gerente é
    um CAMPO DO PAYLOAD que não passou na validação, não uma afirmação sobre
    quem está chamando. Os outros dois status são reservados ao requisitante —
    401 significa "sua sessão morreu" e 403 "suas permissões mudaram", e o
    `authInterceptor` do front reage aos dois globalmente (desloga / resincroniza
    e sai da tela). Devolver 401 aqui derrubaria a sessão do operador só porque
    o gerente digitou a senha errada, no meio de uma separação.
    """
    if not usuario_gerente or not senha:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Esta ação exige o usuário e a senha de um gerente.",
        )
    gerente_id = usuario_publico.validar_credencial_de_cargo(
        sessao_db, usuario_gerente, senha, CARGO_AUTORIZADOR
    )
    if gerente_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Usuário ou senha de gerente inválidos.",
        )
    return gerente_id


def iniciar_processo(
    sessao_db: Session, tipo: TipoProcesso, pedido_id: str, usuario_id: str
) -> ProcessoRespostaSchema:
    """Abre o processo, ou devolve o que já está em andamento (o botão da tela
    é "Iniciar ou continuar" — as duas coisas caem aqui)."""
    configuracao = _config(tipo)
    pedido = _obter_pedido(sessao_db, pedido_id)

    if not pedido_publico.pode_iniciar_expedicao(pedido.status_chave):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Pedido no status '{pedido.status_chave}' não pode ir para a expedição — "
                f"só status '{pedido_publico.STATUS_LIBERADO_PARA_EXPEDICAO}'."
            ),
        )

    # A atribuição só vale alguma coisa se ela barrar de fato: sem isto, quem
    # souber a URL abre um pedido designado a outra pessoa.
    atribuicao = (
        sessao_db.query(ExpedicaoAtribuicao)
        .filter(
            ExpedicaoAtribuicao.pedido_id == pedido_id,
            ExpedicaoAtribuicao.tipo == tipo,
            ExpedicaoAtribuicao.sync_deleted_at.is_(None),
        )
        .first()
    )
    if atribuicao is not None and atribuicao.usuario_id != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Esta {configuracao.rotulo} está atribuída a outro operador.",
        )

    if tipo == "conferencia":
        separacao = _processo_vivo(sessao_db, "separacao", pedido_id)
        if separacao is None or separacao.status != "finalizada":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A separação deste pedido precisa ser finalizada antes da conferência.",
            )

    existente = _processo_vivo(sessao_db, tipo, pedido_id)
    if existente is not None:
        if existente.status == "finalizada":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A {configuracao.rotulo} deste pedido já foi finalizada.",
            )
        _exigir_mesmo_usuario(existente, usuario_id, configuracao)
        return _para_resposta_processo(sessao_db, tipo, existente, pedido)

    # As linhas de item nascem junto com a capa, uma por item do pedido. Assim
    # o estado de cada item é sempre uma linha existente (pendente = datas
    # nulas), e não existe um segundo caminho "item que ainda não tem linha".
    processo = configuracao.capa(
        pedido_id=pedido_id,
        usuario_inicio_id=usuario_id,
        status="em_andamento",
        data_inicio=_agora(),
        itens=[configuracao.item(pedido_item_id=item.id) for item in pedido.itens],
    )
    sessao_db.add(processo)
    _gravar_status(sessao_db, pedido_id, _STATUS_AO_INICIAR[tipo])
    sessao_db.commit()
    sessao_db.refresh(processo)
    return _para_resposta_processo(sessao_db, tipo, processo, pedido)


def _carregar_item(processo, pedido_item_id: str, configuracao: _TipoConfig):
    item = next(
        (
            linha
            for linha in processo.itens
            if linha.pedido_item_id == pedido_item_id and linha.sync_deleted_at is None
        ),
        None,
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item não faz parte desta {configuracao.rotulo}.",
        )
    return item


def iniciar_item(
    sessao_db: Session, tipo: TipoProcesso, processo_id: str, pedido_item_id: str, usuario_id: str
) -> ProcessoRespostaSchema:
    configuracao = _config(tipo)
    processo = _carregar_processo(sessao_db, tipo, processo_id)
    _exigir_processo_em_andamento(processo, configuracao)
    _exigir_mesmo_usuario(processo, usuario_id, configuracao)

    item = _carregar_item(processo, pedido_item_id, configuracao)
    if item.data_fim is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Este item já foi finalizado."
        )
    if item.data_inicio is not None:
        # Reentrar no mesmo item é normal (o operador voltou pra tela) — não
        # sobrescreve data_inicio, senão o tempo medido seria só o do último
        # retorno, não o do item inteiro.
        return _para_resposta_processo(sessao_db, tipo, processo, _obter_pedido(sessao_db, processo.pedido_id))

    em_andamento = next(
        (
            linha
            for linha in processo.itens
            if linha.sync_deleted_at is None and linha.data_inicio is not None and linha.data_fim is None
        ),
        None,
    )
    if em_andamento is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Finalize o item em andamento antes de começar outro.",
        )

    item.data_inicio = _agora()
    incrementar_versao(item)
    sessao_db.commit()
    sessao_db.refresh(processo)
    return _para_resposta_processo(sessao_db, tipo, processo, _obter_pedido(sessao_db, processo.pedido_id))


def bipar(
    sessao_db: Session,
    tipo: TipoProcesso,
    processo_id: str,
    pedido_item_id: str,
    usuario_id: str,
    dados: BiparSchema,
) -> ProcessoRespostaSchema:
    configuracao = _config(tipo)
    processo = _carregar_processo(sessao_db, tipo, processo_id)
    _exigir_processo_em_andamento(processo, configuracao)
    _exigir_mesmo_usuario(processo, usuario_id, configuracao)

    item = _carregar_item(processo, pedido_item_id, configuracao)
    if item.data_inicio is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Inicie este item antes de bipar."
        )
    if item.data_fim is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Este item já foi finalizado."
        )

    pedido = _obter_pedido(sessao_db, processo.pedido_id)
    item_pedido = next((linha for linha in pedido.itens if linha.id == pedido_item_id), None)
    if item_pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado no pedido."
        )

    produto = produto_publico.obter_por_codigo_barras(sessao_db, dados.codigo_barras)
    if produto is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Código de barras não cadastrado em nenhum produto.",
        )
    if produto.id != item_pedido.produto_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Este código de barras é de outro produto.",
        )

    # Carimba a primeira leitura do processo. Só a primeira: `is None` é o que
    # torna isso idempotente — as leituras seguintes não mexem mais.
    if processo.data_primeiro_bipe is None:
        processo.data_primeiro_bipe = _agora()

    # O pedido é sempre em unidade, mas há produto que só se vende pela caixa
    # fechada: um bipe nele vale a caixa inteira. O multiplicador digitado no
    # coletor conta caixas, então os dois se multiplicam.
    unidades_por_leitura = produto.quantidade_multipla_venda
    quantidade_atual = _quantidade(item, configuracao)
    nova_quantidade = quantidade_atual + dados.multiplicador * unidades_por_leitura
    if nova_quantidade > item_pedido.quantidade:
        detalhe = (
            f"Quantidade acima da pedida: o item tem {item_pedido.quantidade} "
            f"e já foram registrados {quantidade_atual}."
        )
        if unidades_por_leitura > 1:
            detalhe += f" Cada leitura deste produto vale {unidades_por_leitura} unidades."
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detalhe)

    setattr(item, configuracao.campo_quantidade, nova_quantidade)
    incrementar_versao(item)
    sessao_db.commit()
    sessao_db.refresh(processo)
    return _para_resposta_processo(sessao_db, tipo, processo, pedido)


def finalizar_item(
    sessao_db: Session,
    tipo: TipoProcesso,
    processo_id: str,
    pedido_item_id: str,
    usuario_id: str,
    dados: FinalizarItemSchema,
) -> ProcessoRespostaSchema:
    configuracao = _config(tipo)
    processo = _carregar_processo(sessao_db, tipo, processo_id)
    _exigir_processo_em_andamento(processo, configuracao)
    _exigir_mesmo_usuario(processo, usuario_id, configuracao)

    item = _carregar_item(processo, pedido_item_id, configuracao)
    if item.data_inicio is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Este item ainda não foi iniciado."
        )
    if item.data_fim is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Este item já foi finalizado."
        )

    pedido = _obter_pedido(sessao_db, processo.pedido_id)
    item_pedido = next((linha for linha in pedido.itens if linha.id == pedido_item_id), None)
    if item_pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado no pedido."
        )

    quantidade = _quantidade(item, configuracao)
    # Acima da pedida é impossível — `bipar` já recusa. O que pode acontecer é
    # faltar mercadoria, e aí quem responde pela falta é um gerente.
    if quantidade < item_pedido.quantidade:
        item.usuario_autorizador_id = _autorizar_gerente(
            sessao_db, dados.usuario_gerente, dados.senha
        )
        item.divergente = True

    item.data_fim = _agora()
    incrementar_versao(item)

    itens_vivos = [linha for linha in processo.itens if linha.sync_deleted_at is None]
    if all(linha.data_fim is not None for linha in itens_vivos):
        processo.status = "finalizada"
        processo.data_fim = _agora()
        processo.usuario_fim_id = usuario_id
        incrementar_versao(processo)
        _gravar_status(sessao_db, processo.pedido_id, _STATUS_AO_FINALIZAR[tipo])

    sessao_db.commit()
    sessao_db.refresh(processo)
    return _para_resposta_processo(sessao_db, tipo, processo, pedido)


def resetar(
    sessao_db: Session, tipo: TipoProcesso, processo_id: str, dados: CredencialGerenteSchema
) -> None:
    """Soft delete do processo inteiro (capa + itens). O histórico de tempo por
    item continua no banco — é justamente o que se quer auditar depois de um
    reset. Um processo novo pode nascer em seguida, do zero."""
    configuracao = _config(tipo)
    processo = _carregar_processo(sessao_db, tipo, processo_id)
    _autorizar_gerente(sessao_db, dados.usuario_gerente, dados.senha)

    if tipo == "separacao":
        # Resetar a separação com uma conferência viva deixaria a conferência
        # sem o pré-requisito que a autorizou a existir. Reseta a conferência
        # primeiro; aí a separação libera.
        conferencia = _processo_vivo(sessao_db, "conferencia", processo.pedido_id)
        if conferencia is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Resete a conferência deste pedido antes de resetar a separação.",
            )

    for item in processo.itens:
        if item.sync_deleted_at is None:
            marcar_apagado(item)
    marcar_apagado(processo)

    # Resetar a separação apaga a passagem do pedido pelo galpão; resetar a
    # conferência devolve ao marco anterior, que continua verdadeiro — a
    # separação daquele pedido ainda está finalizada.
    if tipo == "separacao":
        _limpar_status(sessao_db, processo.pedido_id)
    else:
        _gravar_status(sessao_db, processo.pedido_id, pedido_publico.STATUS_SEPARADO)

    sessao_db.commit()
