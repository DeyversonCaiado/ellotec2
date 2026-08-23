from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin


class Marca(Base, IdMixin, SyncMixin):
    __tablename__ = "marcas"

    nome: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True, default=None)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
