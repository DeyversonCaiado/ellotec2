from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin


class Cargo(Base, IdMixin, SyncMixin):
    __tablename__ = "cargos"

    nome: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
