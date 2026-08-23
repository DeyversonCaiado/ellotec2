"""numero e sistema_origem_id de pedidos passam a ser únicos por empresa

Revision ID: b2d4f6a8c1e3
Revises: a7c9d2e1f3b4
Create Date: 2026-08-18 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2d4f6a8c1e3"
down_revision: Union[str, Sequence[str], None] = "a7c9d2e1f3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_pedidos_numero", table_name="pedidos")
    op.create_index("ix_pedidos_numero", "pedidos", ["numero"], unique=False)

    op.drop_index("ix_pedidos_sistema_origem_id", table_name="pedidos")
    op.create_index("ix_pedidos_sistema_origem_id", "pedidos", ["sistema_origem_id"], unique=False)

    op.create_unique_constraint("uq_pedidos_numero_empresa_id", "pedidos", ["numero", "empresa_id"])
    op.create_unique_constraint(
        "uq_pedidos_sistema_origem_id_empresa_id", "pedidos", ["sistema_origem_id", "empresa_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_pedidos_sistema_origem_id_empresa_id", "pedidos", type_="unique")
    op.drop_constraint("uq_pedidos_numero_empresa_id", "pedidos", type_="unique")

    op.drop_index("ix_pedidos_sistema_origem_id", table_name="pedidos")
    op.create_index("ix_pedidos_sistema_origem_id", "pedidos", ["sistema_origem_id"], unique=True)

    op.drop_index("ix_pedidos_numero", table_name="pedidos")
    op.create_index("ix_pedidos_numero", "pedidos", ["numero"], unique=True)
