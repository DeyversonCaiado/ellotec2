"""produto_codigo_barras (N códigos por produto) e renomeia codigo_barras para codigo_barra_notas

Revision ID: a1c4e7b90f26
Revises: f2a8c14d63b7
Create Date: 2026-08-21 00:00:00.000000

O produto passa a ter mais de um código de barras.

O campo que existia em `produtos` era um só porque no ERP (`fat_produtos.
CODIGO_BARRA`) é um só — e esse é o código que sai impresso na nota. Ele
continua existindo com o nome que sempre descreveu o papel dele:
`codigo_barra_notas`. `alter_column` com `new_column_name`, não drop + add: o
conteúdo da coluna é cadastro em uso, não pode ser perdido no caminho.

Os códigos que o coletor lê no galpão são outros e agora moram em
`produto_codigo_barras`, uma linha por código. O mesmo produto chega em caixa
de fabricante, de distribuidor e reembalada, cada uma com seu código — todas
precisam bipar, e um campo só obrigava a escolher qual valia.

O INSERT ... SELECT no fim copia cada `codigo_barra_notas` preenchido para a
tabela nova. Sem isso, todo produto que bipa hoje pelo código da nota
continuaria bipando (a busca olha os dois), mas o operador não veria esse
código na lista de logística do cadastro — e o primeiro que editasse o produto
gravaria a lista vazia por cima. Copiar deixa as duas visões coerentes desde o
primeiro dia.

`codigo` é indexado sem unique, pela mesma razão dos outros códigos de produto:
cadastro duplicado vindo de integração repete número, e recusar o segundo
quebraria a importação inteira por causa de uma linha.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1c4e7b90f26"
down_revision: Union[str, Sequence[str], None] = "f2a8c14d63b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f("ix_produtos_codigo_barras"), table_name="produtos")
    op.alter_column(
        "produtos",
        "codigo_barras",
        new_column_name="codigo_barra_notas",
        existing_type=sa.String(length=60),
        existing_nullable=True,
    )
    op.create_index(
        op.f("ix_produtos_codigo_barra_notas"), "produtos", ["codigo_barra_notas"], unique=False
    )

    op.create_table(
        "produto_codigo_barras",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("produto_id", sa.String(length=36), nullable=False),
        sa.Column("codigo", sa.String(length=60), nullable=False),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["produto_id"], ["produtos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_produto_codigo_barras_produto_id"),
        "produto_codigo_barras",
        ["produto_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_produto_codigo_barras_codigo"), "produto_codigo_barras", ["codigo"], unique=False
    )

    # UUID gerado pelo banco (a PK é UUID em string, ver IdMixin) para não
    # precisar trazer os produtos para o Python só para semear a tabela.
    op.execute(
        """
        insert into produto_codigo_barras
            (id, produto_id, codigo, sync_created_at, sync_updated_at, sync_version)
        select uuid(), p.id, p.codigo_barra_notas, now(), now(), 1
          from produtos p
         where p.codigo_barra_notas is not null
           and p.codigo_barra_notas <> ''
           and p.sync_deleted_at is null
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_produto_codigo_barras_codigo"), table_name="produto_codigo_barras")
    op.drop_index(op.f("ix_produto_codigo_barras_produto_id"), table_name="produto_codigo_barras")
    op.drop_table("produto_codigo_barras")

    op.drop_index(op.f("ix_produtos_codigo_barra_notas"), table_name="produtos")
    op.alter_column(
        "produtos",
        "codigo_barra_notas",
        new_column_name="codigo_barras",
        existing_type=sa.String(length=60),
        existing_nullable=True,
    )
    op.create_index(op.f("ix_produtos_codigo_barras"), "produtos", ["codigo_barras"], unique=False)
