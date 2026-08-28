from datetime import date

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.notas_fiscais import nota_fiscal_service
from app.domains.notas_fiscais.nota_fiscal_contrato import (
    NotaFiscalAtualizarSchema,
    NotaFiscalCriarSchema,
    NotaFiscalListaPaginadaSchema,
    NotaFiscalRespostaSchema,
    NotaFiscalResumoSchema,
    NotaFiscalXmlSchema,
)
from app.shared.router_base import RouterBase

router = RouterBase(prefix="/notas-fiscais", tags=["Notas Fiscais"])


@router.get("", response_model=NotaFiscalListaPaginadaSchema, summary="Lista paginada de notas fiscais")
def listar(
    page: int = 1,
    # Alias camelCase: o `RouterBase` só camelCasa a RESPOSTA, então o nome do
    # query param precisa ser declarado aqui para bater com o que o front manda.
    # Sem isso o parâmetro é silenciosamente ignorado e vale sempre o default.
    per_page: int = Query(default=20, alias="perPage"),
    sort: str = "data_emissao",
    sort_type: str = Query(default="desc", alias="sortType"),
    q: str | None = Query(default=None, description="Busca por número, chave, CNPJ ou razão social"),
    # É este parâmetro que separa os dois itens do menu ("Notas Entradas" e
    # "Notas Saídas"): mesma tela, mesma rota, filtro diferente.
    tipo_operacao: str | None = Query(default=None, alias="tipoOperacao", pattern="^(entrada|saida)$"),
    empresa_id: str | None = Query(default=None, alias="empresaId"),
    empresa_sistema_origem_id: str | None = Query(default=None, alias="empresaSistemaOrigemId"),
    modelo: str | None = Query(default=None, description="55, 65, 57, NFSE"),
    status_nota: str | None = Query(default=None, alias="status"),
    # Período de EMISSÃO — a data de negócio do documento, nunca os campos de
    # auditoria/sincronização.
    data_inicio: date | None = Query(default=None, alias="dataInicio"),
    data_fim: date | None = Query(default=None, alias="dataFim"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("notas_fiscais.acessar")),
) -> NotaFiscalListaPaginadaSchema:
    # Teto de 100 igual aos outros domínios: é a página que protege o navegador
    # e a API de uma listagem de centenas de milhares.
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    notas, total = nota_fiscal_service.listar_paginado(
        sessao_db,
        page,
        per_page,
        sort,
        sort_type,
        q=q,
        tipo_operacao=tipo_operacao,
        empresa_id=nota_fiscal_service.resolver_empresa(
            sessao_db, empresa_id, empresa_sistema_origem_id
        ),
        modelo=modelo,
        status_nota=status_nota,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    return NotaFiscalListaPaginadaSchema(
        items=[NotaFiscalResumoSchema.model_validate(nota) for nota in notas],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.get("/{nota_id}", response_model=NotaFiscalRespostaSchema, summary="Obtém uma nota fiscal pelo id")
def obter(
    nota_id: str,
    chave_acesso: str | None = Query(
        default=None,
        alias="chaveAcesso",
        description="Se informada, busca a nota por esse campo em vez do id da URL",
    ),
    # O par (chave, empresa) é que identifica uma nota nesta tabela — a mesma
    # chave pode estar guardada por duas filiais. No PUT a empresa vem no
    # corpo; aqui, que não tem corpo, ela precisa vir na query string.
    empresa_id: str | None = Query(default=None, alias="empresaId"),
    empresa_sistema_origem_id: str | None = Query(default=None, alias="empresaSistemaOrigemId"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("notas_fiscais.acessar")),
) -> NotaFiscalRespostaSchema:
    if chave_acesso:
        nota = nota_fiscal_service.obter_por_chave_acesso(
            sessao_db,
            chave_acesso,
            nota_fiscal_service.resolver_empresa(sessao_db, empresa_id, empresa_sistema_origem_id),
        )
    else:
        nota = nota_fiscal_service.obter_por_id(sessao_db, nota_id)
    return NotaFiscalRespostaSchema.model_validate(nota)


@router.get("/{nota_id}/xml", response_model=NotaFiscalXmlSchema, summary="Devolve o XML original da nota")
def obter_xml(
    nota_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("notas_fiscais.acessar")),
) -> NotaFiscalXmlSchema:
    """Rota separada de propósito: o XML tem dezenas de KB e nenhuma tela
    exibe o conteúdo dele. Quem precisa é quem vai baixar o arquivo ou
    reprocessar o documento — e aí pede explicitamente."""
    return NotaFiscalXmlSchema.model_validate(nota_fiscal_service.obter_com_xml(sessao_db, nota_id))


@router.post("", response_model=NotaFiscalRespostaSchema, status_code=201, summary="Registra uma nota fiscal")
def criar(
    dados: NotaFiscalCriarSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("notas_fiscais.gravar.incluir")),
) -> NotaFiscalRespostaSchema:
    return NotaFiscalRespostaSchema.model_validate(nota_fiscal_service.criar(sessao_db, dados))


@router.put("/{nota_id}", response_model=NotaFiscalRespostaSchema, summary="Atualiza uma nota fiscal existente")
def atualizar(
    nota_id: str,
    dados: NotaFiscalAtualizarSchema,
    chave_acesso: str | None = Query(
        default=None,
        alias="chaveAcesso",
        description="Se informada, identifica a nota por esse campo em vez do id da URL",
    ),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("notas_fiscais.gravar.editar")),
) -> NotaFiscalRespostaSchema:
    return NotaFiscalRespostaSchema.model_validate(
        nota_fiscal_service.atualizar(sessao_db, nota_id, dados, chave_acesso)
    )


@router.delete("/{nota_id}", status_code=204, summary="Remove (soft delete) uma nota fiscal")
def apagar(
    nota_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("notas_fiscais.apagar")),
) -> None:
    nota_fiscal_service.apagar(sessao_db, nota_id)
