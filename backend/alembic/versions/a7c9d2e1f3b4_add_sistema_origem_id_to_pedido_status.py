"""add sistema_origem_id to pedido_status

Revision ID: a7c9d2e1f3b4
Revises: f1a2b3c4d5e6
Create Date: 2026-08-18 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7c9d2e1f3b4"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pedido_status", sa.Column("sistema_origem_id", sa.String(length=100), nullable=True))
    op.create_index(
        op.f("ix_pedido_status_sistema_origem_id"), "pedido_status", ["sistema_origem_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pedido_status_sistema_origem_id"), table_name="pedido_status")
    op.drop_column("pedido_status", "sistema_origem_id")
