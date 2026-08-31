"""
Camada HTTP do domínio Cotações (Inteligência de Mercado).

Só há GET: o domínio é de consulta. E note o que NÃO aparece aqui — nenhum
`Depends(obter_sessao)`: estes endpoints não tocam o MySQL, leem o OuroWeb.
"""

from datetime import date, datetime

from fastapi import Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.core.auth.dependencies import exigir_permissao
from app.domains.cotacoes import cotacao_service
from app.domains.cotacoes.cotacao_contrato import (
    PER_PAGE_MAXIMO,
    CotacaoFiltroOpcoesSchema,
    CotacaoFiltrosSchema,
    CotacaoListaPaginadaSchema,
    SituacaoResposta,
)
from app.shared.router_base import RouterBase
from app.shared.sistema_origem.ouroweb.conexao import (
    OuroWebIndisponivel,
    OuroWebTempoEsgotado,
)

router = RouterBase(prefix="/cotacoes", tags=["Cotações"])


def _traduzir_indisponibilidade(erro: OuroWebIndisponivel) -> HTTPException:
    """Erro do sistema de origem vira status HTTP com significado.

    Nunca 500: o defeito não é nosso, e a pessoa na tela precisa saber a
    diferença entre "espere, o banco caiu" e "sua consulta foi grande demais,
    diminua o período" — que é a única das duas que ela consegue resolver.
    """
    if isinstance(erro, OuroWebTempoEsgotado):
        return HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(erro))
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Sistema de origem (OuroWeb) indisponível: {erro}",
    )


def _montar_filtros(
    data_inicio: date | None,
    data_fim: date | None,
    cotacao: int | None,
    q: str | None,
    hospital: str | None,
    cidade: str | None,
    estado: str | None,
    empresa_id: int | None,
    situacao: SituacaoResposta,
) -> CotacaoFiltrosSchema:
    """Valida os filtros e traduz erro de contrato para 422.

    O Pydantic levanta `ValueError` quando falta período E falta cotação; sem
    esta tradução o FastAPI devolveria 500 para o que é erro de quem chamou.
    """
    try:
        return CotacaoFiltrosSchema(
            data_inicio=data_inicio,
            data_fim=data_fim,
            cotacao=cotacao,
            termo=q,
            hospital=hospital,
            cidade=cidade,
            estado=estado,
            empresa_id=empresa_id,
            situacao=situacao,
        )
    except ValueError as erro:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Informe o período de vencimento ou o número da cotação.",
        ) from erro


@router.get(
    "",
    response_model=CotacaoListaPaginadaSchema,
    summary="Lista itens de cotação do Bionexo (somente leitura)",
)
def listar_cotacoes(
    data_inicio: date | None = Query(
        default=None, alias="dataInicio", description="Início do período de vencimento"
    ),
    data_fim: date | None = Query(
        default=None, alias="dataFim", description="Fim do período de vencimento"
    ),
    cotacao: int | None = Query(
        default=None,
        description="Número da cotação no Bionexo. Quando informado, o período é ignorado.",
    ),
    q: str | None = Query(default=None, description="Busca na descrição ou no código do produto"),
    hospital: str | None = Query(default=None),
    cidade: str | None = Query(default=None),
    estado: str | None = Query(default=None, max_length=2),
    empresa_id: int | None = Query(default=None, alias="empresaId"),
    situacao: SituacaoResposta = Query(default="todas"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=PER_PAGE_MAXIMO, alias="perPage"),
    sort: str = Query(default="dataVencimento"),
    sort_type: str = Query(default="desc", alias="sortType"),
    _: None = Depends(exigir_permissao("cotacoes.acessar")),
) -> CotacaoListaPaginadaSchema:
    filtros = _montar_filtros(
        data_inicio, data_fim, cotacao, q, hospital, cidade, estado, empresa_id, situacao
    )
    try:
        return cotacao_service.listar(filtros, page, per_page, sort, sort_type)
    except OuroWebIndisponivel as erro:
        raise _traduzir_indisponibilidade(erro) from erro


@router.get(
    "/exportar",
    summary="Exporta o resultado do filtro em CSV",
    response_class=StreamingResponse,
)
def exportar_cotacoes(
    data_inicio: date | None = Query(default=None, alias="dataInicio"),
    data_fim: date | None = Query(default=None, alias="dataFim"),
    cotacao: int | None = Query(default=None),
    q: str | None = Query(default=None),
    hospital: str | None = Query(default=None),
    cidade: str | None = Query(default=None),
    estado: str | None = Query(default=None, max_length=2),
    empresa_id: int | None = Query(default=None, alias="empresaId"),
    situacao: SituacaoResposta = Query(default="todas"),
    sort: str = Query(default="dataVencimento"),
    sort_type: str = Query(default="desc", alias="sortType"),
    _: None = Depends(exigir_permissao("cotacoes.acessar")),
) -> StreamingResponse:
    """Baixa TODAS as linhas do filtro, sem paginação, em CSV.

    A resposta é em streaming: o arquivo é gerado enquanto o banco é lido, e
    nunca fica inteiro na memória do worker. Medido com 98 mil linhas, montar
    tudo antes de responder chegava a 181 MB de pico — inaceitável num processo
    que atende todos os usuários.

    O limite de 90 dias vale aqui igual à tela; a busca por número de cotação
    dispensa a data, como na listagem.
    """
    filtros = _montar_filtros(
        data_inicio, data_fim, cotacao, q, hospital, cidade, estado, empresa_id, situacao
    )
    try:
        linhas = cotacao_service.exportar_csv(filtros, sort, sort_type)
    except OuroWebIndisponivel as erro:
        raise _traduzir_indisponibilidade(erro) from erro

    nome = f"cotacoes-{datetime.now().strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        linhas,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get(
    "/opcoes-filtro",
    response_model=CotacaoFiltroOpcoesSchema,
    summary="Estados e empresas para os filtros da tela",
)
def listar_opcoes_de_filtro(
    _: None = Depends(exigir_permissao("cotacoes.acessar")),
) -> CotacaoFiltroOpcoesSchema:
    try:
        return cotacao_service.listar_opcoes_de_filtro()
    except OuroWebIndisponivel as erro:
        raise _traduzir_indisponibilidade(erro) from erro
