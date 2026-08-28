"""pedido_itens: identidade própria no sistema de origem

Revision ID: a4d9c2f70b13
Revises: e2c7f4a08b19
Create Date: 2026-08-25 00:00:00.000000

O item do pedido não tinha como ser apontado pelo ERP: só a capa carregava
`sistema_origem_id`. Quem recebia "o item tal do pedido tal" do lado de lá
dependia da ordem do array de itens para adivinhar a linha.

São duas colunas, e não uma, pelo mesmo motivo que a capa tem
`uq_pedidos_sistema_origem_id_empresa_id`: o ERP numera por empresa/filial,
então `sistema_origem_id` sozinho existe em mais de uma empresa e não aponta
para uma linha só. O par é que identifica.

O índice é composto e NÃO é único. Único quebraria em dois pontos reais:
`pedido_service.atualizar` troca o conjunto inteiro de itens (apaga os antigos
e insere os novos) numa transação só, e o soft delete do SyncMixin deixaria
linha apagada ocupando a chave — o MySQL não tem índice único parcial. É a
mesma razão registrada em `expedicao_atribuicoes` (ver expedicao_model.py).

Ambas nullable e sem backfill: item lançado pela tela não vem de sistema
nenhum, e os itens que já estão no banco não têm essa informação em lugar
algum de onde copiar. Nulo aqui significa "não veio de integração", que é
verdade.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a4d9c2f70b13"
down_revision: Union[str, Sequence[str], None] = "e2c7f4a08b19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pedido_itens", sa.Column("sistema_origem_id", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "pedido_itens",
        sa.Column("empresa_sistema_origem_id", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_pedido_itens_sistema_origem",
        "pedido_itens",
        ["sistema_origem_id", "empresa_sistema_origem_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pedido_itens_sistema_origem", table_name="pedido_itens")
    op.drop_column("pedido_itens", "empresa_sistema_origem_id")
    op.drop_column("pedido_itens", "sistema_origem_id")
