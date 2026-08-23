"""moderniza pedido_status com FK real para pedidos

Revision ID: e64825c18550
Revises: 10dbd5fbbfbd
Create Date: 2026-08-17 14:08:47.672065

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e64825c18550'
down_revision: Union[str, Sequence[str], None] = '10dbd5fbbfbd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    A tabela legada `pedido_status` localizava o pedido por
    `(empresa_id, pedido)` em texto solto, sem FK. Ela é recriada do zero
    aqui, no padrão atual (UUID, SyncMixin, FK real pra `pedidos.id`),
    porque a mudança de PK (bigint -> varchar) e o remapeamento de chave
    não dá pra fazer com ALTER incremental. O único registro que existia
    era órfão (pedido "0182307" não existe em `pedidos`, que está vazia),
    então não há dado a preservar.
    """
    op.drop_table('pedido_status')
    op.create_table(
        'pedido_status',
        sa.Column('pedido_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('sync_created_at', sa.DateTime(), nullable=False),
        sa.Column('sync_updated_at', sa.DateTime(), nullable=False),
        sa.Column('sync_deleted_at', sa.DateTime(), nullable=True),
        sa.Column('sync_version', sa.Integer(), nullable=False),
        sa.Column('sync_synced_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['pedido_id'], ['pedidos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pedido_status_pedido_id'), 'pedido_status', ['pedido_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_pedido_status_pedido_id'), table_name='pedido_status')
    op.drop_table('pedido_status')
    op.create_table(
        'pedido_status',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('empresa_id', sa.String(length=20), nullable=False),
        sa.Column('pedido', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='PENDENTE'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('uk_pedido_status'), 'pedido_status', ['empresa_id', 'pedido'], unique=True)
