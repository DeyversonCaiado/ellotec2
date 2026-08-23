"""Snapshot do cliente no pedido (nome fantasia e CNPJ)

Devolve a `pedidos` as colunas de snapshot do cliente que a revisão
9f4a7d2c1b88 havia removido. Motivo: `pedidos` não importa mais nada de
`domains/clientes` — sem o relationship, o nome e o CNPJ precisam estar
gravados no próprio pedido. Além disso, um documento comercial não pode
mudar retroativamente porque o cadastro do cliente mudou depois da emissão.

Também cobre um banco onde `9f4a7d2c1b88` já está marcada como aplicada mas
`pedidos`/`pedido_itens` nunca chegaram a ser criadas (banco sem a tabela
legada `orcamentos` para renomear — a revisão tinha um bug para esse caso,
corrigido nela mesma, mas isso não re-executa numa base que já passou por
ela). Este upgrade cria as duas tabelas do zero quando faltarem.

O backfill preenche os pedidos já existentes com o valor ATUAL do cliente —
é a melhor aproximação disponível, já que o valor da época não foi guardado.

Revision ID: c7b2e1a4d903
Revises: a1f5c9d3e7b2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7b2e1a4d903"
down_revision: Union[str, Sequence[str], None] = "a1f5c9d3e7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tabelas() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _colunas(tabela: str) -> set[str]:
    return {coluna["name"] for coluna in sa.inspect(op.get_bind()).get_columns(tabela)}


def upgrade() -> None:
    tabelas = _tabelas()

    if "pedidos" not in tabelas:
        op.create_table(
            "pedidos",
            sa.Column("numero", sa.String(length=20), nullable=False),
            sa.Column("cliente_id", sa.String(length=36), nullable=False),
            sa.Column("cliente_nome_fantasia", sa.String(length=150), nullable=False, server_default=""),
            sa.Column("cliente_cnpj", sa.String(length=18), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("observacoes", sa.Text(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("sync_created_at", sa.DateTime(), nullable=False),
            sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
            sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
            sa.Column("sync_version", sa.Integer(), nullable=False),
            sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_pedidos_numero", "pedidos", ["numero"], unique=True)
        op.create_index("ix_pedidos_cliente_id", "pedidos", ["cliente_id"])
    else:
        colunas = _colunas("pedidos")
        if "cliente_nome_fantasia" not in colunas:
            op.add_column(
                "pedidos",
                sa.Column("cliente_nome_fantasia", sa.String(length=150), nullable=False, server_default=""),
            )
        if "cliente_cnpj" not in colunas:
            op.add_column(
                "pedidos",
                sa.Column("cliente_cnpj", sa.String(length=18), nullable=False, server_default=""),
            )

        # backfill a partir do cadastro atual de clientes, só quando a coluna
        # acabou de ser criada nesta execução (senão sobrescreveria snapshot
        # já gravado por um pedido criado depois da migração original).
        op.execute(
            sa.text(
                """
                UPDATE pedidos p
                JOIN clientes c ON c.id = p.cliente_id
                SET p.cliente_nome_fantasia = c.nome_fantasia,
                    p.cliente_cnpj = c.cnpj
                WHERE p.cliente_nome_fantasia = ''
                """
            )
        )

    if "pedido_itens" not in _tabelas():
        op.create_table(
            "pedido_itens",
            sa.Column("pedido_id", sa.String(length=36), nullable=False),
            sa.Column("produto_id", sa.String(length=36), nullable=False),
            sa.Column("produto_codigo", sa.String(length=40), nullable=False),
            sa.Column("produto_descricao", sa.String(length=255), nullable=False),
            sa.Column("quantidade", sa.Integer(), nullable=False),
            sa.Column("preco_unitario", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("sync_created_at", sa.DateTime(), nullable=False),
            sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
            sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
            sa.Column("sync_version", sa.Integer(), nullable=False),
            sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["pedido_id"], ["pedidos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["produto_id"], ["produtos.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_pedido_itens_pedido_id", "pedido_itens", ["pedido_id"])
        op.create_index("ix_pedido_itens_produto_id", "pedido_itens", ["produto_id"])


def downgrade() -> None:
    colunas = _colunas("pedidos") if "pedidos" in _tabelas() else set()
    with op.batch_alter_table("pedidos") as batch:
        if "cliente_cnpj" in colunas:
            batch.drop_column("cliente_cnpj")
        if "cliente_nome_fantasia" in colunas:
            batch.drop_column("cliente_nome_fantasia")
