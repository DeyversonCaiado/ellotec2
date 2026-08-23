"""Reconcile legacy orcamentos tables with pedidos.

Revision ID: 9f4a7d2c1b88
Revises: 7e4d1e2b9a55
"""

from alembic import op
import sqlalchemy as sa


revision = "9f4a7d2c1b88"
down_revision = "7e4d1e2b9a55"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    tables = _tables()
    if "pedidos" in tables and "orcamentos" in tables:
        raise RuntimeError("Migração interrompida: pedidos e orcamentos coexistem; reconcilie manualmente a fonte de dados.")

    if "orcamentos" in tables:
        op.rename_table("orcamentos", "pedidos")
        columns = _columns("pedidos")
        with op.batch_alter_table("pedidos") as batch:
            if "cliente_nome_fantasia" in columns:
                batch.drop_column("cliente_nome_fantasia")
            if "cliente_cnpj" in columns:
                batch.drop_column("cliente_cnpj")
    elif "pedidos" not in tables:
        # Instalação nova: não existe `orcamentos` legado pra renomear, então
        # `pedidos` precisa ser criada do zero. Sem este branch, a migração
        # seguia direto pra criação de `pedido_itens` (que tem FK pra
        # `pedidos.id`) sem a tabela existir.
        op.create_table(
            "pedidos",
            sa.Column("numero", sa.String(length=20), nullable=False),
            sa.Column("cliente_id", sa.String(length=36), nullable=False),
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

    if "pedidos" in _tables():
        indexes = _index_names("pedidos")
        if "ix_orcamentos_numero" in indexes:
            op.drop_index("ix_orcamentos_numero", table_name="pedidos")
        if "ix_orcamentos_cliente_id" in indexes:
            op.drop_index("ix_orcamentos_cliente_id", table_name="pedidos")
        indexes = _index_names("pedidos")
        if "ix_pedidos_numero" not in indexes:
            op.create_index("ix_pedidos_numero", "pedidos", ["numero"], unique=True)
        if "ix_pedidos_cliente_id" not in indexes:
            op.create_index("ix_pedidos_cliente_id", "pedidos", ["cliente_id"])

    tables = _tables()
    if "orcamento_itens" in tables and "pedido_itens" in tables:
        raise RuntimeError("Migração interrompida: pedido_itens e orcamento_itens coexistem.")
    if "orcamento_itens" in tables:
        op.rename_table("orcamento_itens", "pedido_itens")
        with op.batch_alter_table("pedido_itens") as batch:
            batch.alter_column("orcamento_id", new_column_name="pedido_id", existing_type=sa.String(length=36))

    if "pedido_itens" not in _tables():
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
    indexes = _index_names("pedido_itens")
    if "ix_pedido_itens_pedido_id" not in indexes:
        op.create_index("ix_pedido_itens_pedido_id", "pedido_itens", ["pedido_id"])
    if "ix_pedido_itens_produto_id" not in indexes:
        op.create_index("ix_pedido_itens_produto_id", "pedido_itens", ["produto_id"])

    if "usuario_permissoes" in _tables():
        op.execute(sa.text("UPDATE usuario_permissoes SET dominio = 'pedidos' WHERE dominio = 'orcamentos'"))


def downgrade() -> None:
    raise RuntimeError("A reconciliação pedidos/orcamentos não possui downgrade automático seguro.")
