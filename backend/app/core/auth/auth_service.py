from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth.auth_contrato import LoginResponse, UsuarioLogadoSchema
from app.core.auth.dispositivo_service import DeviceIdAusenteError, identificar_ou_registrar_dispositivo
from app.core.auth.seguranca import gerar_access_token, verificar_senha
from app.core.auth.sessao_service import criar_sessao
from app.domains.usuarios.usuario_model import Usuario


def autenticar(sessao_db: Session, request: Request, identificador: str, senha: str) -> LoginResponse:
    usuario = (
        sessao_db.query(Usuario)
        .filter(
            (Usuario.email == identificador) | (Usuario.usuario == identificador),
            Usuario.sync_deleted_at.is_(None),
        )
        .first()
    )

    credenciais_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail, usuário ou senha inválidos."
    )

    if usuario is None:
        raise credenciais_invalidas

    if not verificar_senha(senha, usuario.senha_hash):
        raise credenciais_invalidas

    if not usuario.ativo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuário inativo. Contate um administrador.")

    try:
        dispositivo = identificar_ou_registrar_dispositivo(sessao_db, request, usuario.id)
    except DeviceIdAusenteError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cabeçalho X-Device-Id ausente. O cliente deve enviar um identificador de dispositivo estável.",
        )

    _, refresh_token_bruto = criar_sessao(sessao_db, usuario.id, dispositivo.id)
    access_token = gerar_access_token(usuario.id, dispositivo.id)

    sessao_db.commit()
    sessao_db.refresh(usuario)

    return LoginResponse(
        token=access_token,
        refresh_token=refresh_token_bruto,
        usuario=UsuarioLogadoSchema(
            id=usuario.id,
            usuario=usuario.usuario,
            nome=usuario.nome,
            email=usuario.email,
            permissoes=[p.chave for p in usuario.permissoes],
        ),
    )
