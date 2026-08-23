"""cria cargos e vincula usuarios

Revision ID: 22c3528ed7ac
Revises: 87bf647af8f4
Create Date: 2026-08-17 12:52:34.044738

"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '22c3528ed7ac'
down_revision: Union[str, Sequence[str], None] = '87bf647af8f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GERENTE_ID = str(uuid.uuid4())
FUNCIONARIO_ID = str(uuid.uuid4())


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('cargos',
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('sync_created_at', sa.DateTime(), nullable=False),
    sa.Column('sync_updated_at', sa.DateTime(), nullable=False),
    sa.Column('sync_deleted_at', sa.DateTime(), nullable=True),
    sa.Column('sync_version', sa.Integer(), nullable=False),
    sa.Column('sync_synced_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cargos_nome'), 'cargos', ['nome'], unique=True)

    cargos_tabela = sa.table(
        'cargos',
        sa.column('id', sa.String),
        sa.column('nome', sa.String),
        sa.column('sync_created_at', sa.DateTime),
        sa.column('sync_updated_at', sa.DateTime),
        sa.column('sync_version', sa.Integer),
    )
    agora = datetime.now(timezone.utc)
    op.bulk_insert(cargos_tabela, [
        {
            'id': GERENTE_ID,
            'nome': 'Gerente',
            'sync_created_at': agora,
            'sync_updated_at': agora,
            'sync_version': 1,
        },
        {
            'id': FUNCIONARIO_ID,
            'nome': 'Funcionario',
            'sync_created_at': agora,
            'sync_updated_at': agora,
            'sync_version': 1,
        },
    ])

    op.add_column('usuarios', sa.Column('cargo_id', sa.String(length=36), nullable=True))
    op.execute(f"UPDATE usuarios SET cargo_id = '{FUNCIONARIO_ID}'")
    op.alter_column('usuarios', 'cargo_id', existing_type=sa.String(length=36), nullable=False)
    op.create_foreign_key(None, 'usuarios', 'cargos', ['cargo_id'], ['id'])
    op.drop_column('usuarios', 'cargo')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('usuarios', sa.Column('cargo', sa.String(length=100), nullable=False, server_default=''))
    op.drop_constraint(None, 'usuarios', type_='foreignkey')
    op.drop_column('usuarios', 'cargo_id')
    op.drop_index(op.f('ix_cargos_nome'), table_name='cargos')
    op.drop_table('cargos')
