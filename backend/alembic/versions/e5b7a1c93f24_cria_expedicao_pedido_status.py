"""cria expedicao_pedido_status

Revision ID: e5b7a1c93f24
Revises: d4a6f8c02b19
Create Date: 2026-08-19 00:00:00.000000

Onde a expedição grava em que ponto do galpão cada pedido está. Uma linha por
pedido (daí o unique em pedido_id), apontando para o mesmo catálogo
`pedido_status` que o pedido usa — o vocabulário de status é um só.

Não grava em `pedidos.status_id` de propósito: aquele campo é da integração, e
um PUT do ERP no mesmo pedido apagaria o andamento da separação/conferência.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5b7a1c93f24"
down_revision: Union[str, Sequence[str], None] = "d4a6f8c02b19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expedicao_pedido_status",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pedido_id", sa.String(length=36), nullable=False),
        sa.Column("status_id", sa.String(length=36), nullable=False),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["pedido_id"], ["pedidos.id"]),
        sa.ForeignKeyConstraint(["status_id"], ["pedido_status.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_expedicao_pedido_status_pedido_id"),
        "expedicao_pedido_status",
        ["pedido_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_expedicao_pedido_status_status_id"),
        "expedicao_pedido_status",
        ["status_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_expedicao_pedido_status_status_id"), table_name="expedicao_pedido_status")
    op.drop_index(op.f("ix_expedicao_pedido_status_pedido_id"), table_name="expedicao_pedido_status")
    op.drop_table("expedicao_pedido_status")
