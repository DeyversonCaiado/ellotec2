from datetime import datetime, timezone

from app.shared.router_base import RouterBase
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import auth_service, sessao_service
from app.core.auth.auth_contrato import LoginPayload, LoginResponse, RefreshPayload, UsuarioLogadoSchema
from app.core.auth.dependencies import ContextoRequisicao, obter_usuario_atual
from app.core.auth.dispositivo_service import validar_dispositivo_da_requisicao
from app.core.auth.seguranca import gerar_access_token
from app.core.database.conexao import obter_sessao
from app.domains.usuarios.usuario_model import Usuario

router = RouterBase(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=LoginResponse, summary="Login com e-mail e senha")
def login(payload: LoginPayload, request: Request, sessao_db: Session = Depends(obter_sessao)) -> LoginResponse:
    """
    Requer o header `X-Device-Id` com um UUID estável gerado pelo cliente
    (gerado uma vez, persistido em localStorage, reenviado sempre). Sem
    esse header, a API responde 400 — não dá pra emitir uma sessão sem
    saber a qual dispositivo ela pertence.
    """
    identificador = payload.identificador()
    if not identificador:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Informe e-mail ou usuário.")
    return auth_service.autenticar(sessao_db, request, identificador, payload.senha)


@router.post("/refresh", response_model=LoginResponse, summary="Renova o access token usando o refresh token")
def renovar(payload: RefreshPayload, request: Request, sessao_db: Session = Depends(obter_sessao)) -> LoginResponse:
    registro_sessao = sessao_service.buscar_sessao_valida(sessao_db, payload.refresh_token)
    if registro_sessao is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido ou expirado.")

    # mesmo dispositivo físico precisa estar fazendo a renovação
    validar_dispositivo_da_requisicao(sessao_db, request, registro_sessao.dispositivo_id)

    usuario = (
        sessao_db.query(Usuario)
        .filter(Usuario.id == registro_sessao.usuario_id, Usuario.sync_deleted_at.is_(None))
        .first()
    )
    if usuario is None or not usuario.ativo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado ou inativo.")

    registro_sessao.ultimo_uso_em = datetime.now(timezone.utc)
    novo_access_token = gerar_access_token(usuario.id, registro_sessao.dispositivo_id)
    sessao_db.commit()

    return LoginResponse(
        token=novo_access_token,
        refresh_token=payload.refresh_token,
        usuario=UsuarioLogadoSchema(
            id=usuario.id,
            usuario=usuario.usuario,
            nome=usuario.nome,
            email=usuario.email,
            permissoes=[p.chave for p in usuario.permissoes],
        ),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoga a sessão atual (refresh token)")
def logout(payload: RefreshPayload, sessao_db: Session = Depends(obter_sessao)) -> None:
    registro_sessao = sessao_service.buscar_sessao_valida(sessao_db, payload.refresh_token)
    if registro_sessao is not None:
        sessao_service.revogar_sessao(sessao_db, registro_sessao)
        sessao_db.commit()


@router.get("/me", response_model=UsuarioLogadoSchema, summary="Dados do usuário autenticado")
def eu(ctx: ContextoRequisicao = Depends(obter_usuario_atual)) -> UsuarioLogadoSchema:
    return UsuarioLogadoSchema(
        id=ctx.usuario.id,
        usuario=ctx.usuario.usuario,
        nome=ctx.usuario.nome,
        email=ctx.usuario.email,
        permissoes=[p.chave for p in ctx.usuario.permissoes],
    )
