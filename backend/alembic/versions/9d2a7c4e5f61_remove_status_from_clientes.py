"""remove status from clientes

Revision ID: 9d2a7c4e5f61
Revises: 4b8d6e1f2a03
Create Date: 2026-08-14 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d2a7c4e5f61"
down_revision: Union[str, Sequence[str], None] = "4b8d6e1f2a03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("clientes", "status")


def downgrade() -> None:
    op.add_column("clientes", sa.Column("status", sa.String(length=20), nullable=True))
