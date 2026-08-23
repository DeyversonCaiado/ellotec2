"""produtos: dun_14

Revision ID: c8f3d5b26e47
Revises: b7e2c4a91d35
Create Date: 2026-08-19 00:00:00.000000

DUN-14 (GTIN-14) é o código impresso na embalagem de despacho — a caixa
fechada. Na bipagem do coletor a expedição procura primeiro pelo EAN da
unidade (`codigo_barras`) e cai neste campo quando não encontra.

Indexado e não único, pelo mesmo motivo do `codigo_barras`: cadastros
duplicados vindos de integração podem repetir o número, e uma constraint
única quebraria a importação.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8f3d5b26e47"
down_revision: Union[str, Sequence[str], None] = "b7e2c4a91d35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("produtos", sa.Column("dun_14", sa.String(length=60), nullable=True))
    op.create_index(op.f("ix_produtos_dun_14"), "produtos", ["dun_14"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_produtos_dun_14"), table_name="produtos")
    op.drop_column("produtos", "dun_14")
