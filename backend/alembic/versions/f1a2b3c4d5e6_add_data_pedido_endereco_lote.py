"""add data_pedido to pedidos and endereco_produto/lote to pedido_itens

Revision ID: f1a2b3c4d5e6
Revises: d5e7f9a1b324
Create Date: 2026-08-18 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "d5e7f9a1b324"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pedidos",
        sa.Column("data_pedido", sa.Date(), nullable=False, server_default=sa.text("(CURRENT_DATE)")),
    )
    op.alter_column("pedidos", "data_pedido", server_default=None)

    op.add_column("pedido_itens", sa.Column("endereco_produto", sa.String(length=100), nullable=True))
    op.add_column("pedido_itens", sa.Column("lote", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("pedido_itens", "lote")
    op.drop_column("pedido_itens", "endereco_produto")
    op.drop_column("pedidos", "data_pedido")
