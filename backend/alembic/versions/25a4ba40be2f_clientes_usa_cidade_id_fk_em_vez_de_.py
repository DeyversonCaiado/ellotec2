"""clientes usa cidade_id fk em vez de cidade e uf

Revision ID: 25a4ba40be2f
Revises: c7b2e1a4d903
Create Date: 2026-08-13 22:06:54.369068

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '25a4ba40be2f'
down_revision: Union[str, Sequence[str], None] = 'c7b2e1a4d903'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nota: o autogenerate também detectou drift preexistente e não relacionado
    # (tipo de cidades.id, índices de usuarios) — removido manualmente desta
    # revisão para manter o escopo só na troca cidade/uf -> cidade_id em clientes.
    op.add_column('clientes', sa.Column('cidade_id', sa.String(length=36), nullable=False))
    op.create_foreign_key('fk_clientes_cidade_id_cidades', 'clientes', 'cidades', ['cidade_id'], ['id'])
    op.drop_column('clientes', 'uf')
    op.drop_column('clientes', 'cidade')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('clientes', sa.Column('cidade', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=False))
    op.add_column('clientes', sa.Column('uf', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=2), nullable=False))
    op.drop_constraint('fk_clientes_cidade_id_cidades', 'clientes', type_='foreignkey')
    op.drop_column('clientes', 'cidade_id')
