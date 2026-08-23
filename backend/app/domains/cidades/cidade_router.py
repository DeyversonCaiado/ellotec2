from app.shared.router_base import RouterBase
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.cidades import cidade_service
from app.domains.cidades.cidade_model import Cidade
from app.domains.cidades.cidade_contrato import (
    CidadeAtualizarSchema,
    CidadeCriarSchema,
    CidadeListaPaginadaSchema,
    CidadeRespostaSchema,
)

router = RouterBase(prefix="/cidades", tags=["Cidades"])


def _para_resposta(cidade: Cidade) -> CidadeRespostaSchema:
    return CidadeRespostaSchema(
        id=cidade.id,
        codigo_municipio=cidade.codigo_municipio,
        nome=cidade.nome,
        uf=cidade.uf,
        criado_em=cidade.sync_created_at,
    )


@router.get("", response_model=CidadeListaPaginadaSchema, summary="Lista cidades")
def listar(
    page: int = 1,
    per_page: int = 20,
    sort: str = "nome",
    sort_type: str = "asc",
    busca: str | None = None,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("cidades.acessar")),
) -> CidadeListaPaginadaSchema:
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    itens, total = cidade_service.listar_paginado(sessao_db, page, per_page, sort, sort_type, busca)
    return CidadeListaPaginadaSchema(
        items=[_para_resposta(c) for c in itens],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.get("/{cidade_id}", response_model=CidadeRespostaSchema, summary="Obtém uma cidade pelo id")
def obter(
    cidade_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("cidades.acessar")),
) -> CidadeRespostaSchema:
    return _para_resposta(cidade_service.obter_por_id(sessao_db, cidade_id))


@router.post("", response_model=CidadeRespostaSchema, status_code=201, summary="Cria uma nova cidade")
def criar(
    dados: CidadeCriarSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("cidades.gravar.incluir")),
) -> CidadeRespostaSchema:
    return _para_resposta(cidade_service.criar(sessao_db, dados))


@router.put("/{cidade_id}", response_model=CidadeRespostaSchema, summary="Atualiza uma cidade existente")
def atualizar(
    cidade_id: str,
    dados: CidadeAtualizarSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("cidades.gravar.editar")),
) -> CidadeRespostaSchema:
    return _para_resposta(cidade_service.atualizar(sessao_db, cidade_id, dados))


@router.delete("/{cidade_id}", status_code=204, summary="Remove (soft delete) uma cidade")
def apagar(
    cidade_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("cidades.apagar")),
) -> None:
    cidade_service.apagar(sessao_db, cidade_id)
