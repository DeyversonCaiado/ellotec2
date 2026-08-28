"""quantidade por endereço em estoque_endereco_lote

Revision ID: e7a1c5d94b28
Revises: d2b7f4e9a610
Create Date: 2026-08-27 00:00:00.000000

A tabela nasceu como vínculo puro (endereço ↔ lote). Faltava o "quanto": a
expedição precisa mostrar a quantidade **por endereço** — hoje ela mostra o
total do item somado, o que não diz ao operador quanto pegar em cada prateleira
— e precisa baixar dessa quantidade quando a separação fecha.

`server_default="0"` existe só para a coluna poder nascer NOT NULL num banco que
já tem linhas. As linhas antigas ficam com saldo zero, e é o certo: elas nunca
souberam a quantidade, e zero é o que a consistência da expedição vai apontar
como "endereçamento incompleto" em vez de deixar passar um número inventado.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a1c5d94b28"
down_revision: Union[str, Sequence[str], None] = "d2b7f4e9a610"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "estoque_endereco_lote",
        sa.Column(
            "quantidade",
            sa.Numeric(precision=14, scale=3),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("estoque_endereco_lote", "quantidade")
