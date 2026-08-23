"""cria historico

Revision ID: e9b3c7a25f18
Revises: d7f2a4b81c50
Create Date: 2026-08-20 00:00:00.000000

Histórico de alterações rastreáveis feitas pelo sistema, inclusive as que
gravam em outro banco.

`tabela` é texto livre e não FK para nada de propósito: o primeiro caso de uso
é a correção de código de barras na bipagem, que altera `fat_produtos` no Oracle
do ERP — uma tabela que não existe neste banco.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e9b3c7a25f18"
down_revision: Union[str, Sequence[str], None] = "d7f2a4b81c50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "historico",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("empresa_id", sa.String(length=36), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("tabela", sa.String(length=100), nullable=False),
        sa.Column("campo", sa.String(length=100), nullable=False),
        sa.Column("valor_antigo", sa.Text(), nullable=True),
        sa.Column("valor_novo", sa.Text(), nullable=True),
        sa.Column("tela", sa.String(length=100), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("data_alteracao", sa.DateTime(), nullable=False),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_historico_empresa_id"), "historico", ["empresa_id"], unique=False)
    op.create_index(op.f("ix_historico_usuario_id"), "historico", ["usuario_id"], unique=False)
    op.create_index(op.f("ix_historico_tabela"), "historico", ["tabela"], unique=False)
    op.create_index(op.f("ix_historico_tela"), "historico", ["tela"], unique=False)
    op.create_index(
        op.f("ix_historico_data_alteracao"), "historico", ["data_alteracao"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_historico_data_alteracao"), table_name="historico")
    op.drop_index(op.f("ix_historico_tela"), table_name="historico")
    op.drop_index(op.f("ix_historico_tabela"), table_name="historico")
    op.drop_index(op.f("ix_historico_usuario_id"), table_name="historico")
    op.drop_index(op.f("ix_historico_empresa_id"), table_name="historico")
    op.drop_table("historico")
