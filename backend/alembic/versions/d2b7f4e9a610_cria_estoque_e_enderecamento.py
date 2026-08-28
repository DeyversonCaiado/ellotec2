"""estoque e endereçamento: saldo, lote, endereço e o vínculo entre eles

Revision ID: d2b7f4e9a610
Revises: c9e4a71f5b38
Create Date: 2026-08-26 00:00:00.000000

Cria as quatro tabelas dos dois domínios novos:

- `estoque`               — saldo do produto por empresa (domínio `estoque`)
- `estoque_lotes`         — o mesmo saldo aberto por lote, com fabricação e
                            vencimento (domínio `estoque`)
- `estoque_enderecos`     — os lugares do galpão (domínio `enderecamento`)
- `estoque_endereco_lote` — onde cada lote está guardado (domínio
                            `enderecamento`)

E remove `pedido_itens.endereco_produto`, que é o motivo de tudo isto existir.
Aquela coluna misturava dois assuntos: o que o cliente comprou (pedido) e onde a
mercadoria está guardada (estoque). Endereço é do estoque, e a relação com o
lote é muitos-para-muitos de verdade — um lote se espalha por vários endereços.
Espremer isso num campo só foi o que fez a consulta da integração devolver uma
linha de pedido por endereço, cada uma com a quantidade INTEIRA (ver a revisão
c9e4a71f5b38, que limpou as 90 linhas duplicadas).

A partir daqui a expedição chega no endereço partindo do par (produto, lote) da
linha do pedido: `estoque_lotes` dá identidade ao lote e `estoque_endereco_lote`
diz em quais endereços ele está.

`downgrade()` recria a coluna vazia. O conteúdo dela não volta — e não deve: o
que estava lá era um endereço por linha, quando a realidade eram vários.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2b7f4e9a610"
down_revision: Union[str, Sequence[str], None] = "c9e4a71f5b38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _colunas_sync() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    # ---------------------------------------------------------------- estoque
    op.create_table(
        "estoque",
        *_colunas_sync(),
        sa.Column("produto_id", sa.String(length=36), nullable=False),
        sa.Column("empresa_id", sa.String(length=36), nullable=False),
        # Numeric e não Integer: há produto vendido em quilo e em metro.
        sa.Column("quantidade", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("sistema_origem_id", sa.String(length=100), nullable=True),
        sa.Column("empresa_sistema_origem_id", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["produto_id"], ["produtos.id"]),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "produto_id", name="uq_estoque_empresa_produto"),
    )
    op.create_index(op.f("ix_estoque_produto_id"), "estoque", ["produto_id"])
    op.create_index(op.f("ix_estoque_empresa_id"), "estoque", ["empresa_id"])
    op.create_index(op.f("ix_estoque_sistema_origem_id"), "estoque", ["sistema_origem_id"])

    # ---------------------------------------------------------- estoque_lotes
    op.create_table(
        "estoque_lotes",
        *_colunas_sync(),
        sa.Column("produto_id", sa.String(length=36), nullable=False),
        sa.Column("lote", sa.String(length=100), nullable=False),
        sa.Column("quantidade", sa.Numeric(precision=14, scale=3), nullable=False),
        # Datas de NEGÓCIO: é delas que sai o FEFO e o bloqueio de vencido.
        sa.Column("fabricacao", sa.Date(), nullable=True),
        sa.Column("vencimento", sa.Date(), nullable=True),
        sa.Column("empresa_id", sa.String(length=36), nullable=False),
        sa.Column("sistema_origem_id", sa.String(length=100), nullable=True),
        sa.Column("empresa_sistema_origem_id", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["produto_id"], ["produtos.id"]),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "empresa_id", "produto_id", "lote", name="uq_estoque_lotes_empresa_produto_lote"
        ),
    )
    op.create_index(op.f("ix_estoque_lotes_produto_id"), "estoque_lotes", ["produto_id"])
    op.create_index(op.f("ix_estoque_lotes_lote"), "estoque_lotes", ["lote"])
    op.create_index(op.f("ix_estoque_lotes_vencimento"), "estoque_lotes", ["vencimento"])
    op.create_index(op.f("ix_estoque_lotes_empresa_id"), "estoque_lotes", ["empresa_id"])
    op.create_index(
        op.f("ix_estoque_lotes_sistema_origem_id"), "estoque_lotes", ["sistema_origem_id"]
    )

    # ------------------------------------------------------ estoque_enderecos
    op.create_table(
        "estoque_enderecos",
        *_colunas_sync(),
        sa.Column("descricao", sa.String(length=100), nullable=False),
        sa.Column("empresa_id", sa.String(length=36), nullable=False),
        sa.Column("sistema_origem_id", sa.String(length=100), nullable=True),
        sa.Column("empresa_sistema_origem_id", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "empresa_id", "descricao", name="uq_estoque_enderecos_empresa_descricao"
        ),
    )
    op.create_index(op.f("ix_estoque_enderecos_empresa_id"), "estoque_enderecos", ["empresa_id"])
    op.create_index(
        op.f("ix_estoque_enderecos_sistema_origem_id"), "estoque_enderecos", ["sistema_origem_id"]
    )

    # --------------------------------------------------- estoque_endereco_lote
    op.create_table(
        "estoque_endereco_lote",
        *_colunas_sync(),
        sa.Column("estoque_enderecos_id", sa.String(length=36), nullable=False),
        sa.Column("estoque_lotes_id", sa.String(length=36), nullable=False),
        sa.Column("empresa_id", sa.String(length=36), nullable=False),
        sa.Column("sistema_origem_id", sa.String(length=100), nullable=True),
        sa.Column("empresa_sistema_origem_id", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["estoque_enderecos_id"], ["estoque_enderecos.id"]),
        sa.ForeignKeyConstraint(["estoque_lotes_id"], ["estoque_lotes.id"]),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "estoque_enderecos_id",
            "estoque_lotes_id",
            name="uq_estoque_endereco_lote_endereco_lote",
        ),
    )
    op.create_index(
        op.f("ix_estoque_endereco_lote_estoque_enderecos_id"),
        "estoque_endereco_lote",
        ["estoque_enderecos_id"],
    )
    op.create_index(
        op.f("ix_estoque_endereco_lote_estoque_lotes_id"),
        "estoque_endereco_lote",
        ["estoque_lotes_id"],
    )
    op.create_index(
        op.f("ix_estoque_endereco_lote_empresa_id"), "estoque_endereco_lote", ["empresa_id"]
    )
    op.create_index(
        op.f("ix_estoque_endereco_lote_sistema_origem_id"),
        "estoque_endereco_lote",
        ["sistema_origem_id"],
    )

    # ------------------------------- o endereço sai da linha do pedido
    op.drop_column("pedido_itens", "endereco_produto")


def downgrade() -> None:
    op.add_column(
        "pedido_itens", sa.Column("endereco_produto", sa.String(length=100), nullable=True)
    )
    op.drop_table("estoque_endereco_lote")
    op.drop_table("estoque_enderecos")
    op.drop_table("estoque_lotes")
    op.drop_table("estoque")
