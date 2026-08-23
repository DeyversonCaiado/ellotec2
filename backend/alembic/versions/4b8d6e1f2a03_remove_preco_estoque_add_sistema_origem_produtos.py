"""remove preco_unitario/estoque and add sistema_origem_id to produtos

Revision ID: 4b8d6e1f2a03
Revises: 5842cb829e35
Create Date: 2026-08-13 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4b8d6e1f2a03"
down_revision: Union[str, Sequence[str], None] = "5842cb829e35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("produtos", sa.Column("sistema_origem_id", sa.String(length=100), nullable=True))
    op.drop_column("produtos", "preco_unitario")
    op.drop_column("produtos", "estoque")


def downgrade() -> None:
    op.add_column("produtos", sa.Column("estoque", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("produtos", sa.Column("preco_unitario", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.drop_column("produtos", "sistema_origem_id")
