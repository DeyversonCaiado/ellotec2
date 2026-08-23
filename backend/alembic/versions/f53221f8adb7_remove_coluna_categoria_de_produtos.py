"""remove coluna categoria de produtos

Revision ID: f53221f8adb7
Revises: e64825c18550
Create Date: 2026-08-17 16:11:32.024866

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f53221f8adb7'
down_revision: Union[str, Sequence[str], None] = 'e64825c18550'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('produtos', 'categoria')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('produtos', sa.Column('categoria', sa.String(length=100), nullable=False, server_default=''))
