from app.shared.router_base import RouterBase
from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao, obter_usuario_atual
from app.core.database.conexao import obter_sessao
from app.domains.usuarios import usuario_service
from app.domains.usuarios.usuario_model import Usuario
from app.domains.usuarios.usuario_contrato import (
    UsuarioAtualizarSchema,
    UsuarioCriarSchema,
    UsuarioListaPaginadaSchema,
    UsuarioRespostaSchema,
    UsuarioResumoSchema,
)

router = RouterBase(prefix="/usuarios", tags=["Usuários"])


@router.get(
    "/vendedores",
    response_model=list[UsuarioResumoSchema],
    summary="Lista usuários ativos (id + nome) — canal leve pra outros domínios (ex: vendedor de pedido)",
)
def listar_vendedores(
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(obter_usuario_atual),
) -> list[UsuarioResumoSchema]:
    return [
        UsuarioResumoSchema(id=u.id, nome=u.nome) for u in usuario_service.listar_resumo(sessao_db)
    ]


def _para_resposta(usuario: Usuario) -> UsuarioRespostaSchema:
    return UsuarioRespostaSchema(
        id=usuario.id,
        usuario=usuario.usuario,
        sistema_origem_id=usuario.sistema_origem_id,
        nome=usuario.nome,
        email=usuario.email,
        cargo_id=usuario.cargo_id,
        cargo_nome=usuario.cargo.nome,
        ativo=usuario.ativo,
        permissoes=[p.chave for p in usuario.permissoes],
        criado_em=usuario.sync_created_at,
    )


@router.get("", response_model=UsuarioListaPaginadaSchema, summary="Lista usuários")
def listar(
    page: int = 1,
    per_page: int = 20,
    sort: str = "sync_created_at",
    sort_type: str = "desc",
    busca: str | None = None,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("usuarios.acessar")),
) -> UsuarioListaPaginadaSchema:
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    itens, total = usuario_service.listar_paginado(sessao_db, page, per_page, sort, sort_type, busca)
    return UsuarioListaPaginadaSchema(
        items=[_para_resposta(u) for u in itens],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.get("/{usuario_id}", response_model=UsuarioRespostaSchema, summary="Obtém um usuário pelo id")
def obter(
    usuario_id: str,
    sistema_origem_id: str | None = Query(default=None, description="Se informado, busca o usuário por esse campo em vez do id da URL"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("usuarios.acessar")),
) -> UsuarioRespostaSchema:
    usuario = (
        usuario_service.obter_por_sistema_origem_id(sessao_db, sistema_origem_id)
        if sistema_origem_id
        else usuario_service.obter_por_id(sessao_db, usuario_id)
    )
    return _para_resposta(usuario)


@router.post("", response_model=UsuarioRespostaSchema, status_code=201, summary="Cria um novo usuário")
def criar(
    dados: UsuarioCriarSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("usuarios.gravar.incluir")),
) -> UsuarioRespostaSchema:
    return _para_resposta(usuario_service.criar(sessao_db, dados))


@router.put("/{usuario_id}", response_model=UsuarioRespostaSchema, summary="Atualiza um usuário existente")
def atualizar(
    usuario_id: str,
    dados: UsuarioAtualizarSchema,
    sistema_origem_id: str | None = Query(default=None, description="Se informado, identifica o usuário por esse campo em vez do id da URL"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("usuarios.gravar.editar")),
) -> UsuarioRespostaSchema:
    return _para_resposta(usuario_service.atualizar(sessao_db, usuario_id, dados, sistema_origem_id))


@router.delete("/{usuario_id}", status_code=204, summary="Remove (soft delete) um usuário")
def apagar(
    usuario_id: str,
    sessao_db: Session = Depends(obter_sessao),
    ctx: ContextoRequisicao = Depends(exigir_permissao("usuarios.apagar")),
) -> None:
    usuario_service.apagar(sessao_db, usuario_id, usuario_solicitante_id=ctx.usuario.id)
