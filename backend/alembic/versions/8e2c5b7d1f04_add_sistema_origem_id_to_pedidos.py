"""add sistema_origem_id to pedidos

Revision ID: 8e2c5b7d1f04
Revises: 6a1f3d8c9e02
Create Date: 2026-08-14 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8e2c5b7d1f04"
down_revision: Union[str, Sequence[str], None] = "6a1f3d8c9e02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pedidos", sa.Column("sistema_origem_id", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("pedidos", "sistema_origem_id")
