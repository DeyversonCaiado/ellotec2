"""add sistema_origem_id to marcas

Revision ID: d1a2b3c4e5f6
Revises: c31705af2d49
Create Date: 2026-08-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1a2b3c4e5f6"
down_revision: Union[str, Sequence[str], None] = "c31705af2d49"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("marcas", sa.Column("sistema_origem_id", sa.String(length=100), nullable=True))
    op.create_index(
        op.f("ix_marcas_sistema_origem_id"), "marcas", ["sistema_origem_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_marcas_sistema_origem_id"), table_name="marcas")
    op.drop_column("marcas", "sistema_origem_id")
