"""adiciona marca_id em produtos

Revision ID: c31705af2d49
Revises: f53221f8adb7
Create Date: 2026-08-17 16:25:42.408130

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c31705af2d49'
down_revision: Union[str, Sequence[str], None] = 'f53221f8adb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('produtos', sa.Column('marca_id', sa.String(length=36), nullable=False))
    op.create_index(op.f('ix_produtos_marca_id'), 'produtos', ['marca_id'], unique=False)
    op.create_foreign_key(None, 'produtos', 'marcas', ['marca_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(None, 'produtos', type_='foreignkey')
    op.drop_index(op.f('ix_produtos_marca_id'), table_name='produtos')
    op.drop_column('produtos', 'marca_id')
