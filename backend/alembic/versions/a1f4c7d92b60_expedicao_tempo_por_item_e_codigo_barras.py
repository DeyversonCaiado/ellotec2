"""expedicao: tempo por item, divergencia e codigo de barras em produtos

Revision ID: a1f4c7d92b60
Revises: c3e5a7f9b2d4
Create Date: 2026-08-18 00:00:00.000000

Três mudanças, todas exigidas pelo fluxo de separação/conferência no coletor:

1. `data_inicio`/`data_fim` nos ITENS dos dois processos — a capa já tinha
   as datas, mas o que se quer medir é o tempo gasto POR ITEM.
2. `divergente` em separação (conferência já tinha) + `usuario_autorizador_id`
   nos dois — finalizar item com quantidade abaixo da pedida exige senha de
   gerente, e quem liberou precisa ficar rastreável.
3. `codigo_barras` em produtos — é por ele que a bipagem no coletor
   identifica o item.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1f4c7d92b60"
down_revision: Union[str, Sequence[str], None] = "c3e5a7f9b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABELAS_ITEM = ("expedicao_separacao_itens", "expedicao_conferencia_itens")


def upgrade() -> None:
    for tabela in _TABELAS_ITEM:
        op.add_column(tabela, sa.Column("data_inicio", sa.DateTime(), nullable=True))
        op.add_column(tabela, sa.Column("data_fim", sa.DateTime(), nullable=True))
        op.add_column(
            tabela, sa.Column("usuario_autorizador_id", sa.String(length=36), nullable=True)
        )
        op.create_index(
            op.f(f"ix_{tabela}_usuario_autorizador_id"),
            tabela,
            ["usuario_autorizador_id"],
            unique=False,
        )
        op.create_foreign_key(
            f"fk_{tabela}_usuario_autorizador_id_usuarios",
            tabela,
            "usuarios",
            ["usuario_autorizador_id"],
            ["id"],
        )

    # `divergente` só existia em conferência — agora as duas etapas fecham
    # item divergente do mesmo jeito.
    op.add_column(
        "expedicao_separacao_itens",
        sa.Column("divergente", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("expedicao_separacao_itens", "divergente", server_default=None)

    op.add_column("produtos", sa.Column("codigo_barras", sa.String(length=60), nullable=True))
    op.create_index(op.f("ix_produtos_codigo_barras"), "produtos", ["codigo_barras"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_produtos_codigo_barras"), table_name="produtos")
    op.drop_column("produtos", "codigo_barras")

    op.drop_column("expedicao_separacao_itens", "divergente")

    for tabela in _TABELAS_ITEM:
        op.drop_constraint(
            f"fk_{tabela}_usuario_autorizador_id_usuarios", tabela, type_="foreignkey"
        )
        op.drop_index(op.f(f"ix_{tabela}_usuario_autorizador_id"), table_name=tabela)
        op.drop_column(tabela, "usuario_autorizador_id")
        op.drop_column(tabela, "data_fim")
        op.drop_column(tabela, "data_inicio")
