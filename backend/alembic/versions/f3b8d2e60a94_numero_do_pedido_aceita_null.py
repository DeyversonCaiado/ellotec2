"""numero do pedido passa a aceitar NULL

Revision ID: f3b8d2e60a94
Revises: e7a1c5d94b28
Create Date: 2026-08-27 00:00:00.000000

O número do pedido é o do ERP quando ele existe (`sistema_origem_id`) e um
sequencial daqui quando o pedido nasce na tela. Nem toda origem externa, porém,
tem um número no instante em que manda o pedido — e recusar a carga por causa
disso perde o pedido inteiro por um campo que o remetente ainda vai preencher.

Duas consequências que o desenho já suporta, e por isso a mudança é segura:

- No MySQL dois NULL não colidem num índice único, então
  `uq_pedidos_numero_empresa_id` continua valendo para quem tem número e não
  barra vários pedidos sem número na mesma empresa.
- A busca da listagem faz `numero LIKE '%termo%'`, que simplesmente não casa com
  NULL — o pedido sem número não aparece na busca por número, que é o
  comportamento correto.

Não há downgrade automático seguro: voltar para NOT NULL exigiria inventar um
número para as linhas nulas, e inventar número de pedido é exatamente o que esta
revisão existe para evitar. O downgrade preenche as nulas com o
`sistema_origem_id` quando ele existe e ABORTA se sobrar alguma — assim quem
reverter decide o que fazer, em vez de descobrir depois.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3b8d2e60a94"
down_revision: Union[str, Sequence[str], None] = "e7a1c5d94b28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "pedidos",
        "numero",
        existing_type=sa.String(length=20),
        nullable=True,
    )


def downgrade() -> None:
    conexao = op.get_bind()
    conexao.execute(
        sa.text(
            "UPDATE pedidos SET numero = sistema_origem_id "
            "WHERE numero IS NULL AND sistema_origem_id IS NOT NULL"
        )
    )
    restantes = conexao.execute(
        sa.text("SELECT COUNT(*) FROM pedidos WHERE numero IS NULL")
    ).scalar()
    if restantes:
        raise RuntimeError(
            f"{restantes} pedido(s) sem número e sem sistema_origem_id. "
            "Defina um número para eles antes de voltar a coluna para NOT NULL."
        )
    op.alter_column(
        "pedidos",
        "numero",
        existing_type=sa.String(length=20),
        nullable=False,
    )
