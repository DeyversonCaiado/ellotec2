"""add sistema_origem_id to clientes

Revision ID: 6a1f3d8c9e02
Revises: 9d2a7c4e5f61
Create Date: 2026-08-14 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6a1f3d8c9e02"
down_revision: Union[str, Sequence[str], None] = "9d2a7c4e5f61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clientes", sa.Column("sistema_origem_id", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("clientes", "sistema_origem_id")
