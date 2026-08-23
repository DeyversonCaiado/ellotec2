"""cria expedicao_atribuicoes

Revision ID: d7f2a4b81c50
Revises: f6c8b3d150ea
Create Date: 2026-08-20 00:00:00.000000

Quem é o responsável por cada etapa (separação/conferência) de um pedido.

A chave lógica é `(pedido_id, tipo)` e não `pedido_id`: o caso normal do galpão
é uma pessoa separar e outra conferir o mesmo pedido.

Não tem UniqueConstraint em `(pedido_id, tipo)` de propósito. A tabela usa soft
delete (SyncMixin), então linhas apagadas continuariam ocupando a chave, e o
MySQL não tem índice único parcial para excluí-las. Quem garante um responsável
vivo por etapa é `expedicao_service.atribuir`, que apaga a atribuição anterior
antes de gravar a nova. O índice composto abaixo não é único — existe para a
consulta de listagem, que filtra a fila inteira por responsável.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7f2a4b81c50"
down_revision: Union[str, Sequence[str], None] = "f6c8b3d150ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expedicao_atribuicoes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pedido_id", sa.String(length=36), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("atribuido_por_id", sa.String(length=36), nullable=False),
        sa.Column("data_atribuicao", sa.DateTime(), nullable=False),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["pedido_id"], ["pedidos.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["atribuido_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_expedicao_atribuicoes_pedido_id"),
        "expedicao_atribuicoes",
        ["pedido_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_expedicao_atribuicoes_tipo"), "expedicao_atribuicoes", ["tipo"], unique=False
    )
    op.create_index(
        op.f("ix_expedicao_atribuicoes_usuario_id"),
        "expedicao_atribuicoes",
        ["usuario_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_expedicao_atribuicoes_atribuido_por_id"),
        "expedicao_atribuicoes",
        ["atribuido_por_id"],
        unique=False,
    )
    # Índice da pergunta que a listagem faz a cada página do operador comum:
    # "quais pedidos estão atribuídos a mim e ainda valem?". Sem ele, filtrar a
    # fila por responsável varre a tabela inteira.
    op.create_index(
        "ix_expedicao_atribuicoes_usuario_vivas",
        "expedicao_atribuicoes",
        ["usuario_id", "sync_deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_expedicao_atribuicoes_usuario_vivas", table_name="expedicao_atribuicoes")
    op.drop_index(
        op.f("ix_expedicao_atribuicoes_atribuido_por_id"), table_name="expedicao_atribuicoes"
    )
    op.drop_index(op.f("ix_expedicao_atribuicoes_usuario_id"), table_name="expedicao_atribuicoes")
    op.drop_index(op.f("ix_expedicao_atribuicoes_tipo"), table_name="expedicao_atribuicoes")
    op.drop_index(op.f("ix_expedicao_atribuicoes_pedido_id"), table_name="expedicao_atribuicoes")
    op.drop_table("expedicao_atribuicoes")
