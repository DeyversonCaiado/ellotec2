from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin


class Pedido(Base, IdMixin, SyncMixin):
    __tablename__ = "pedidos"
    __table_args__ = (
        # numero e sistema_origem_id não são mais únicos globalmente — são
        # únicos POR EMPRESA. Faz sentido porque cada empresa/filial numera
        # (e integra com sistemas externos) de forma independente; o mesmo
        # "PED-00001" pode existir em duas empresas diferentes sem colidir.
        UniqueConstraint("numero", "empresa_id", name="uq_pedidos_numero_empresa_id"),
        UniqueConstraint(
            "sistema_origem_id", "empresa_id", name="uq_pedidos_sistema_origem_id_empresa_id"
        ),
        # A listagem da expedição filtra por data do pedido e ordena por data de
        # alteração. Declarados aqui, e não como `index=True` na coluna, porque
        # sync_updated_at vem do SyncMixin — indexá-lo lá criaria o índice em
        # toda tabela do sistema, e só esta precisa.
        Index("ix_pedidos_data_pedido", "data_pedido"),
        Index("ix_pedidos_sync_updated_at", "sync_updated_at"),
    )

    # Sem índice próprio: `uq_pedidos_numero_empresa_id` já começa por `numero`,
    # e o MySQL usa o prefixo à esquerda de um índice composto. O mesmo vale
    # para sistema_origem_id abaixo. Os índices avulsos que existiam custavam
    # ~64 MB sem servir a nenhuma consulta que o composto não sirva.
    numero: Mapped[str] = mapped_column(String(20), nullable=False)
    data_pedido: Mapped[date] = mapped_column(Date, nullable=False)
    # Quando o pedido foi liberado (ex: análise de crédito aprovada no ERP).
    # É um MILESTONE, não auditoria: marca o instante em que o pedido passou a
    # existir para o armazém, e é a partir dele que se mede o ciclo da
    # expedição. Nulo = ainda não liberado, que é informação legítima.
    #
    # Chega pela integração (`liberacaoDataHora` do ERP). Não é escrito por
    # nenhuma tela daqui — quem libera é o financeiro, do lado de lá.
    liberado_em: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)

    # cliente_id é FK real (o banco recusa id inexistente), mas o nome e o CNPJ
    # são SNAPSHOT: cópia do que o cliente era no momento da emissão. Não existe
    # relationship() aqui de propósito — pedidos não importa nada de
    # domains/clientes, e um pedido antigo não pode mudar porque o cadastro do
    # cliente mudou depois.
    cliente_id: Mapped[str] = mapped_column(ForeignKey("clientes.id"), nullable=False, index=True)
    cliente_nome_fantasia: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    cliente_cnpj: Mapped[str] = mapped_column(String(18), nullable=False, default="")

    # empresa_id é FK real (cadastro vivo, não snapshot) — identifica de qual
    # empresa/filial o pedido é. Diferente de cliente_id acima, não tem
    # colunas de snapshot porque a empresa do pedido não é um dado que se
    # imprime numa nota fiscal antiga; é só um vínculo organizacional.
    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)

    # Vendedor é o usuário responsável pelo pedido — vínculo vivo (não
    # snapshot) com domains/usuarios, resolvido via usuario_publico.py
    # (ver "Regras de import entre domínios" no ARCHITECTURE.md do backend).
    vendedor_id: Mapped[str | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)

    # Ver comentário em `numero`: coberto por uq_pedidos_sistema_origem_id_empresa_id.
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Só existe UM status por pedido — é o próprio pedido que aponta pro
    # catálogo (status_id -> pedido_status.id), não o contrário. A tabela
    # pedido_status é um catálogo fixo (rascunho/enviado/aprovado/recusado),
    # não uma linha por pedido.
    status_id: Mapped[str] = mapped_column(ForeignKey("pedido_status.id"), nullable=False, index=True)
    observacoes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    itens: Mapped[list["PedidoItem"]] = relationship(
        back_populates="pedido",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PedidoItem.sync_created_at",
    )
    status: Mapped["PedidoStatus"] = relationship(lazy="joined")


class PedidoItem(Base, IdMixin, SyncMixin):
    __tablename__ = "pedido_itens"

    pedido_id: Mapped[str] = mapped_column(
        ForeignKey("pedidos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produto_id: Mapped[str] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)

    produto_codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    produto_descricao: Mapped[str] = mapped_column(String(255), nullable=False)

    quantidade: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    preco_unitario: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    # Disponíveis apenas via API — não exibidos nem editáveis no front hoje.
    endereco_produto: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lote: Mapped[str | None] = mapped_column(String(100), nullable=True)

    pedido: Mapped["Pedido"] = relationship(back_populates="itens")


class PedidoStatus(Base, IdMixin, SyncMixin):
    """
    Catálogo fixo dos status possíveis de um pedido (rascunho, enviado,
    aprovado, recusado — ver StatusPedido em pedido_contrato.py). É o
    pedido que referencia uma linha daqui (Pedido.status_id), nunca o
    contrário: um pedido tem exatamente um status, então não faz sentido
    a tabela de status guardar um pedido_id apontando de volta.

    Antes era uma tabela legada que localizava o pedido por
    `(empresa_id, pedido)` em texto solto, e depois virou (por engano) uma
    tabela 1:1 com `pedido_id`, que nunca chegou a ser usada por nenhum
    service — o texto do status ficava direto em `Pedido.status`,
    divergindo dessa tabela. Esta é a correção: uma tabela só, um dono só.
    """

    __tablename__ = "pedido_status"

    chave: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
