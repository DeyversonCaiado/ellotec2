from app.shared.router_base import RouterBase
from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.clientes import cliente_service
from app.domains.clientes.cliente_model import Cliente
from app.domains.clientes.cliente_contrato import (
    ClienteAtualizarSchema,
    ClienteCriarSchema,
    ClienteListaPaginadaSchema,
    ClienteRespostaSchema,
)

router = RouterBase(prefix="/clientes", tags=["Clientes"])


def _para_resposta(cliente: Cliente) -> ClienteRespostaSchema:
    return ClienteRespostaSchema(
        id=cliente.id,
        codigo=cliente.codigo,
        razao_social=cliente.razao_social,
        nome_fantasia=cliente.nome_fantasia,
        cpf_cnpj=cliente.cpf_cnpj,
        email=cliente.email,
        telefone=cliente.telefone,
        celular=cliente.celular,
        logradouro=cliente.logradouro,
        numero=cliente.numero,
        complemento=cliente.complemento,
        bairro=cliente.bairro,
        cep=cliente.cep,
        sistema_origem_id=cliente.sistema_origem_id,
        cidade_id=cliente.cidade_id,
        cidade_nome=cliente.cidade.nome,
        cidade_uf=cliente.cidade.uf,
        ativo=cliente.ativo,
        criado_em=cliente.sync_created_at,
    )


@router.get("", response_model=ClienteListaPaginadaSchema, summary="Lista clientes")
def listar(
    page: int = 1,
    per_page: int = 20,
    sort: str = "nome_fantasia",
    sort_type: str = "asc",
    q: str | None = Query(default=None, description="Termo de busca: razão social, fantasia ou CPF/CNPJ"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("clientes.acessar")),
) -> ClienteListaPaginadaSchema:
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    itens, total = cliente_service.listar_paginado(sessao_db, page, per_page, sort, sort_type, q)
    return ClienteListaPaginadaSchema(
        items=[_para_resposta(c) for c in itens],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.get("/{cliente_id}", response_model=ClienteRespostaSchema, summary="Obtém um cliente pelo id")
def obter(
    cliente_id: str,
    sistema_origem_id: str | None = Query(default=None, description="Se informado, busca o cliente por esse campo em vez do id da URL"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("clientes.acessar")),
) -> ClienteRespostaSchema:
    cliente = (
        cliente_service.obter_por_sistema_origem_id(sessao_db, sistema_origem_id)
        if sistema_origem_id
        else cliente_service.obter_por_id(sessao_db, cliente_id)
    )
    return _para_resposta(cliente)


@router.post("", response_model=ClienteRespostaSchema, status_code=201, summary="Cria um novo cliente")
def criar(
    dados: ClienteCriarSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("clientes.gravar.incluir")),
) -> ClienteRespostaSchema:
    return _para_resposta(cliente_service.criar(sessao_db, dados))


@router.put("/{cliente_id}", response_model=ClienteRespostaSchema, summary="Atualiza um cliente existente")
def atualizar(
    cliente_id: str,
    dados: ClienteAtualizarSchema,
    sistema_origem_id: str | None = Query(default=None, description="Se informado, identifica o cliente por esse campo em vez do id da URL"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("clientes.gravar.editar")),
) -> ClienteRespostaSchema:
    return _para_resposta(cliente_service.atualizar(sessao_db, cliente_id, dados, sistema_origem_id))


@router.delete("/{cliente_id}", status_code=204, summary="Remove (soft delete) um cliente")
def apagar(
    cliente_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("clientes.apagar")),
) -> None:
    cliente_service.apagar(sessao_db, cliente_id)
