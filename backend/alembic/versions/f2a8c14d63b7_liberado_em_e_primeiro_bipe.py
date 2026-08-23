"""pedidos.liberado_em e primeiro bipe nos processos de expedição

Revision ID: f2a8c14d63b7
Revises: e9b3c7a25f18
Create Date: 2026-08-20 00:00:00.000000

Dois milestones, não campos de auditoria.

`pedidos.liberado_em` é quando o pedido foi liberado no ERP (ex: aprovação de
crédito). É o instante em que o pedido passa a existir para o armazém, e é dele
que se conta o ciclo da expedição — por isso vem indexado: é candidato natural
a ordenação da fila.

`data_primeiro_bipe` marca quando o trabalho realmente começou em cada processo.
Diferente de `data_inicio`, que é a abertura: entre abrir a lista e bipar o
primeiro item o operador ainda está indo até o endereço, e esse tempo não é
separação nem conferência.

Todas nullable: pedido não liberado e processo sem leitura ainda são estados
legítimos, não dado faltando.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2a8c14d63b7"
down_revision: Union[str, Sequence[str], None] = "e9b3c7a25f18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pedidos", sa.Column("liberado_em", sa.DateTime(), nullable=True))
    op.create_index(op.f("ix_pedidos_liberado_em"), "pedidos", ["liberado_em"], unique=False)

    op.add_column(
        "expedicao_separacoes", sa.Column("data_primeiro_bipe", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "expedicao_conferencias", sa.Column("data_primeiro_bipe", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("expedicao_conferencias", "data_primeiro_bipe")
    op.drop_column("expedicao_separacoes", "data_primeiro_bipe")
    op.drop_index(op.f("ix_pedidos_liberado_em"), table_name="pedidos")
    op.drop_column("pedidos", "liberado_em")
