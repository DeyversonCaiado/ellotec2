"""cpf_cnpj deixa de ser unico em clientes

Revision ID: 5c1e8f3a9d02
Revises: 3f6a9c2d8b71
Create Date: 2026-08-15 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5c1e8f3a9d02"
down_revision: Union[str, Sequence[str], None] = "3f6a9c2d8b71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f("ix_clientes_cpf_cnpj"), table_name="clientes")
    op.create_index(op.f("ix_clientes_cpf_cnpj"), "clientes", ["cpf_cnpj"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_clientes_cpf_cnpj"), table_name="clientes")
    op.create_index(op.f("ix_clientes_cpf_cnpj"), "clientes", ["cpf_cnpj"], unique=True)
