from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin


class Empresa(Base, IdMixin, SyncMixin):
    __tablename__ = "empresas"

    codigo: Mapped[str | None] = mapped_column(String(10), nullable=True, default=None)
    razao_social: Mapped[str] = mapped_column(String(200), nullable=False)
    nome_fantasia: Mapped[str] = mapped_column(String(150), nullable=False)
    # Nome curto pelo qual a empresa é chamada no dia a dia ("Matriz", "BSB").
    # Nullable porque o cadastro já existia sem ele e porque nem toda empresa
    # precisa de um — razão social e nome fantasia continuam sendo os nomes
    # oficiais, este é só o atalho.
    apelido: Mapped[str | None] = mapped_column(String(60), nullable=True, default=None)
    cnpj: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
