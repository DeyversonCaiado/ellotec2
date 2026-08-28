from datetime import date
from decimal import Decimal

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.entregas import entrega_service
from app.domains.entregas.entrega_contrato import (
    EntregaCriarSchema,
    EntregaNotaCriarSchema,
    EntregaNotaListaPaginadaSchema,
    EntregaNotaRespostaSchema,
    EntregaRespostaSchema,
    FiltrosListagemSchema,
    InteracaoAtualizarSchema,
    InteracaoCriarSchema,
    SugestoesFiltroSchema,
)
from app.shared.router_base import RouterBase

router = RouterBase(prefix="/entregas", tags=["Entregas"])


def _restricao_de_vendedor(ctx: ContextoRequisicao) -> str | None:
    """Devolve o id do usuário quando ele NÃO pode ver tudo.

    Sem `entregas.ver_todas`, o vendedor enxerga apenas as notas em que ele é o
    vendedor. A checagem é aqui e não no service porque é regra de acesso, não
    de negócio — e é feita no backend porque o front esconder a linha é só UX.
    """
    tem_ver_todas = any(p.chave == "entregas.ver_todas" for p in ctx.usuario.permissoes)
    return None if tem_ver_todas else ctx.usuario.id


# ---------------------------------------------------------------------------
# Integração (o ERP faz POST aqui; nada é lido do Oracle)
# ---------------------------------------------------------------------------


@router.post(
    "/mapas",
    response_model=EntregaRespostaSchema,
    status_code=200,
    summary="Registra ou atualiza um mapa de carga",
)
def registrar_mapa(
    dados: EntregaCriarSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("entregas.integrar")),
) -> EntregaRespostaSchema:
    """200 e não 201 de propósito: é upsert. O job de integração reprocessa o
    mesmo mapa, e responder 201 sugeriria que criou algo novo toda vez."""
    return EntregaRespostaSchema.model_validate(
        entrega_service.registrar_entrega(sessao_db, dados)
    )


@router.post(
    "/notas",
    response_model=EntregaNotaRespostaSchema,
    status_code=200,
    summary="Registra ou atualiza uma nota acompanhada, com os itens",
)
def registrar_nota(
    dados: EntregaNotaCriarSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("entregas.integrar")),
) -> EntregaNotaRespostaSchema:
    nota = entrega_service.registrar_nota(sessao_db, dados)
    return entrega_service.montar_resposta(sessao_db, nota)


# ---------------------------------------------------------------------------
# Tela
# ---------------------------------------------------------------------------


def _mes_atual() -> tuple[date, date]:
    """Período padrão da tela: do dia 1º até hoje, sobre a data da nota.

    Mesmo padrão da listagem da expedição. Sem ele, uma requisição sem período
    varreria a base inteira só para contar o rodapé — e "o que é deste mês?" é a
    pergunta que esta tela existe para responder.

    Fica no ROUTER e não no service de propósito: "sem data = sem filtro"
    continua sendo a regra do service, e o padrão é decisão da API. É o que
    permite um relatório futuro pedir a base toda sem lutar contra um mês que
    ele não escolheu.
    """
    hoje = date.today()
    return hoje.replace(day=1), hoje


# Um parâmetro por campo do painel, repetível (`?uf=GO&uf=DF`). É verboso, e é
# de propósito: o FastAPI sabe explodir um modelo Pydantic em query params
# (`Annotated[Schema, Query()]`), mas nesta versão isso só funciona quando o
# modelo é o ÚNICO parâmetro de query do endpoint — havendo qualquer outro
# (`page`, `sort`...), ele volta a exigir um parâmetro literal chamado
# "filtros" e a requisição da tela morre com 422. Testado, não suposto.
def _lista(alias: str, descricao: str):
    return Query(default=None, alias=alias, description=descricao)


@router.get(
    "", response_model=EntregaNotaListaPaginadaSchema, summary="Lista paginada de entregas"
)
def listar(
    page: int = 1,
    # Alias camelCase: o `RouterBase` só camelCasa a RESPOSTA, então o nome do
    # query param precisa ser declarado aqui para bater com o que o front manda.
    per_page: int = Query(default=20, alias="perPage"),
    sort: str = "data_nota",
    sort_type: str = Query(default="desc", alias="sortType"),
    q: str | None = Query(default=None, description="Nota, pedido, cliente, cidade ou transportadora"),
    # --- o painel de filtros: cada campo aceita vários valores ---
    empresa: list[str] | None = _lista("empresa", "Apelido da empresa emissora"),
    tipo_nota: list[str] | None = _lista("tipoNota", "venda, bonificacao, devolucao_cliente..."),
    pedido: list[str] | None = _lista("pedido", "Número do pedido"),
    numero_nota: list[str] | None = _lista("numeroNota", "Número da nota"),
    data_nota: list[date] | None = _lista("dataNota", "Dia da nota (não o período)"),
    cliente: list[str] | None = _lista("cliente", "Nome do cliente"),
    uf: list[str] | None = _lista("uf", "UF do cliente"),
    cidade: list[str] | None = _lista("cidade", "Cidade do cliente"),
    situacao: list[str] | None = _lista("situacao", "Situação da nota no ERP"),
    vendedor: list[str] | None = _lista("vendedor", "Nome do vendedor"),
    transportadora: list[str] | None = _lista("transportadora", "Transportadora da nota"),
    status: list[str] | None = _lista("status", "Status da entrega (slug)"),
    numero_mapa: list[str] | None = _lista("numeroMapa", "Número do mapa de carga"),
    data_mapa: list[date] | None = _lista("dataMapa", "Dia do mapa de carga"),
    nota_devolvida: list[str] | None = _lista(
        "notaDevolvida", "Número da nota que esta devolve (extraído da chave referenciada)"
    ),
    produto: list[str] | None = _lista("produto", "Notas que contêm este produto"),
    marca: list[str] | None = _lista("marca", "Notas que contêm esta marca"),
    lote: list[str] | None = _lista("lote", "Notas que contêm este lote"),
    quantidade: list[Decimal] | None = _lista("quantidade", "Notas com item nesta quantidade"),
    # --- fora do painel ---
    # As ABAS da tela (Em atraso, No prazo, Sem mapa...). Valor único, e por
    # isso não entra no painel: aba é escolha exclusiva, filtro é acumulativo.
    status_prazo: str | None = Query(default=None, alias="statusPrazo"),
    # Período pela DATA DA NOTA — data de negócio, nunca os campos sync_*.
    data_inicio: date | None = Query(default=None, alias="dataInicio"),
    data_fim: date | None = Query(default=None, alias="dataFim"),
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("entregas.acessar")),
) -> EntregaNotaListaPaginadaSchema:
    # Teto de 100 igual aos outros domínios: é a página que protege o navegador
    # e a API de uma listagem de centenas de milhares.
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    inicio_padrao, fim_padrao = _mes_atual()

    filtros = FiltrosListagemSchema(
        empresa=empresa or [],
        tipo_nota=tipo_nota or [],
        pedido=pedido or [],
        numero_nota=numero_nota or [],
        data_nota=data_nota or [],
        cliente=cliente or [],
        uf=uf or [],
        cidade=cidade or [],
        situacao=situacao or [],
        vendedor=vendedor or [],
        transportadora=transportadora or [],
        status=status or [],
        numero_mapa=numero_mapa or [],
        data_mapa=data_mapa or [],
        nota_devolvida=nota_devolvida or [],
        produto=produto or [],
        marca=marca or [],
        lote=lote or [],
        quantidade=quantidade or [],
    )

    items, total = entrega_service.listar_paginado(
        sessao_db,
        page,
        per_page,
        sort,
        sort_type,
        q=q,
        filtros=filtros,
        status_prazo=status_prazo,
        data_inicio=data_inicio or inicio_padrao,
        data_fim=data_fim or fim_padrao,
        apenas_vendedor_id=_restricao_de_vendedor(ctx),
    )
    return EntregaNotaListaPaginadaSchema(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.get(
    "/opcoes-filtros",
    response_model=SugestoesFiltroSchema,
    summary="Sugestões de um campo do painel de filtros",
)
def opcoes_filtros(
    campo: str = Query(description="Campo do painel: empresa, cliente, pedido, produto..."),
    termo: str | None = Query(default=None, description="O que a pessoa digitou"),
    data_inicio: date | None = Query(default=None, alias="dataInicio"),
    data_fim: date | None = Query(default=None, alias="dataFim"),
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("entregas.acessar")),
) -> SugestoesFiltroSchema:
    """Um endpoint só para os 19 campos: `campo` diz qual, `termo` recorta.

    Declarado ANTES de `/{nota_id}`: as rotas são resolvidas na ordem, e um
    path param no mesmo nível engoliria "opcoes-filtros" como se fosse um id.

    O padrão de período é o MESMO da listagem, e tem que continuar sendo: se as
    sugestões saíssem de um intervalo e a lista de outro, o autocomplete
    ofereceria um cliente que a listagem não traz — e a pessoa concluiria que o
    filtro está quebrado.
    """
    inicio_padrao, fim_padrao = _mes_atual()
    return entrega_service.sugestoes_de_campo(
        sessao_db,
        campo=campo,
        termo=termo,
        data_inicio=data_inicio or inicio_padrao,
        data_fim=data_fim or fim_padrao,
        apenas_vendedor_id=_restricao_de_vendedor(ctx),
    )


@router.get(
    "/{nota_id}",
    response_model=EntregaNotaRespostaSchema,
    summary="Detalhe da nota: capa, itens e a linha do tempo",
)
def obter(
    nota_id: str,
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("entregas.acessar")),
) -> EntregaNotaRespostaSchema:
    nota = entrega_service.obter_por_id(sessao_db, nota_id, _restricao_de_vendedor(ctx))
    # A restrição vai junto: a seção de notas de devolução também é listagem, e
    # sem isso ela mostraria, dentro do detalhe, uma nota que a lista esconde.
    return entrega_service.montar_resposta(
        sessao_db, nota, apenas_vendedor_id=_restricao_de_vendedor(ctx)
    )


@router.post(
    "/{nota_id}/interacoes",
    response_model=EntregaNotaRespostaSchema,
    status_code=201,
    summary="Registra uma interação na linha do tempo",
)
def registrar_interacao(
    nota_id: str,
    dados: InteracaoCriarSchema,
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("entregas.interacao.registrar")),
) -> EntregaNotaRespostaSchema:
    """Devolve a nota inteira, não só a interação: registrar muda o
    `statusAtual` e o `statusPrazo` da nota, e a tela precisa dos dois
    atualizados sem fazer um segundo request."""
    nota = entrega_service.registrar_interacao(
        sessao_db, nota_id, dados, ctx.usuario.id, _restricao_de_vendedor(ctx)
    )
    return entrega_service.montar_resposta(sessao_db, nota)


@router.put(
    "/{nota_id}/interacoes/{interacao_id}",
    response_model=EntregaNotaRespostaSchema,
    summary="Corrige uma interação já lançada",
)
def atualizar_interacao(
    nota_id: str,
    interacao_id: str,
    dados: InteracaoAtualizarSchema,
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("entregas.interacao.registrar")),
) -> EntregaNotaRespostaSchema:
    nota = entrega_service.atualizar_interacao(
        sessao_db, nota_id, interacao_id, dados, ctx.usuario.id, _restricao_de_vendedor(ctx)
    )
    return entrega_service.montar_resposta(sessao_db, nota)


@router.delete(
    "/{nota_id}/interacoes/{interacao_id}",
    response_model=EntregaNotaRespostaSchema,
    summary="Remove (soft delete) uma interação lançada errado",
)
def apagar_interacao(
    nota_id: str,
    interacao_id: str,
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("entregas.interacao.apagar")),
) -> EntregaNotaRespostaSchema:
    nota = entrega_service.apagar_interacao(
        sessao_db, nota_id, interacao_id, _restricao_de_vendedor(ctx)
    )
    return entrega_service.montar_resposta(sessao_db, nota)
