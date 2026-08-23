"""pedidos: índices de data_pedido e sync_updated_at

Revision ID: f6c8b3d150ea
Revises: a3d9e5f71c02
Create Date: 2026-08-19 00:00:00.000000

A listagem da expedição passou a mostrar todos os pedidos, filtrados por
período de DATA DO PEDIDO e ordenados por data de alteração. Sem índice nesses
campos, MySQL varre as ~230 mil linhas de `pedidos` e ordena em arquivo
temporário — foi exatamente o que estourou o /tmp do servidor de banco quando a
listagem perdeu o índice de status.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f6c8b3d150ea"
down_revision: Union[str, Sequence[str], None] = "a3d9e5f71c02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# data_pedido é por onde a tela filtra o período; sync_updated_at é por onde a
# lista ordena.
_INDICES = {
    "ix_pedidos_data_pedido": "data_pedido",
    "ix_pedidos_sync_updated_at": "sync_updated_at",
}


def _existentes() -> set[str]:
    """DDL de índice no MySQL não é transacional: uma migration que falha no
    meio deixa parte aplicada. Conferir antes evita que a correção seguinte
    esbarre em 'índice já existe' ou 'índice não existe'."""
    return {indice["name"] for indice in sa.inspect(op.get_bind()).get_indexes("pedidos")}


def upgrade() -> None:
    existentes = _existentes()
    for nome, coluna in _INDICES.items():
        if nome not in existentes:
            op.create_index(op.f(nome), "pedidos", [coluna], unique=False)


def downgrade() -> None:
    existentes = _existentes()
    for nome in _INDICES:
        if nome in existentes:
            op.drop_index(op.f(nome), table_name="pedidos")
