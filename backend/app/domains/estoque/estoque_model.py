from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin

# Nenhum model de outro domínio é importado aqui: as FKs abaixo apontam pras
# tabelas de `produtos` e `empresas` só pelo nome, e é o banco quem recusa id
# inexistente (ver ARCHITECTURE.md → "Validação de id por foreign key").


class Estoque(Base, IdMixin, SyncMixin):
    """Saldo do produto na empresa — o total, sem abrir por lote nem endereço.

    É a resposta para "quanto tem?" numa consulta só. O detalhe de qual lote e
    de onde ele está guardado mora em `estoque_lotes` e em
    `estoque_endereco_lote` (domínio `enderecamento`), porque são perguntas
    diferentes e nem toda tela precisa das três.
    """

    __tablename__ = "estoque"
    __table_args__ = (
        # Um saldo por produto por empresa. Filial é dona do próprio estoque:
        # o mesmo produto tem saldo diferente em cada uma, e somá-los seria
        # mentira operacional (a mercadoria não está no galpão de quem separa).
        UniqueConstraint("empresa_id", "produto_id", name="uq_estoque_empresa_produto"),
    )

    produto_id: Mapped[str] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)
    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    # Numeric e não Integer: há produto vendido em quilo e em metro, e o saldo
    # deles é fracionado no ERP. Arredondar na entrada perderia mercadoria.
    quantidade: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=0)

    # Como o ERP chama esta linha e a empresa dela. Nullable porque o registro
    # também pode nascer aqui (ajuste manual), sem correspondente lá.
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    empresa_sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class EstoqueLote(Base, IdMixin, SyncMixin):
    """O saldo aberto por lote, com fabricação e vencimento.

    É esta tabela que dá identidade ao lote dentro do sistema: `estoque_lotes.id`
    é o que o domínio `enderecamento` referencia para dizer em que endereço
    aquele lote está guardado. Sem ela, o endereço teria que apontar para um
    par (produto, texto do lote) solto em cada tabela que precisasse dele.
    """

    __tablename__ = "estoque_lotes"
    __table_args__ = (
        # A chave natural do lote: empresa + produto + o texto do lote. O mesmo
        # número de lote se repete entre produtos diferentes (é do fabricante,
        # não nosso), então produto sozinho não identifica nada.
        UniqueConstraint("empresa_id", "produto_id", "lote", name="uq_estoque_lotes_empresa_produto_lote"),
    )

    produto_id: Mapped[str] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)
    lote: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    quantidade: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    # Datas de NEGÓCIO, nunca derivadas de sync_created_at: é delas que sai o
    # FEFO da separação e o bloqueio de mercadoria vencida.
    # Nullable porque produto sem controle de validade não tem nenhuma das duas.
    fabricacao: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    vencimento: Mapped[date | None] = mapped_column(Date, nullable=True, default=None, index=True)

    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    empresa_sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
