from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.conexao import Base
from app.domains.usuarios.cargo_model import Cargo
from app.shared.sync_mixin import IdMixin, SyncMixin


class Usuario(Base, IdMixin, SyncMixin):
    __tablename__ = "usuarios"

    usuario: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(180), nullable=False, unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    cargo_id: Mapped[str] = mapped_column(String(36), ForeignKey("cargos.id"), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    cargo: Mapped[Cargo] = relationship(lazy="joined")
    permissoes: Mapped[list["UsuarioPermissao"]] = relationship(
        back_populates="usuario",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class UsuarioPermissao(Base, IdMixin, SyncMixin):
    """
    Uma linha por (usuario, chave de permissão) marcada. Normalizado em vez
    de guardar um JSON dentro de `usuarios` — assim dá pra indexar, filtrar
    ("quem tem 'pedidos.gravar.editar'?") e auditar sem parsear JSON.
    `chave` é uma string opaca do catálogo `PERMISSOES_VALIDAS`
    (`core/permissions/permission_model.py`), não mais um par
    (dominio, ação) fixo de CRUD.
    """

    __tablename__ = "usuario_permissoes"
    __table_args__ = (UniqueConstraint("usuario_id", "chave", name="uq_usuario_chave"),)

    usuario_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    chave: Mapped[str] = mapped_column(String(100), nullable=False)

    usuario: Mapped["Usuario"] = relationship(back_populates="permissoes")
