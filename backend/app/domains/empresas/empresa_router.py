from app.shared.router_base import RouterBase
from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.empresas import empresa_service
from app.domains.empresas.empresa_model import Empresa
from app.domains.empresas.empresa_contrato import (
    EmpresaAtualizarSchema,
    EmpresaCriarSchema,
    EmpresaListaPaginadaSchema,
    EmpresaRespostaSchema,
)

router = RouterBase(prefix="/empresas", tags=["Empresas"])


def _para_resposta(empresa: Empresa) -> EmpresaRespostaSchema:
    return EmpresaRespostaSchema(
        id=empresa.id,
        codigo=empresa.codigo,
        razao_social=empresa.razao_social,
        nome_fantasia=empresa.nome_fantasia,
        apelido=empresa.apelido,
        cnpj=empresa.cnpj,
        sistema_origem_id=empresa.sistema_origem_id,
        ativo=empresa.ativo,
        criado_em=empresa.sync_created_at,
    )


@router.get("", response_model=EmpresaListaPaginadaSchema, summary="Lista empresas")
def listar(
    page: int = 1,
    per_page: int = 20,
    sort: str = "razao_social",
    sort_type: str = "asc",
    q: str | None = Query(default=None, description="Termo de busca: razão social, fantasia ou CNPJ"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("empresas.acessar")),
) -> EmpresaListaPaginadaSchema:
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    itens, total = empresa_service.listar_paginado(sessao_db, page, per_page, sort, sort_type, q)
    return EmpresaListaPaginadaSchema(
        items=[_para_resposta(e) for e in itens],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.get("/{empresa_id}", response_model=EmpresaRespostaSchema, summary="Obtém uma empresa pelo id")
def obter(
    empresa_id: str,
    sistema_origem_id: str | None = Query(default=None, description="Se informado, busca a empresa por esse campo em vez do id da URL"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("empresas.acessar")),
) -> EmpresaRespostaSchema:
    empresa = (
        empresa_service.obter_por_sistema_origem_id(sessao_db, sistema_origem_id)
        if sistema_origem_id
        else empresa_service.obter_por_id(sessao_db, empresa_id)
    )
    return _para_resposta(empresa)


@router.post("", response_model=EmpresaRespostaSchema, status_code=201, summary="Cria uma nova empresa")
def criar(
    dados: EmpresaCriarSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("empresas.gravar.incluir")),
) -> EmpresaRespostaSchema:
    return _para_resposta(empresa_service.criar(sessao_db, dados))


@router.put("/{empresa_id}", response_model=EmpresaRespostaSchema, summary="Atualiza uma empresa existente")
def atualizar(
    empresa_id: str,
    dados: EmpresaAtualizarSchema,
    sistema_origem_id: str | None = Query(default=None, description="Se informado, identifica a empresa por esse campo em vez do id da URL"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("empresas.gravar.editar")),
) -> EmpresaRespostaSchema:
    return _para_resposta(empresa_service.atualizar(sessao_db, empresa_id, dados, sistema_origem_id))


@router.delete("/{empresa_id}", status_code=204, summary="Remove (soft delete) uma empresa")
def apagar(
    empresa_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("empresas.apagar")),
) -> None:
    empresa_service.apagar(sessao_db, empresa_id)
