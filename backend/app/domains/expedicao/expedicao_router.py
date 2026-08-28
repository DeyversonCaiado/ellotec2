from datetime import date

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.expedicao import expedicao_service
from app.domains.expedicao.expedicao_contrato import (
    AtribuirSchema,
    EmpresaFiltroSchema,
    BiparSchema,
    CredencialGerenteSchema,
    FinalizarItemSchema,
    OperadorSchema,
    PedidoExpedicaoDetalheSchema,
    PedidoExpedicaoListaPaginadaSchema,
    ProcessoRespostaSchema,
    TipoProcesso,
)
from app.shared.router_base import RouterBase

router = RouterBase(prefix="/expedicao", tags=["Expedição"])


def _exigir_execucao(ctx: ContextoRequisicao, tipo: TipoProcesso) -> None:
    """Separação e conferência são permissões distintas — um operador pode ter
    uma e não a outra. `exigir_permissao` não serve aqui porque a chave só é
    conhecida depois de ler o path param `tipo`, então a checagem acontece na
    primeira linha do endpoint. Continua sendo o backend barrando, que é o
    que importa (ver ARCHITECTURE.md → "Toda permissão é checada no backend").
    """
    chave = f"expedicao.{tipo}.executar"
    if not any(permissao.chave == chave for permissao in ctx.usuario.permissoes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permissão negada: requer '{chave}'.",
        )


def _pode_liberar_enderecamento(ctx: ContextoRequisicao) -> bool:
    """Se quem está chamando pode passar por cima da inconsistência de
    endereçamento. Não é `exigir_permissao` porque não barra ninguém: quem não
    tem a chave continua podendo delegar — só não atravessa o bloqueio."""
    return any(
        permissao.chave == "expedicao.enderecamento.liberar"
        for permissao in ctx.usuario.permissoes
    )


def _mes_atual() -> tuple[date, date]:
    """Período padrão da tela: do dia 1º até hoje, sobre a data do pedido. É o
    recorte que responde 'o que é deste mês?' sem o operador digitar nada."""
    hoje = date.today()
    return hoje.replace(day=1), hoje


@router.get(
    "/pedidos",
    response_model=PedidoExpedicaoListaPaginadaSchema,
    summary="Lista paginada de pedidos para a expedição",
)
def listar_pedidos(
    page: int = 1,
    # Alias camelCase: o `RouterBase` só camelCasa a RESPOSTA, então o nome do
    # query param precisa ser declarado aqui para bater com o que o front manda.
    per_page: int = Query(default=20, alias="perPage"),
    q: str | None = Query(default=None, description="Termo de busca: número do pedido ou cliente"),
    data_inicio: date | None = Query(
        default=None,
        alias="dataInicio",
        description="Início do período por data do pedido (padrão: dia 1º do mês)",
    ),
    data_fim: date | None = Query(
        default=None,
        alias="dataFim",
        description="Fim do período por data do pedido (padrão: hoje)",
    ),
    # Repetível: ?statusPedido=PED&statusPedido=separado. É a forma padrão de
    # lista em query string, e é o que o HttpParams do Angular gera.
    status_pedido: list[str] | None = Query(
        default=None,
        alias="statusPedido",
        description="Chaves do catálogo pedido_status. Vazio = todos os status.",
    ),
    empresa_id: str | None = Query(
        default=None, alias="empresaId", description="Filtra por empresa emissora do pedido"
    ),
    operador_id: str | None = Query(
        default=None,
        alias="operadorId",
        description="Filtra pedidos em que o usuário abriu a separação ou a conferência",
    ),
    situacao: str | None = Query(
        default=None,
        description=(
            "Situação no galpão: todos, nao_iniciados, em_separacao, "
            "aguardando_conferencia, em_conferencia, concluidos ou divergentes"
        ),
    ),
    sort: str = Query(
        default="sync_updated_at",
        description="numero, data_pedido, cliente_nome_fantasia, liberado_em ou sync_updated_at",
    ),
    sort_type: str = Query(default="desc", alias="sortType"),
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.acessar")),
) -> PedidoExpedicaoListaPaginadaSchema:
    """Todos os filtros são resolvidos no banco, na mesma consulta paginada.

    Nenhum deles filtra a página já carregada: com ~230 mil pedidos, o que a
    tela recebe é uma amostra, e recortar a amostra responde "não achei" para
    pedido que existe."""
    inicio_padrao, fim_padrao = _mes_atual()
    # Teto de 100 pelo mesmo motivo dos outros domínios: a página é o que
    # protege o navegador e o banco de uma listagem de centenas de milhares.
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    return expedicao_service.listar_pedidos(
        sessao_db,
        data_inicio=data_inicio or inicio_padrao,
        data_fim=data_fim or fim_padrao,
        termo=q,
        page=page,
        per_page=per_page,
        status_chaves=status_pedido,
        usuario_id=ctx.usuario.id,
        empresa_id=empresa_id,
        operador_id=operador_id,
        situacao=situacao,
        # Quem distribui trabalho vê a fila inteira; quem não distribui vê só
        # o que foi atribuído a ele. A decisão é do service, não da tela.
        ver_tudo=expedicao_service.pode_atribuir(ctx.usuario.permissoes),
        sort=sort,
        sort_type=sort_type,
    )


@router.get(
    "/status-pedido",
    response_model=list[str],
    summary="Chaves de status do ERP, para o filtro da listagem",
)
def listar_status_pedido(
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.acessar")),
) -> list[str]:
    """Espelha o catálogo de `pedidos` pela permissão da expedição. Sem isto a
    tela dependeria de `pedidos.acessar`, que o operador não tem."""
    return expedicao_service.listar_status_pedido(sessao_db)


@router.get(
    "/operadores",
    response_model=list[OperadorSchema],
    summary="Operadores da expedição (filtro da listagem)",
)
def listar_operadores_do_filtro(
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.acessar")),
) -> list[OperadorSchema]:
    """`expedicao.acessar` e não `expedicao.atribuir`: filtrar a própria lista
    não é distribuir trabalho. Quem só executa também procura pelo nome do
    colega para saber onde um pedido parou."""
    return expedicao_service.listar_operadores_do_filtro(sessao_db)


@router.get(
    "/empresas",
    response_model=list[EmpresaFiltroSchema],
    summary="Empresas do cadastro (filtro da listagem)",
)
def listar_empresas(
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.acessar")),
) -> list[EmpresaFiltroSchema]:
    """Espelha o cadastro de empresas pela permissão da expedição, como o
    catálogo de status. Sem isto a tela dependeria de `empresas.acessar`, que o
    operador de galpão não tem — e o 403 derrubaria ele da tela."""
    return expedicao_service.listar_empresas(sessao_db)


@router.get(
    "/operadores/{tipo}",
    response_model=list[OperadorSchema],
    summary="Operadores que podem executar a etapa (seletor de responsável)",
)
def listar_operadores(
    tipo: TipoProcesso,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.atribuir")),
) -> list[OperadorSchema]:
    return expedicao_service.listar_operadores(sessao_db, tipo)


@router.post(
    "/atribuicoes",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Define ou remove o responsável por uma etapa em vários pedidos",
)
def atribuir(
    dados: AtribuirSchema,
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.atribuir")),
) -> None:
    """`usuarioId` nulo remove o responsável — desatribuir é um valor deste
    campo, não um endpoint separado."""
    expedicao_service.atribuir(sessao_db, dados, atribuido_por_id=ctx.usuario.id)


@router.get(
    "/pedidos/{pedido_id}",
    response_model=PedidoExpedicaoDetalheSchema,
    summary="Detalhe do pedido com a situação de separação e conferência",
)
def obter_pedido(
    pedido_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.acessar")),
) -> PedidoExpedicaoDetalheSchema:
    return expedicao_service.obter_pedido(sessao_db, pedido_id)


@router.get(
    "/{tipo}/{processo_id}",
    response_model=ProcessoRespostaSchema,
    summary="Obtém uma separação/conferência com seus itens",
)
def obter_processo(
    tipo: TipoProcesso,
    processo_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.acessar")),
) -> ProcessoRespostaSchema:
    return expedicao_service.obter_processo(sessao_db, tipo, processo_id)


@router.post(
    "/{tipo}/pedidos/{pedido_id}/iniciar",
    response_model=ProcessoRespostaSchema,
    summary="Inicia ou continua a separação/conferência de um pedido",
)
def iniciar_processo(
    tipo: TipoProcesso,
    pedido_id: str,
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.acessar")),
) -> ProcessoRespostaSchema:
    _exigir_execucao(ctx, tipo)
    return expedicao_service.iniciar_processo(sessao_db, tipo, pedido_id, ctx.usuario.id)


@router.post(
    "/{tipo}/pedidos/{pedido_id}/iniciar-delegado",
    response_model=ProcessoRespostaSchema,
    summary="Inicia a etapa inteira em nome do operador atribuído",
)
def iniciar_delegado(
    tipo: TipoProcesso,
    pedido_id: str,
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.delegar")),
) -> ProcessoRespostaSchema:
    """Não chama `_exigir_execucao`: quem delega não executa a etapa, despacha
    alguém que executa. Exigir dele a permissão de separar obrigaria todo
    gerente a poder separar — o contrário do motivo de existir a delegação."""
    return expedicao_service.iniciar_delegado(
        sessao_db, tipo, pedido_id, ctx.usuario.id, _pode_liberar_enderecamento(ctx)
    )


@router.post(
    "/{tipo}/pedidos/{pedido_id}/finalizar-delegado",
    response_model=ProcessoRespostaSchema,
    summary="Finaliza a etapa inteira em nome do operador atribuído",
)
def finalizar_delegado(
    tipo: TipoProcesso,
    pedido_id: str,
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.delegar")),
) -> ProcessoRespostaSchema:
    """Pelo pedido, e não pelo id do processo: quem clica está olhando a tela do
    pedido, e um `GET` a mais só para descobrir o id do processo seria uma ida
    ao servidor sem informação nova."""
    return expedicao_service.finalizar_delegado(
        sessao_db, tipo, pedido_id, ctx.usuario.id, _pode_liberar_enderecamento(ctx)
    )


@router.post(
    "/{tipo}/{processo_id}/itens/{pedido_item_id}/iniciar",
    response_model=ProcessoRespostaSchema,
    summary="Marca o início do item (começa a contar o tempo gasto nele)",
)
def iniciar_item(
    tipo: TipoProcesso,
    processo_id: str,
    pedido_item_id: str,
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.acessar")),
) -> ProcessoRespostaSchema:
    _exigir_execucao(ctx, tipo)
    return expedicao_service.iniciar_item(sessao_db, tipo, processo_id, pedido_item_id, ctx.usuario.id)


@router.post(
    "/{tipo}/{processo_id}/itens/{pedido_item_id}/bipar",
    response_model=ProcessoRespostaSchema,
    summary="Registra uma leitura de código de barras no item",
)
def bipar(
    tipo: TipoProcesso,
    processo_id: str,
    pedido_item_id: str,
    dados: BiparSchema,
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.acessar")),
) -> ProcessoRespostaSchema:
    _exigir_execucao(ctx, tipo)
    return expedicao_service.bipar(
        sessao_db, tipo, processo_id, pedido_item_id, ctx.usuario.id, dados
    )


@router.post(
    "/{tipo}/{processo_id}/itens/{pedido_item_id}/finalizar",
    response_model=ProcessoRespostaSchema,
    summary="Finaliza o item; exige senha de gerente se faltou quantidade",
)
def finalizar_item(
    tipo: TipoProcesso,
    processo_id: str,
    pedido_item_id: str,
    dados: FinalizarItemSchema,
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.acessar")),
) -> ProcessoRespostaSchema:
    _exigir_execucao(ctx, tipo)
    return expedicao_service.finalizar_item(
        sessao_db, tipo, processo_id, pedido_item_id, ctx.usuario.id, dados
    )


@router.post(
    "/{tipo}/{processo_id}/resetar",
    status_code=204,
    summary="Reseta (soft delete) uma separação OU uma conferência",
)
def resetar(
    tipo: TipoProcesso,
    processo_id: str,
    dados: CredencialGerenteSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao.resetar")),
) -> None:
    expedicao_service.resetar(sessao_db, tipo, processo_id, dados)
