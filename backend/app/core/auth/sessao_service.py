from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.auth.sessao_model import Sessao
from app.core.auth.seguranca import gerar_refresh_token_bruto, hash_refresh_token
from app.core.settings import obter_settings

settings = obter_settings()


def criar_sessao(sessao_db: Session, usuario_id: str, dispositivo_id: str) -> tuple[Sessao, str]:
    """Cria uma nova sessão (refresh token) e retorna o registro + o token
    em texto puro (que só existe nesse momento — depois disso só o hash
    fica salvo)."""
    token_bruto = gerar_refresh_token_bruto()
    expira_em = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_dias)

    registro = Sessao(
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        refresh_token_hash=hash_refresh_token(token_bruto),
        expira_em=expira_em,
        ultimo_uso_em=datetime.now(timezone.utc),
    )
    sessao_db.add(registro)
    sessao_db.flush()
    return registro, token_bruto


def buscar_sessao_valida(sessao_db: Session, refresh_token_bruto: str) -> Sessao | None:
    token_hash = hash_refresh_token(refresh_token_bruto)
    registro = sessao_db.query(Sessao).filter(Sessao.refresh_token_hash == token_hash).first()

    if registro is None:
        return None
    if registro.revogada:
        return None
    if registro.sync_deleted_at is not None:
        return None

    # MySQL pode retornar datetime sem timezone (naive). Normaliza pra UTC
    # antes de comparar com datetime.now(timezone.utc) que é sempre aware.
    expira = registro.expira_em
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    if expira < datetime.now(timezone.utc):
        return None

    return registro


def revogar_sessao(sessao_db: Session, registro: Sessao) -> None:
    registro.revogada = True
    registro.revogada_em = datetime.now(timezone.utc)
    sessao_db.flush()


def revogar_todas_sessoes_do_usuario(sessao_db: Session, usuario_id: str) -> int:
    """Usado para 'sair de todos os dispositivos' / bloqueio de conta."""
    registros = (
        sessao_db.query(Sessao)
        .filter(Sessao.usuario_id == usuario_id, Sessao.revogada.is_(False))
        .all()
    )
    for registro in registros:
        registro.revogada = True
        registro.revogada_em = datetime.now(timezone.utc)
    sessao_db.flush()
    return len(registros)
