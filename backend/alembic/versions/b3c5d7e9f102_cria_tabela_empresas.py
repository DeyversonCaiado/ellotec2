"""cria tabela empresas

Revision ID: b3c5d7e9f102
Revises: a2b4c6d8e0f1
Create Date: 2026-08-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3c5d7e9f102"
down_revision: Union[str, Sequence[str], None] = "a2b4c6d8e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "empresas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("codigo", sa.String(length=10), nullable=True),
        sa.Column("razao_social", sa.String(length=200), nullable=False),
        sa.Column("nome_fantasia", sa.String(length=150), nullable=False),
        sa.Column("cnpj", sa.String(length=18), nullable=False),
        sa.Column("sistema_origem_id", sa.String(length=100), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_empresas_cnpj"), "empresas", ["cnpj"], unique=False)
    op.create_index(op.f("ix_empresas_sistema_origem_id"), "empresas", ["sistema_origem_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_empresas_sistema_origem_id"), table_name="empresas")
    op.drop_index(op.f("ix_empresas_cnpj"), table_name="empresas")
    op.drop_table("empresas")
