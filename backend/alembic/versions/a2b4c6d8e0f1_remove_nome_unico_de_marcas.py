"""remove restricao de nome unico em marcas

Revision ID: a2b4c6d8e0f1
Revises: d1a2b3c4e5f6
Create Date: 2026-08-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a2b4c6d8e0f1"
down_revision: Union[str, Sequence[str], None] = "d1a2b3c4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f("ix_marcas_nome"), table_name="marcas")
    op.create_index(op.f("ix_marcas_nome"), "marcas", ["nome"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_marcas_nome"), table_name="marcas")
    op.create_index(op.f("ix_marcas_nome"), "marcas", ["nome"], unique=True)
