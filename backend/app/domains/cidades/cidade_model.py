from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin


class Cidade(Base, IdMixin, SyncMixin):
    __tablename__ = "cidades"

    codigo_municipio: Mapped[int] = mapped_column(Integer, nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    uf: Mapped[str] = mapped_column(String(2), nullable=False)
