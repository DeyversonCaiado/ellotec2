"""add empresa_id to pedidos

Revision ID: c4d6e8f0a213
Revises: b3c5d7e9f102
Create Date: 2026-08-17 00:00:01.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4d6e8f0a213"
down_revision: Union[str, Sequence[str], None] = "b3c5d7e9f102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pedidos", sa.Column("empresa_id", sa.String(length=36), nullable=False))
    op.create_index(op.f("ix_pedidos_empresa_id"), "pedidos", ["empresa_id"], unique=False)
    op.create_foreign_key(
        "fk_pedidos_empresa_id_empresas", "pedidos", "empresas", ["empresa_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_pedidos_empresa_id_empresas", "pedidos", type_="foreignkey")
    op.drop_index(op.f("ix_pedidos_empresa_id"), table_name="pedidos")
    op.drop_column("pedidos", "empresa_id")
