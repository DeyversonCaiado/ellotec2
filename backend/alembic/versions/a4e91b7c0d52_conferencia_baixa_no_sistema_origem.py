"""expedicao_conferencias: desfecho da baixa no sistema de origem

Duas colunas novas em `expedicao_conferencias`, ambas nullable:

- `finalizado_origem_em` (DATETIME): quando o ERP aceitou a baixa do pedido
  (status `FEC`). NULL = ainda não foi fechado lá. É coluna de NEGÓCIO e não um
  campo `sync_*` de propósito — o instante em que o ERP aceitou é um fato, e
  campo de sincronização nunca entra em regra de negócio (ver ARCHITECTURE.md).
- `motivo_falha_origem` (VARCHAR(255)): por que a última tentativa foi recusada.
  Sobrescrita a cada tentativa, limpa quando dá certo.

Existem porque a conferência fechar AQUI e o pedido fechar LÁ são duas
transações em bancos diferentes: o Oracle pode estar fora do ar no exato minuto
em que o operador termina de bipar. Sem elas, o pedido ficava "conferido" no
ELLOTEC e `PED` no ERP sem nenhum rastro do motivo.

Escrita à mão em vez de `--autogenerate` pelo mesmo motivo documentado na
migração `02cfde971d6f`: o autogenerate desta base ainda arrasta um conjunto de
divergências preexistentes entre os models e o banco (índices de `usuarios`, o
tipo de `cidades.id`) que não têm relação nenhuma com esta mudança e não podem
viajar de carona numa migração de duas colunas.

Revision ID: a4e91b7c0d52
Revises: 02cfde971d6f
Create Date: 2026-09-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4e91b7c0d52"
down_revision: Union[str, Sequence[str], None] = "02cfde971d6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "expedicao_conferencias",
        sa.Column("finalizado_origem_em", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "expedicao_conferencias",
        sa.Column("motivo_falha_origem", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("expedicao_conferencias", "motivo_falha_origem")
    op.drop_column("expedicao_conferencias", "finalizado_origem_em")
