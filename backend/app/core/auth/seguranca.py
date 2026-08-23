import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.settings import obter_settings

settings = obter_settings()

_contexto_senha = CryptContext(schemes=["bcrypt"], deprecated="auto")


def gerar_hash_senha(senha_pura: str) -> str:
    return _contexto_senha.hash(senha_pura)


def verificar_senha(senha_pura: str, senha_hash: str) -> bool:
    return _contexto_senha.verify(senha_pura, senha_hash)


def gerar_access_token(usuario_id: str, dispositivo_id: str) -> str:
    """
    JWT de curta duração (default 30 min), nunca persistido — só
    verificado por assinatura. Carrega o dispositivo_id junto pra permitir
    checar, em cada request, que o token foi emitido pro dispositivo que
    está de fato fazendo a chamada (ver core/auth/dependencies.py).
    """
    agora = datetime.now(timezone.utc)
    payload = {
        "sub": usuario_id,
        "dispositivo_id": dispositivo_id,
        "tipo": "access",
        "iat": agora,
        "exp": agora + timedelta(minutes=settings.jwt_access_token_minutos),
    }
    return jwt.encode(payload, settings.jwt_segredo, algorithm=settings.jwt_algoritmo)


def decodificar_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, settings.jwt_segredo, algorithms=[settings.jwt_algoritmo])
    except JWTError:
        return None
    if payload.get("tipo") != "access":
        return None
    return payload


def gerar_refresh_token_bruto() -> str:
    """Refresh token é um valor aleatório opaco (não JWT) — não precisa
    carregar payload nenhum, só ser longo, aleatório e imprevisível."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token_bruto: str) -> str:
    """Guardamos só o hash no banco (mesma lógica de senha): se o banco
    vazar, ninguém ganha refresh tokens válidos de graça."""
    return hashlib.sha256(token_bruto.encode("utf-8")).hexdigest()
