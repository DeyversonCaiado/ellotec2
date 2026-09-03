"""
Regra de negócio da expedição: separação e conferência de um pedido.

Os dois processos têm exatamente o mesmo ciclo de vida (abre → item a item →
fecha), só mudam a tabela e o nome da coluna de quantidade. Por isso existe
`_TIPOS` logo abaixo, em vez de dois blocos gêmeos de ~200 linhas cada: a
regra mora num lugar só, e uma correção não precisa ser feita duas vezes.

Fronteiras com outros domínios: este arquivo só conversa com `pedidos`,
`clientes`, `produtos`, `usuarios`, `estoque` e `enderecamento` pelos
respectivos `*_publico.py` (ver ARCHITECTURE.md → "Regras de import entre
domínios").

O endereço da mercadoria é o caso mais novo dessa lista e vale explicar: ele
NÃO está mais na linha do pedido. A expedição parte do par (produto, lote) do
item, pede a `estoque_publico` o id do lote e pede a `enderecamento_publico` os
endereços daquele lote — dois canais de leitura, nenhuma query em tabela alheia.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.clientes import cliente_publico
from app.domains.empresas import empresa_publico
from app.domains.enderecamento import enderecamento_publico
from app.domains.estoque import estoque_publico
from app.domains.expedicao.expedicao_contrato import (
    AtribuicaoSchema,
    AtribuirSchema,
    BiparSchema,
    EmpresaFiltroSchema,
    CredencialGerenteSchema,
    EnderecoItemSchema,
    FinalizarItemSchema,
    FinalizarNoSistemaOrigemSchema,
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
from app.domains.expedicao_configuracoes import expedicao_configuracao_publico
from app.domains.pedidos import pedido_publico
from app.domains.produtos import produto_publico
from app.domains.sistema_origem import sistema_origem_publico
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


def _linhas_que_contam(processo, ids_do_pedido: set[str] | None = None) -> list:
    """As linhas vivas do processo que ainda correspondem a um item do pedido.

    A integração pode remover uma linha de um pedido que já está no galpão. Do
    lado de `pedidos` isso é um `marcar_apagado()`, e a linha some da fronteira
    (`pedido_publico`). Do lado de cá sobra uma linha de separação órfã: viva na
    tabela, invisível na tela (`_para_resposta_processo` só monta o que ainda
    está no pedido) e sem jeito de ser finalizada.

    Sem este filtro, essa linha órfã trava o processo para sempre — "todos os
    itens fecharam?" nunca dá verdadeiro — e o cabeçalho passa a mostrar coisas
    como "2 de 1", porque os finalizados vêm do processo e o total vem do pedido.

    `ids_do_pedido` nulo significa "não sei quais são" e devolve tudo, para o
    chamador que não tem o pedido em mãos não pagar uma consulta a mais.
    """
    vivas = [linha for linha in processo.itens if linha.sync_deleted_at is None]
    if ids_do_pedido is None:
        return vivas
    return [linha for linha in vivas if linha.pedido_item_id in ids_do_pedido]


def _situacao(
    sessao_db: Session, tipo: TipoProcesso, pedido_id: str, ids_do_pedido: set[str]
) -> SituacaoProcessoSchema:
    configuracao = _config(tipo)
    processo = _processo_vivo(sessao_db, tipo, pedido_id)
    if processo is None:
        return SituacaoProcessoSchema(
            id=None,
            status="nao_iniciada",
            usuario_id=None,
            usuario_nome=None,
            itens_finalizados=0,
            itens_total=len(ids_do_pedido),
            tem_divergencia=False,
        )

    itens_vivos = _linhas_que_contam(processo, ids_do_pedido)
    nomes_gestor = usuario_publico.obter_nomes(
        sessao_db,
        [
            id_gestor
            for id_gestor in (processo.usuario_gestor_inicio_id, processo.usuario_gestor_fim_id)
            if id_gestor
        ],
    )
    return SituacaoProcessoSchema(
        id=processo.id,
        status=processo.status,
        usuario_id=processo.usuario_inicio_id,
        usuario_nome=usuario_publico.obter_nome(sessao_db, processo.usuario_inicio_id),
        itens_finalizados=sum(1 for item in itens_vivos if item.data_fim is not None),
        itens_total=len(ids_do_pedido),
        tem_divergencia=any(item.divergente for item in itens_vivos),
        data_primeiro_bipe=processo.data_primeiro_bipe,
        data_fim=processo.data_fim,
        data_inicio=processo.data_inicio,
        usuario_gestor_inicio_nome=nomes_gestor.get(processo.usuario_gestor_inicio_id),
        usuario_gestor_fim_nome=nomes_gestor.get(processo.usuario_gestor_fim_id),
        delegado=bool(processo.usuario_gestor_inicio_id or processo.usuario_gestor_fim_id),
        # Só a conferência tem as colunas — ver o mesmo getattr em
        # `_para_resposta_processo`.
        finalizado_origem_em=getattr(processo, "finalizado_origem_em", None),
        motivo_falha_origem=getattr(processo, "motivo_falha_origem", None),
        tentativa_origem_em=getattr(processo, "tentativa_origem_em", None),
        tentativa_origem_usuario_nome=_nome_gestor(
            sessao_db, getattr(processo, "tentativa_origem_usuario_id", None)
        ),
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

    # Operadores e gestores num lote só — são todos nomes de usuário, e separar
    # em duas consultas dobraria as idas ao banco por página sem ganhar nada.
    nomes = usuario_publico.obter_nomes(
        sessao_db,
        [
            id_usuario
            for processo in por_pedido.values()
            for id_usuario in (
                processo.usuario_inicio_id,
                processo.usuario_gestor_inicio_id,
                processo.usuario_gestor_fim_id,
                # Só a conferência tem — na separação o getattr devolve None e
                # o `if` abaixo descarta, sem consulta a mais.
                getattr(processo, "tentativa_origem_usuario_id", None),
            )
            if id_usuario
        ],
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

        itens_vivos = _linhas_que_contam(processo, {item.id for item in pedido.itens})
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
            data_inicio=processo.data_inicio,
            usuario_gestor_inicio_nome=nomes.get(processo.usuario_gestor_inicio_id),
            usuario_gestor_fim_nome=nomes.get(processo.usuario_gestor_fim_id),
            delegado=bool(processo.usuario_gestor_inicio_id or processo.usuario_gestor_fim_id),
            finalizado_origem_em=getattr(processo, "finalizado_origem_em", None),
            motivo_falha_origem=getattr(processo, "motivo_falha_origem", None),
            tentativa_origem_em=getattr(processo, "tentativa_origem_em", None),
            tentativa_origem_usuario_nome=nomes.get(
                getattr(processo, "tentativa_origem_usuario_id", None)
            ),
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

# Quem tem esta permissão inicia e finaliza uma etapa NO NOME do operador
# atribuído. Separada de PERMISSAO_ATRIBUIR de propósito: distribuir trabalho e
# executar por outra pessoa são coisas diferentes.
PERMISSAO_DELEGAR = "expedicao.delegar"

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


def _atribuicao_viva(
    sessao_db: Session, tipo: TipoProcesso, pedido_id: str
) -> ExpedicaoAtribuicao | None:
    """O responsável designado por uma etapa de um pedido, ou None."""
    return (
        sessao_db.query(ExpedicaoAtribuicao)
        .filter(
            ExpedicaoAtribuicao.pedido_id == pedido_id,
            ExpedicaoAtribuicao.tipo == tipo,
            ExpedicaoAtribuicao.sync_deleted_at.is_(None),
        )
        .first()
    )


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


def _aplicar_recorte(ids_base: set[str], recorte: _Recorte) -> set[str]:
    """O mesmo recorte que a listagem aplica, mas em cima de um conjunto de ids
    já em memória — é assim que os contadores por situação saem sem repetir a
    consulta paginada uma vez por aba."""
    resultado = ids_base
    for conjunto in recorte.incluir:
        resultado = resultado & set(conjunto)
    if recorte.excluir:
        resultado = resultado - set(recorte.excluir)
    return resultado


def _contagens_por_situacao(sessao_db: Session, ids_base: list[str]) -> dict[str, int]:
    """Quantos pedidos caem em cada situação, NO PERÍODO.

    Os contadores respondem "quanto tem no galpão hoje", e por isso levam em
    conta **apenas o período** — nem termo, nem status do ERP, nem empresa, nem
    operador, nem a situação escolhida. Assim eles não mudam enquanto a pessoa
    mexe nos filtros, e servem de painel fixo: o coordenador olha e sabe que há
    12 pedidos parados e 3 em conferência naquele intervalo, independente do que
    ele esteja procurando na lista.

    A ÚNICA coisa fora o período que entra é a **visibilidade por atribuição**,
    e ela entra porque não é filtro: é regra de acesso. Contar pedido que a
    pessoa não pode ver entregaria, no número, exatamente o que a lista esconde.

    Derivado de `_recorte_da_situacao`, o mesmo que o filtro usa. Reaproveitar em
    vez de reescrever a regra em SQL de contagem é deliberado: seriam duas
    definições da mesma coisa, e elas divergiriam em silêncio no dia em que
    alguém mexesse numa só — o número da aba deixaria de bater com a lista que
    ela abre.
    """
    conjunto_base = set(ids_base)
    return {
        situacao: len(_aplicar_recorte(conjunto_base, _recorte_da_situacao(sessao_db, situacao)))
        for situacao in SITUACOES_VALIDAS
    }


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
    if situacao and situacao != "todos" and situacao not in SITUACOES_VALIDAS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Situação inválida. Use uma destas: {', '.join(SITUACOES_VALIDAS)}.",
        )

    # A visibilidade fica separada dos filtros porque ela NÃO é um filtro: é
    # regra de acesso. Os contadores ignoram os filtros da tela, mas não podem
    # ignorar isto — contar pedido que a pessoa não pode ver vazaria, no número,
    # exatamente o que a lista esconde.
    conjuntos_visibilidade: list[list[str]] = []
    if not ver_tudo:
        conjuntos_visibilidade.append(
            _pedidos_atribuidos_a(sessao_db, usuario_id) if usuario_id else []
        )

    conjuntos_obrigatorios: list[list[str]] = list(conjuntos_visibilidade)
    ids_excluidos: list[str] = []

    if operador_id:
        conjuntos_obrigatorios.append(_pedidos_do_operador(sessao_db, operador_id))

    if situacao and situacao != "todos":
        recorte = _recorte_da_situacao(sessao_db, situacao)
        conjuntos_obrigatorios.extend(recorte.incluir)
        ids_excluidos.extend(recorte.excluir)

    def _interseccao(conjuntos: list[list[str]]) -> list[str] | None:
        if not conjuntos:
            return None
        resultado = set(conjuntos[0])
        for conjunto in conjuntos[1:]:
            resultado &= set(conjunto)
        return list(resultado)

    # Contadores do PERÍODO inteiro: sem termo, sem status do ERP, sem empresa,
    # sem operador e sem a situação escolhida. Só o período e a visibilidade.
    contagens = _contagens_por_situacao(
        sessao_db,
        pedido_publico.listar_ids_para_expedicao(
            sessao_db,
            data_inicio,
            data_fim,
            termo=None,
            status_chaves=None,
            ids_permitidos=_interseccao(conjuntos_visibilidade),
            ids_excluidos=None,
            empresa_id=None,
        ),
    )

    pedido_ids_visiveis = _interseccao(conjuntos_obrigatorios)
    if pedido_ids_visiveis is not None:
        if not pedido_ids_visiveis:
            # Nenhum pedido atende: a lista é vazia, e nem vale ir ao banco de
            # pedidos. Vale tanto para "nada atribuído a mim" quanto para um
            # filtro que não casou com nada.
            return PedidoExpedicaoListaPaginadaSchema(
                items=[],
                total=0,
                page=page,
                per_page=per_page,
                sort=sort,
                sort_type=sort_type,
                # Os contadores vão mesmo com a lista vazia: é justamente aí que
                # o usuário precisa deles, para ver em qual aba estão os pedidos
                # que ele está procurando.
                contagens_por_situacao=contagens,
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
    # Endereçamento da página inteira em bloco — a listagem precisa dele porque
    # `pode_iniciar` já embute a consistência, e o coordenador tem que ver na
    # fila qual pedido está travado sem abrir um por um.
    produtos_da_pagina = produto_publico.obter_para_expedicao(
        sessao_db,
        [item.produto_id for pedido in pedidos for item in pedido.itens],
    )
    # Uma leitura só para a página inteira: os parâmetros são do galpão, não do
    # pedido, e consultá-los por linha daria N consultas iguais.
    enderecamento = _enderecamento_dos_pedidos(
        sessao_db,
        pedidos,
        produtos_da_pagina,
        expedicao_configuracao_publico.obter_parametros(sessao_db),
    )
    bloqueios = {
        pedido.id: _bloqueio_do_pedido(
            pedido,
            enderecamento,
            pedido.id in separacoes and separacoes[pedido.id].status == "finalizada",
        )
        for pedido in pedidos
    }
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
            pode_iniciar=(
                pedido_publico.pode_iniciar_expedicao(pedido.status_chave)
                and bloqueios[pedido.id] is None
            ),
            bloqueio_enderecamento=bloqueios[pedido.id],
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
        contagens_por_situacao=contagens,
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


# --------------------------------------------------------------------------
# Consistência do endereçamento
#
# Antes de deixar o operador começar, a expedição confere se o que está
# endereçado no galpão sustenta o que o pedido pede. Duas regras, e as duas
# barram o pedido INTEIRO — não só o item com problema.
#
# **Por que o pedido inteiro.** Separação é uma viagem só pelo galpão, com uma
# caixa só. Liberar os itens bons e deixar um pendurado significa que alguém vai
# ter que voltar depois para terminar o mesmo pedido — e, no meio disso, o
# pedido fica num estado que não é "separado" nem "não separado". É mais barato
# resolver o endereçamento antes do que remendar depois.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class _Enderecamento:
    """O estado de endereçamento de UM item do pedido."""

    enderecos: list[EnderecoItemSchema]
    quantidade_enderecada: Decimal
    # None = consistente. Preenchido = a frase que a tela mostra no quadro
    # vermelho e que o 409 devolve quando alguém tenta iniciar assim mesmo.
    bloqueio: str | None


_SEM_ENDERECAMENTO = _Enderecamento(
    enderecos=[], quantidade_enderecada=Decimal(0), bloqueio=None
)


def _bloqueio_do_item(
    item,
    enderecos: list[EnderecoItemSchema],
    enderecada: Decimal,
    multipla_venda: int,
    parametros: expedicao_configuracao_publico.ParametrosExpedicao,
) -> str | None:
    """As duas regras de consistência, na ordem em que o operador as entende.

    1. **Saldo endereçado suficiente** (`soma >= pedido`). É `>=`, não `==`: o
       endereço guarda o estoque inteiro do lote, não uma reserva do pedido, e
       exigir igualdade reprovaria o caso normal de ter mais mercadoria na
       prateleira do que o cliente comprou.

    2. **Cada endereço fecha em múltiplo da embalagem de venda.** Produto que só
       se vende em caixa de 12 não pode ter 7 unidades soltas num endereço: o
       operador bipa a caixa, cada bipe vale 12, e ele nunca conseguiria fechar
       aquele endereço. Um saldo assim é erro de cadastro ou sobra de uma baixa
       manual, e é melhor descobrir agora do que com o operador na frente da
       prateleira.

    **Cada uma tem o seu parâmetro** em `expedicao_configuracoes`, e é aqui — no
    item, antes de o texto existir — que a configuração decide. Desligar uma
    regra é a regra não ser calculada, não um bloqueio calculado que alguém
    ignora depois: `bloqueio` preenchido significa, em todo o resto do código e
    do front, "este pedido não pode ser iniciado".

    Elas são parâmetros separados porque são problemas diferentes do galpão —
    falta de mercadoria endereçada versus saldo quebrado numa prateleira — e um
    interruptor só obrigaria a desligar as duas para resolver metade.
    """
    if not parametros.permite_conferir_com_divergencia and enderecada < Decimal(
        item.quantidade
    ):
        return (
            f"Endereçamento insuficiente: os endereços somam {_texto_quantidade(enderecada)} "
            f"e o pedido precisa de {item.quantidade}."
        )

    if not parametros.permite_conferir_fora_do_multiplo_de_venda and multipla_venda > 1:
        quebrados = [
            endereco
            for endereco in enderecos
            if Decimal(str(endereco.quantidade)) % multipla_venda != 0
        ]
        if quebrados:
            primeiro = quebrados[0]
            return (
                f"Endereço {primeiro.descricao} tem "
                f"{_texto_quantidade(Decimal(str(primeiro.quantidade)))}, que não fecha "
                f"em múltiplo de {multipla_venda} (embalagem de venda do produto)."
            )

    return None


def _texto_quantidade(valor: Decimal) -> str:
    """Quantidade sem casas decimais quando ela é inteira — o galpão fala '3',
    não '3.000'."""
    normalizado = Decimal(valor).normalize()
    return str(normalizado.quantize(Decimal(1)) if normalizado == normalizado.to_integral() else normalizado)


def _enderecamento_dos_pedidos(
    sessao_db: Session,
    pedidos: list[pedido_publico.PedidoResumo],
    produtos: dict[str, produto_publico.ProdutoExpedicao],
    parametros: expedicao_configuracao_publico.ParametrosExpedicao,
) -> dict[str, _Enderecamento]:
    """pedido_item_id -> endereços daquele lote, com quantidade e bloqueio.

    Consulta em lote para a página inteira, não por item: os pares
    (produto, lote) são agrupados por empresa — lote é por empresa, então
    `estoque_publico` precisa de uma chamada por empresa — e os endereços de
    todos os lotes saem de uma consulta só.
    """
    if not pedidos:
        return {}

    pares_por_empresa: dict[str, set[tuple[str, str]]] = {}
    for pedido in pedidos:
        for item in pedido.itens:
            if item.lote:
                pares_por_empresa.setdefault(pedido.empresa_id, set()).add(
                    (item.produto_id, item.lote)
                )

    ids_de_lote: dict[tuple[str, str, str], str] = {}
    for empresa_id, pares in pares_por_empresa.items():
        for chave, lote_id in estoque_publico.obter_ids_de_lotes(
            sessao_db, empresa_id, list(pares)
        ).items():
            ids_de_lote[(empresa_id, *chave)] = lote_id

    por_lote = enderecamento_publico.obter_enderecos_por_lote(
        sessao_db, list(ids_de_lote.values())
    )

    resultado: dict[str, _Enderecamento] = {}
    for pedido in pedidos:
        for item in pedido.itens:
            lote_id = ids_de_lote.get((pedido.empresa_id, item.produto_id, item.lote))
            enderecos = [
                EnderecoItemSchema(
                    endereco_id=linha.endereco_id,
                    descricao=linha.descricao,
                    quantidade=float(linha.quantidade),
                )
                for linha in por_lote.get(lote_id, [])
            ]
            enderecada = sum(
                (Decimal(str(endereco.quantidade)) for endereco in enderecos), Decimal(0)
            )
            produto = produtos.get(item.produto_id, _PRODUTO_PADRAO)
            resultado[item.id] = _Enderecamento(
                enderecos=enderecos,
                quantidade_enderecada=enderecada,
                bloqueio=_bloqueio_do_item(
                    item,
                    enderecos,
                    enderecada,
                    produto.quantidade_multipla_venda,
                    parametros,
                ),
            )
    return resultado


def _bloqueio_do_pedido(
    pedido: pedido_publico.PedidoResumo,
    enderecamento: dict[str, _Enderecamento],
    separacao_finalizada: bool = False,
) -> str | None:
    """A primeira pendência de endereçamento do pedido, ou None se está tudo em
    ordem. Basta um item para travar o pedido — ver o comentário do bloco.

    **Os parâmetros do galpão não chegam aqui**, e isso é de propósito: quem os
    aplica é `_bloqueio_do_item`, uma regra de cada vez. Quando o coordenador
    desliga uma delas, ela deixa de ser calculada — não vira um bloqueio
    calculado que esta função ignora depois. Ver `expedicao_configuracoes`.

    **Depois que a separação fecha, a regra deixa de valer.** A mercadoria já
    saiu da prateleira (foi esta função que autorizou, e o fechamento baixou o
    saldo), então o endereço está legitimamente vazio. Sem esta saída, a
    conferência do próprio pedido que acabou de ser separado seria recusada por
    "endereçamento insuficiente" — o sistema barrando a consequência do que ele
    mesmo fez.
    """
    if separacao_finalizada:
        return None
    for item in pedido.itens:
        bloqueio = enderecamento.get(item.id, _SEM_ENDERECAMENTO).bloqueio
        if bloqueio:
            return f"{item.produto_codigo} — {bloqueio}"
    return None


def _separacao_finalizada(sessao_db: Session, pedido_id: str) -> bool:
    processo = _processo_vivo(sessao_db, "separacao", pedido_id)
    return processo is not None and processo.status == "finalizada"


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
    enderecamento: "_Enderecamento",
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
        enderecos=enderecamento.enderecos,
        quantidade_enderecada=float(enderecamento.quantidade_enderecada),
        bloqueio=enderecamento.bloqueio,
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
    enderecamento: "_Enderecamento",
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
        enderecos=enderecamento.enderecos,
        quantidade_enderecada=float(enderecamento.quantidade_enderecada),
        bloqueio=enderecamento.bloqueio,
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

    ids_do_pedido = {item.id for item in pedido.itens}
    separacao = _situacao(sessao_db, "separacao", pedido.id, ids_do_pedido)
    conferencia = _situacao(sessao_db, "conferencia", pedido.id, ids_do_pedido)
    atribuicoes = _atribuicoes_vivas(sessao_db, [pedido.id])
    nomes_atribuicao = usuario_publico.obter_nomes(
        sessao_db,
        [linha.usuario_id for linha in atribuicoes.values()]
        + [linha.atribuido_por_id for linha in atribuicoes.values()],
    )
    itens_separacao = _mapa_itens_processados(sessao_db, "separacao", pedido.id)
    itens_conferencia = _mapa_itens_processados(sessao_db, "conferencia", pedido.id)
    produtos = _produtos_do_pedido(sessao_db, pedido)
    enderecamento = _enderecamento_dos_pedidos(
        sessao_db,
        [pedido],
        produtos,
        expedicao_configuracao_publico.obter_parametros(sessao_db),
    )
    bloqueio_enderecamento = _bloqueio_do_pedido(
        pedido, enderecamento, _separacao_finalizada(sessao_db, pedido.id)
    )

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
        # As duas barreiras juntas: status do ERP E endereçamento consistente.
        pode_iniciar=(
            pedido_publico.pode_iniciar_expedicao(pedido.status_chave)
            and bloqueio_enderecamento is None
        ),
        bloqueio_enderecamento=bloqueio_enderecamento,
        status_permite_iniciar=pedido_publico.pode_iniciar_expedicao(pedido.status_chave),
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
                enderecamento.get(item.id, _SEM_ENDERECAMENTO),
            )
            for item in pedido.itens
        ],
    )


def _nome_gestor(sessao_db: Session, gestor_id: str | None) -> str | None:
    """Nulo é o caso normal (o operador executou sozinho) — sem o guarda, cada
    resposta faria uma consulta a mais só para receber None de volta."""
    return usuario_publico.obter_nome(sessao_db, gestor_id) if gestor_id else None


def _para_resposta_processo(
    sessao_db: Session, tipo: TipoProcesso, processo, pedido: pedido_publico.PedidoResumo
) -> ProcessoRespostaSchema:
    configuracao = _config(tipo)
    itens_pedido = {item.id: item for item in pedido.itens}
    produtos = _produtos_do_pedido(sessao_db, pedido)
    enderecamento = _enderecamento_dos_pedidos(
        sessao_db,
        [pedido],
        produtos,
        expedicao_configuracao_publico.obter_parametros(sessao_db),
    )
    return ProcessoRespostaSchema(
        id=processo.id,
        tipo=tipo,
        pedido_id=processo.pedido_id,
        pedido_numero=pedido.sistema_origem_id or pedido.numero,
        status=processo.status,
        usuario_inicio_id=processo.usuario_inicio_id,
        usuario_inicio_nome=usuario_publico.obter_nome(sessao_db, processo.usuario_inicio_id),
        usuario_fim_id=processo.usuario_fim_id,
        usuario_gestor_inicio_nome=_nome_gestor(sessao_db, processo.usuario_gestor_inicio_id),
        usuario_gestor_fim_nome=_nome_gestor(sessao_db, processo.usuario_gestor_fim_id),
        data_inicio=processo.data_inicio,
        data_fim=processo.data_fim,
        # getattr porque só `Conferencia` tem as colunas: na separação não há
        # nada a fechar no ERP, e criar as mesmas duas colunas lá só para o
        # acesso ficar simétrico seria schema por conveniência de código.
        finalizado_origem_em=getattr(processo, "finalizado_origem_em", None),
        motivo_falha_origem=getattr(processo, "motivo_falha_origem", None),
        tentativa_origem_em=getattr(processo, "tentativa_origem_em", None),
        tentativa_origem_usuario_nome=_nome_gestor(
            sessao_db, getattr(processo, "tentativa_origem_usuario_id", None)
        ),
        itens=[
            _item_do_processo(
                item,
                itens_pedido[item.pedido_item_id],
                produtos.get(itens_pedido[item.pedido_item_id].produto_id, _PRODUTO_PADRAO),
                configuracao,
                enderecamento.get(item.pedido_item_id, _SEM_ENDERECAMENTO),
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

    # O `podeIniciar` da tela esconde o botão, mas quem barra de fato é aqui —
    # o front é UX, o backend é a barreira (ver ARCHITECTURE.md → "Toda
    # permissão é checada no backend, sempre"; a ideia vale para regra de
    # negócio também).
    produtos = _produtos_do_pedido(sessao_db, pedido)
    bloqueio = _bloqueio_do_pedido(
        pedido,
        _enderecamento_dos_pedidos(
            sessao_db,
            [pedido],
            produtos,
            expedicao_configuracao_publico.obter_parametros(sessao_db),
        ),
        _separacao_finalizada(sessao_db, pedido_id),
    )
    if bloqueio is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Endereçamento inconsistente, o pedido não pode ser iniciado. {bloqueio}",
        )

    # A atribuição só vale alguma coisa se ela barrar de fato: sem isto, quem
    # souber a URL abre um pedido designado a outra pessoa.
    atribuicao = _atribuicao_viva(sessao_db, tipo, pedido_id)
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


def _baixar_do_enderecamento(
    sessao_db: Session,
    tipo: TipoProcesso,
    processo,
    pedido,
    liberar_enderecamento: bool = False,
) -> None:
    """Tira do endereço o que foi separado. Chamada quando o processo FECHA.

    **Só na separação.** É nela que a mercadoria sai fisicamente da prateleira;
    a conferência mexe no que já está na caixa. Baixar nas duas descontaria o
    mesmo produto duas vezes do galpão.

    **Escrita em domínio alheio, pela borda.** Quem é dono do saldo de endereço
    é o `enderecamento` — a expedição pede a baixa por
    `enderecamento_publico.baixar_lote`, que não dá `commit()`. A baixa e a
    finalização ficam na MESMA transação: se qualquer coisa falhar depois, o
    `rollback` desfaz as duas juntas e o saldo do galpão não fica errado. Ver
    ARCHITECTURE.md → "Escrita pela borda".

    Item sem lote é pulado: sem lote não há linha em `estoque_lotes` de onde
    baixar. Hoje isso não acontece (a consistência de endereçamento barraria o
    pedido antes), mas pular é mais seguro que estourar no fechamento de um
    processo que o operador já terminou.

    `liberar_enderecamento` só é `True` quando quem fechou a etapa tem
    `expedicao.enderecamento.liberar` — é a etapa aberta pela exceção de
    emergência, e o endereço não tem o saldo que a baixa pede justamente porque
    ele estava errado. Nesse caso o `enderecamento` zera o que havia em vez de
    recusar; ver `enderecamento_publico.baixar_lote`.
    """
    if tipo != "separacao":
        return

    configuracao = _config(tipo)
    itens_pedido = {item.id: item for item in pedido.itens}
    pares = [(item.produto_id, item.lote) for item in pedido.itens if item.lote]
    ids_de_lote = estoque_publico.obter_ids_de_lotes(sessao_db, pedido.empresa_id, pares)

    for linha in processo.itens:
        if linha.sync_deleted_at is not None:
            continue
        item = itens_pedido.get(linha.pedido_item_id)
        if item is None or not item.lote:
            continue

        quantidade = Decimal(_quantidade(linha, configuracao))
        if quantidade <= 0:
            continue

        lote_id = ids_de_lote.get((item.produto_id, item.lote))
        if lote_id is None:
            continue

        enderecamento_publico.baixar_lote(
            sessao_db, lote_id, quantidade, permitir_saldo_insuficiente=liberar_enderecamento
        )


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

    itens_vivos = _linhas_que_contam(processo, {linha.id for linha in pedido.itens})
    if all(linha.data_fim is not None for linha in itens_vivos):
        processo.status = "finalizada"
        processo.data_fim = _agora()
        processo.usuario_fim_id = usuario_id
        incrementar_versao(processo)
        _gravar_status(sessao_db, processo.pedido_id, _STATUS_AO_FINALIZAR[tipo])
        _baixar_do_enderecamento(sessao_db, tipo, processo, pedido)

    sessao_db.commit()
    sessao_db.refresh(processo)
    return _para_resposta_processo(sessao_db, tipo, processo, pedido)


# ---------------------------------------------------------------------------
# Execução delegada: o gerente executa a etapa NO NOME do operador atribuído
#
# O galpão não tem coletor para todo mundo. O gerente designa uma pessoa, ela
# separa no papel e avisa quando termina; o gerente registra o início e o fim
# aqui. Por isso as duas funções abaixo não bipam nada — não há leitura para
# registrar, e fingir que houve seria pior que assumir o que de fato aconteceu.
#
# Em ambas, `usuario_inicio_id`/`usuario_fim_id` recebem o OPERADOR (de quem é o
# trabalho) e as colunas `usuario_gestor_*` recebem quem clicou. É esse par que
# faz o relatório futuro sair com as duas pessoas.
#
# Nenhuma delas pede senha de gerente, ao contrário de `resetar` e do fecho com
# falta em `finalizar_item`. Lá a senha existe porque quem está na tela é o
# operador, e a credencial é a única prova de que um gerente autorizou. Aqui
# quem está logado JÁ é o gerente, com `expedicao.delegar` checada no endpoint —
# pedir senha seria pedir que ele prove ser ele mesmo.
# ---------------------------------------------------------------------------


def _operador_da_etapa(sessao_db: Session, tipo: TipoProcesso, pedido_id: str, quem_clicou: str) -> str:
    """De quem é o TRABALHO desta etapa.

    Com responsável atribuído, é ele — o gerente está executando em nome dele,
    que é o caso que a execução delegada existe para resolver.

    **Sem responsável, é quem clicou.** Antes isso era um 409 pedindo para
    atribuir alguém primeiro, e a exigência não se sustentava: o pedido sem
    responsável não é "de ninguém", é de quem resolveu pegá-lo. Obrigar a passar
    pela atribuição para começar um pedido que a própria pessoa vai fazer era
    cerimônia sem dono — e o gerente acabava atribuindo a si mesmo só para
    liberar o botão, o que registra a mesma coisa com um passo a mais.
    """
    atribuicao = _atribuicao_viva(sessao_db, tipo, pedido_id)
    return atribuicao.usuario_id if atribuicao is not None else quem_clicou


def _gestor_ou_nulo(quem_clicou: str, operador_id: str) -> str | None:
    """O campo de gestor só é preenchido quando quem clicou NÃO é o operador.

    É o que dá sentido à coluna: ela responde "quem clicou, quando não foi o
    próprio operador". Gravar o gerente ali quando ele é o operador diria que
    ele executou em nome de si mesmo, e o relatório de produtividade contaria
    a mesma pessoa duas vezes.
    """
    return quem_clicou if quem_clicou != operador_id else None


def iniciar_delegado(
    sessao_db: Session,
    tipo: TipoProcesso,
    pedido_id: str,
    gestor_id: str,
    liberar_enderecamento: bool = False,
) -> ProcessoRespostaSchema:
    """Abre a etapa com todos os itens iniciados, creditada ao operador
    atribuído — ou a quem clicou, quando não há responsável designado.

    Todos de uma vez, e não um a um: quem vai andar pelo galpão é o operador,
    com a lista na mão. A trava de "um item em andamento por vez" existe para
    medir o tempo POR ITEM na bipagem — aqui não há bipagem, e aplicá-la
    obrigaria o gerente a dar um clique por linha sem medir nada.

    `liberar_enderecamento` é a exceção de emergência (permissão
    `expedicao.enderecamento.liberar`, checada no router): com ela, a
    inconsistência de endereçamento deixa de barrar a abertura. **O status do
    ERP continua barrando** — ele não é problema do galpão, e nada que se faça
    daqui o resolve.
    """
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

    # Mesma barreira de `iniciar_processo` — o botão delegado é outro caminho
    # para a mesma etapa, e um caminho que não checasse seria o buraco por onde
    # a regra some. A diferença é só quem pode atravessá-la.
    if not liberar_enderecamento:
        produtos = _produtos_do_pedido(sessao_db, pedido)
        bloqueio = _bloqueio_do_pedido(
            pedido,
            _enderecamento_dos_pedidos(
                sessao_db,
                [pedido],
                produtos,
                expedicao_configuracao_publico.obter_parametros(sessao_db),
            ),
            _separacao_finalizada(sessao_db, pedido_id),
        )
        if bloqueio is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Endereçamento inconsistente, o pedido não pode ser iniciado. {bloqueio}",
            )

    operador_id = _operador_da_etapa(sessao_db, tipo, pedido_id, gestor_id)

    if tipo == "conferencia":
        separacao = _processo_vivo(sessao_db, "separacao", pedido_id)
        if separacao is None or separacao.status != "finalizada":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A separação deste pedido precisa ser finalizada antes da conferência.",
            )

    existente = _processo_vivo(sessao_db, tipo, pedido_id)
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {configuracao.rotulo} deste pedido já foi iniciada.",
        )

    agora = _agora()
    processo = configuracao.capa(
        pedido_id=pedido_id,
        usuario_inicio_id=operador_id,
        usuario_gestor_inicio_id=_gestor_ou_nulo(gestor_id, operador_id),
        status="em_andamento",
        data_inicio=agora,
        itens=[
            configuracao.item(pedido_item_id=item.id, data_inicio=agora) for item in pedido.itens
        ],
    )
    sessao_db.add(processo)
    _gravar_status(sessao_db, pedido_id, _STATUS_AO_INICIAR[tipo])
    sessao_db.commit()
    sessao_db.refresh(processo)
    return _para_resposta_processo(sessao_db, tipo, processo, pedido)


def finalizar_delegado(
    sessao_db: Session,
    tipo: TipoProcesso,
    pedido_id: str,
    gestor_id: str,
    liberar_enderecamento: bool = False,
) -> ProcessoRespostaSchema:
    """Fecha a etapa inteira no nome do operador, completando os itens abertos.

    Cada item pendente fecha com a quantidade PEDIDA, sem divergência: o gerente
    está confirmando que o operador fez o trabalho completo. Fechar com o que
    estiver gravado marcaria tudo como divergente (ninguém bipou), e o relatório
    de falta passaria a apontar falta que não houve.

    Falta de verdade continua pelo caminho de sempre — item a item, com senha de
    gerente em `finalizar_item`.

    `liberar_enderecamento` (permissão `expedicao.enderecamento.liberar`, checada
    no router) é o que faz a etapa aberta em emergência conseguir FECHAR: sem
    ele, a baixa do endereço recusaria com "saldo endereçado insuficiente" e o
    pedido ficaria preso em andamento — liberar o início sem liberar o fim não
    destravaria faturamento nenhum.
    """
    configuracao = _config(tipo)
    processo = _processo_vivo(sessao_db, tipo, pedido_id)
    if processo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Este pedido não tem {configuracao.rotulo} em andamento.",
        )
    _exigir_processo_em_andamento(processo, configuracao)

    # Se o responsável mudou depois da abertura, quem o gerente está creditando
    # não é mais quem fez o trabalho. Recusar é mais honesto que gravar errado.
    #
    # Sem atribuição não há o que conferir: o processo já nasceu creditado a
    # quem o abriu (ver `_operador_da_etapa`), e é esse crédito que vale.
    atribuicao = _atribuicao_viva(sessao_db, tipo, processo.pedido_id)
    if atribuicao is not None and atribuicao.usuario_id != processo.usuario_inicio_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Esta {configuracao.rotulo} foi aberta por outro operador. "
                "Resete o processo antes de finalizá-lo em nome do responsável atual."
            ),
        )

    pedido = _obter_pedido(sessao_db, processo.pedido_id)
    quantidades_pedidas = {item.id: item.quantidade for item in pedido.itens}

    agora = _agora()
    for item in processo.itens:
        if item.sync_deleted_at is not None or item.data_fim is not None:
            continue
        if item.data_inicio is None:
            item.data_inicio = agora
        setattr(item, configuracao.campo_quantidade, quantidades_pedidas.get(item.pedido_item_id, 0))
        item.data_fim = agora
        incrementar_versao(item)

    processo.status = "finalizada"
    processo.data_fim = agora
    processo.usuario_fim_id = processo.usuario_inicio_id
    processo.usuario_gestor_fim_id = _gestor_ou_nulo(gestor_id, processo.usuario_inicio_id)
    incrementar_versao(processo)
    _gravar_status(sessao_db, processo.pedido_id, _STATUS_AO_FINALIZAR[tipo])
    _baixar_do_enderecamento(sessao_db, tipo, processo, pedido, liberar_enderecamento)

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


# ---------------------------------------------------------------------------
# Baixa no sistema de origem (ERP)
#
# A conferência fechar AQUI e o pedido fechar LÁ são duas coisas separadas, e é
# por isso que este passo é um clique próprio e não um efeito do último item
# bipado. Três motivos, todos concretos:
#
# 1. O ERP pede quatro números — volumes, espécie, peso líquido e peso bruto —
#    que só existem depois de a mercadoria estar embalada. Ninguém sabe o peso
#    bruto enquanto está bipando.
# 2. O Oracle é outro banco e outra transação. Ele pode estar fora do ar no
#    exato minuto em que o operador termina, e nesse caso o trabalho do galpão
#    não pode ser perdido nem repetido — fica conferido aqui, pendente lá, e o
#    botão continua disponível.
# 3. A ordem dos commits importa: primeiro o ERP, depois o nosso banco. Se
#    fosse ao contrário e o ERP recusasse, ficaria gravado aqui que o pedido
#    foi fechado lá — mentira que só apareceria no faturamento.
# ---------------------------------------------------------------------------

# Cabe em `expedicao_conferencias.motivo_falha_origem` (VARCHAR 255). Truncar é
# melhor do que estourar a coluna no meio do registro de uma falha — o texto
# inteiro continua indo para o operador na resposta HTTP.
_TAMANHO_MOTIVO_FALHA = 255


def _exigir_vinculo(valor: str | None, o_que: str) -> str:
    """O código no ERP de alguma das três pontas (empresa, pedido, usuário).

    Sem qualquer um deles não há como identificar o registro do outro lado, e
    seguir assim gravaria a baixa no pedido errado — por isso é 409 e não um
    valor padrão.
    """
    if not (valor or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{o_que} não tem vínculo com o sistema de origem, então não dá para "
                "identificar o registro lá. Finalize por dentro do ERP e avise o suporte."
            ),
        )
    return valor.strip()


def finalizar_no_sistema_origem(
    sessao_db: Session,
    pedido_id: str,
    usuario_id: str,
    dados: FinalizarNoSistemaOrigemSchema,
) -> ProcessoRespostaSchema:
    """Fecha no ERP o pedido cuja conferência já terminou aqui.

    Devolve a conferência atualizada — a mesma resposta do resto do domínio,
    para a tela do coletor só substituir o que tem em mão.
    """
    conferencia = _processo_vivo(sessao_db, "conferencia", pedido_id)
    if conferencia is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Este pedido não tem conferência aberta.",
        )
    if conferencia.status != "finalizada":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Termine a conferência antes de finalizar o pedido no sistema de origem.",
        )
    if conferencia.finalizado_origem_em is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este pedido já foi finalizado no sistema de origem.",
        )

    pedido = _obter_pedido(sessao_db, pedido_id)
    empresa_no_erp = _exigir_vinculo(
        empresa_publico.obter_sistema_origem_id(sessao_db, pedido.empresa_id),
        "A empresa do pedido",
    )
    pedido_no_erp = _exigir_vinculo(pedido.sistema_origem_id, "Este pedido")
    usuario_no_erp = usuario_publico.obter_sistema_origem_id(sessao_db, usuario_id)

    # Quem clicou e quando, gravado ANTES de falar com o ERP e nos dois
    # desfechos. O caso que isso resolve é uma recusa que só é explicável pela
    # conta que clicou (conta administrativa nossa não tem código no ERP) — e
    # sem estas duas colunas o motivo gravado não dizia de quem era a tentativa.
    conferencia.tentativa_origem_usuario_id = usuario_id
    conferencia.tentativa_origem_em = _agora()

    try:
        sistema_origem_publico.finalizar_pedido(
            empresa_sistema_origem_id=empresa_no_erp,
            pedido_sistema_origem_id=pedido_no_erp,
            usuario_sistema_origem_id=usuario_no_erp or "",
            volume=dados.volume,
            especie=dados.especie,
            peso_liquido=dados.peso_liquido,
            peso_bruto=dados.peso_bruto,
            # Só para a mensagem de recusa poder dizer DE QUAL conta está
            # falando — contas administrativas nossas não têm código no ERP, e
            # "seu usuário não tem vínculo" sem o login obriga a adivinhar.
            usuario_login=usuario_publico.obter_login(sessao_db, usuario_id) or "",
        )
    except HTTPException as recusa:
        # A recusa fica GRAVADA antes de subir. É o que responde, dias depois,
        # "por que este pedido está conferido aqui e aberto lá?" — sem isso a
        # única pista seria o operador lembrar da mensagem que viu na tela.
        conferencia.motivo_falha_origem = str(recusa.detail)[:_TAMANHO_MOTIVO_FALHA]
        incrementar_versao(conferencia)
        sessao_db.commit()
        raise

    # Só chega aqui com o COMMIT do Oracle já feito — ver o comentário do bloco
    # sobre a ordem dos commits.
    conferencia.finalizado_origem_em = _agora()
    conferencia.motivo_falha_origem = None
    incrementar_versao(conferencia)
    sessao_db.commit()
    sessao_db.refresh(conferencia)
    return _para_resposta_processo(sessao_db, "conferencia", conferencia, pedido)
