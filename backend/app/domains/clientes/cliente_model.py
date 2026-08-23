from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.conexao import Base
from app.domains.cidades.cidade_model import Cidade
from app.shared.sync_mixin import IdMixin, SyncMixin


class Cliente(Base, IdMixin, SyncMixin):
    __tablename__ = "clientes"

    codigo: Mapped[str | None] = mapped_column(String(10), nullable=True, default=None)
    razao_social: Mapped[str] = mapped_column(String(200), nullable=False)
    nome_fantasia: Mapped[str] = mapped_column(String(150), nullable=False)
    cpf_cnpj: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    telefone: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    celular: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    logradouro: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    numero: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    complemento: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    bairro: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    cep: Mapped[str | None] = mapped_column(String(10), nullable=True, default=None)
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
    cidade_id: Mapped[str] = mapped_column(String(36), ForeignKey("cidades.id"), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    cidade: Mapped[Cidade] = relationship(lazy="joined")
