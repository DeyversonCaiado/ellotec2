"""add vendedor_id to pedidos (FK usuarios.id)

Revision ID: c3e5a7f9b2d4
Revises: b2d4f6a8c1e3
Create Date: 2026-08-18 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3e5a7f9b2d4"
down_revision: Union[str, Sequence[str], None] = "b2d4f6a8c1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pedidos", sa.Column("vendedor_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_pedidos_vendedor_id"), "pedidos", ["vendedor_id"], unique=False)
    op.create_foreign_key(
        "fk_pedidos_vendedor_id_usuarios", "pedidos", "usuarios", ["vendedor_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_pedidos_vendedor_id_usuarios", "pedidos", type_="foreignkey")
    op.drop_index(op.f("ix_pedidos_vendedor_id"), table_name="pedidos")
    op.drop_column("pedidos", "vendedor_id")
