from app.shared.router_base import RouterBase
from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.marcas import marca_service
from app.domains.marcas.marca_model import Marca
from app.domains.marcas.marca_contrato import (
    MarcaAtualizarSchema,
    MarcaCriarSchema,
    MarcaListaPaginadaSchema,
    MarcaRespostaSchema,
)

router = RouterBase(prefix="/marcas", tags=["Marcas"])


def _para_resposta(marca: Marca) -> MarcaRespostaSchema:
    return MarcaRespostaSchema(
        id=marca.id,
        nome=marca.nome,
        sistema_origem_id=marca.sistema_origem_id,
        ativo=marca.ativo,
        criado_em=marca.sync_created_at,
    )


@router.get("", response_model=MarcaListaPaginadaSchema, summary="Lista marcas")
def listar(
    page: int = 1,
    per_page: int = 20,
    sort: str = "nome",
    sort_type: str = "asc",
    q: str | None = Query(default=None, description="Termo de busca: nome"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("marcas.acessar")),
) -> MarcaListaPaginadaSchema:
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    itens, total = marca_service.listar_paginado(sessao_db, page, per_page, sort, sort_type, q)
    return MarcaListaPaginadaSchema(
        items=[_para_resposta(m) for m in itens],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.get("/{marca_id}", response_model=MarcaRespostaSchema, summary="Obtém uma marca pelo id")
def obter(
    marca_id: str,
    sistema_origem_id: str | None = Query(default=None, description="Se informado, busca a marca por esse campo em vez do id da URL"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("marcas.acessar")),
) -> MarcaRespostaSchema:
    marca = (
        marca_service.obter_por_sistema_origem_id(sessao_db, sistema_origem_id)
        if sistema_origem_id
        else marca_service.obter_por_id(sessao_db, marca_id)
    )
    return _para_resposta(marca)


@router.post("", response_model=MarcaRespostaSchema, status_code=201, summary="Cria uma nova marca")
def criar(
    dados: MarcaCriarSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("marcas.gravar.incluir")),
) -> MarcaRespostaSchema:
    return _para_resposta(marca_service.criar(sessao_db, dados))


@router.put("/{marca_id}", response_model=MarcaRespostaSchema, summary="Atualiza uma marca existente")
def atualizar(
    marca_id: str,
    dados: MarcaAtualizarSchema,
    sistema_origem_id: str | None = Query(default=None, description="Se informado, identifica a marca por esse campo em vez do id da URL"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("marcas.gravar.editar")),
) -> MarcaRespostaSchema:
    return _para_resposta(marca_service.atualizar(sessao_db, marca_id, dados, sistema_origem_id))


@router.delete("/{marca_id}", status_code=204, summary="Remove (soft delete) uma marca")
def apagar(
    marca_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("marcas.apagar")),
) -> None:
    marca_service.apagar(sessao_db, marca_id)
