from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin


class Sessao(Base, IdMixin, SyncMixin):
    """
    Uma sessão = um refresh token vivo, vinculado a um usuário E a um
    dispositivo específico. O access token (JWT de curta duração) nunca é
    persistido — só o refresh token tem estado no banco, porque é ele que
    precisa ser revogável (logout remoto, "sair de todos os dispositivos",
    bloqueio de conta).

    refresh_token_hash guarda um hash (não o token em texto puro) pelo
    mesmo motivo de nunca guardar senha em texto puro: se o banco vazar,
    o invasor não ganha tokens de sessão válidos de graça.
    """

    __tablename__ = "sessoes"

    usuario_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    dispositivo_id: Mapped[str] = mapped_column(
        ForeignKey("dispositivos.id", ondelete="CASCADE"), nullable=False, index=True
    )

    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revogada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revogada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    ultimo_uso_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    dispositivo: Mapped["Dispositivo"] = relationship(back_populates="sessoes")
