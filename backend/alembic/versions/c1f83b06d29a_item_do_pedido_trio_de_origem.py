"""pedido_itens: o trio empresa + pedido + produto do sistema de origem

Revision ID: c1f83b06d29a
Revises: b7e3a9d51c04
Create Date: 2026-08-25 00:00:00.000000

Corrige a modelagem que a a4d9c2f70b13 tinha deixado pela metade.

Lá o item ganhou `sistema_origem_id` + `empresa_sistema_origem_id`, com aquele
primeiro campo significando "o id da linha do item no ERP". Só que o ERP não dá
id próprio para a linha do item: ele a identifica pela chave natural
**empresa + pedido + produto**. Com duas colunas faltava a perna do pedido, e o
mesmo produto se repete em pedidos diferentes da mesma empresa — ou seja, o par
não chegava a uma linha só, que era exatamente o problema que a migração
anterior queria resolver.

Duas mudanças, então:

1. `sistema_origem_id` vira `produto_sistema_origem_id`. O conteúdo é o código
   do produto no ERP, e é esse o nome dele em todo o resto do projeto (o campo
   já existia com esse nome no contrato de entrada, onde resolve `produto_id`).
   Manter o nome `sistema_origem_id` guardando o código do produto faria esse
   nome significar uma coisa aqui e outra em `pedidos`, `produtos`, `empresas`
   e `usuarios`, onde ele quer dizer "o id da própria linha no ERP".

2. Entra `pedido_sistema_origem_id`, a perna que faltava.

O índice é refeito com as três colunas, e o pedido passa a ser a primeira: é a
mais seletiva, e o prefixo (pedido, empresa) já responde "quais são os itens
deste pedido?" sem precisar de um segundo índice.

Sem backfill e sem perda: o rename preserva o que estiver gravado, e a coluna
nova nasce nula. A migração anterior subiu há minutos e nenhuma integração
chegou a popular as colunas, então na prática as três estão vazias.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c1f83b06d29a"
down_revision: Union[str, Sequence[str], None] = "b7e3a9d51c04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # O índice é derrubado antes do rename: ele referencia a coluna antiga.
    op.drop_index("ix_pedido_itens_sistema_origem", table_name="pedido_itens")

    op.alter_column(
        "pedido_itens",
        "sistema_origem_id",
        new_column_name="produto_sistema_origem_id",
        existing_type=sa.String(length=100),
        existing_nullable=True,
    )
    op.add_column(
        "pedido_itens",
        sa.Column("pedido_sistema_origem_id", sa.String(length=100), nullable=True),
    )

    op.create_index(
        "ix_pedido_itens_sistema_origem",
        "pedido_itens",
        ["pedido_sistema_origem_id", "empresa_sistema_origem_id", "produto_sistema_origem_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pedido_itens_sistema_origem", table_name="pedido_itens")

    op.drop_column("pedido_itens", "pedido_sistema_origem_id")
    op.alter_column(
        "pedido_itens",
        "produto_sistema_origem_id",
        new_column_name="sistema_origem_id",
        existing_type=sa.String(length=100),
        existing_nullable=True,
    )

    op.create_index(
        "ix_pedido_itens_sistema_origem",
        "pedido_itens",
        ["sistema_origem_id", "empresa_sistema_origem_id"],
    )
