"""add sistema_origem_id to usuarios

Revision ID: 7e4d1e2b9a55
Revises: 2c3d8f4a7c91
Create Date: 2026-08-10 16:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7e4d1e2b9a55"
down_revision: Union[str, Sequence[str], None] = "2c3d8f4a7c91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("sistema_origem_id", sa.String(length=100), nullable=True))
    op.create_index(
        op.f("ix_usuarios_sistema_origem_id"), "usuarios", ["sistema_origem_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_usuarios_sistema_origem_id"), table_name="usuarios")
    op.drop_column("usuarios", "sistema_origem_id")
