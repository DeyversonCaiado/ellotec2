"""add unique index to sistema_origem_id in clientes, produtos e pedidos

Revision ID: 3f6a9c2d8b71
Revises: 8e2c5b7d1f04
Create Date: 2026-08-14 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3f6a9c2d8b71"
down_revision: Union[str, Sequence[str], None] = "8e2c5b7d1f04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_clientes_sistema_origem_id"), "clientes", ["sistema_origem_id"], unique=True
    )
    op.create_index(
        op.f("ix_produtos_sistema_origem_id"), "produtos", ["sistema_origem_id"], unique=True
    )
    op.create_index(
        op.f("ix_pedidos_sistema_origem_id"), "pedidos", ["sistema_origem_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pedidos_sistema_origem_id"), table_name="pedidos")
    op.drop_index(op.f("ix_produtos_sistema_origem_id"), table_name="produtos")
    op.drop_index(op.f("ix_clientes_sistema_origem_id"), table_name="clientes")
