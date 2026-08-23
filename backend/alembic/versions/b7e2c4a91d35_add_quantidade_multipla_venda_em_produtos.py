"""produtos: quantidade_multipla_venda

Revision ID: b7e2c4a91d35
Revises: a1f4c7d92b60
Create Date: 2026-08-19 00:00:00.000000

Quantas unidades entram numa embalagem de venda. O estoque continua sendo
contado em unidade — o campo existe porque há produto que só se vende pela
caixa fechada, e cada leitura no coletor precisa valer a caixa inteira.

Sobe com server_default "1" para não quebrar as linhas existentes (produto
vendido na unidade), e o default é removido em seguida: o valor passa a vir
sempre do model, como nas outras colunas.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e2c4a91d35"
down_revision: Union[str, Sequence[str], None] = "a1f4c7d92b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "produtos",
        sa.Column("quantidade_multipla_venda", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("produtos", "quantidade_multipla_venda")
