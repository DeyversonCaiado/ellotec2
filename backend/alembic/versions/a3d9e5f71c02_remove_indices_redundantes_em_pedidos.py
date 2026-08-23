"""pedidos: remove índices redundantes de numero e sistema_origem_id

Revision ID: a3d9e5f71c02
Revises: e5b7a1c93f24
Create Date: 2026-08-19 00:00:00.000000

`ix_pedidos_numero` e `ix_pedidos_sistema_origem_id` indexam, cada um, uma
coluna que já é a PRIMEIRA de um índice composto:

    uq_pedidos_numero_empresa_id            (numero, empresa_id)
    uq_pedidos_sistema_origem_id_empresa_id (sistema_origem_id, empresa_id)

O MySQL usa o prefixo à esquerda de um índice composto, então toda busca por
`numero` ou por `sistema_origem_id` sozinhos continua indexada sem eles. São
~64 MB numa tabela cujos índices já pesam o dobro dos dados — cada entrada de
índice secundário carrega a PK junto, e a PK aqui é um UUID de 36 caracteres.

Vem antes da migration de índices da listagem (f6c8b3d150ea) de propósito: o
servidor está sem espaço em disco, e criar índice lá exige folga que só existe
depois desta.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a3d9e5f71c02"
down_revision: Union[str, Sequence[str], None] = "e5b7a1c93f24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REDUNDANTES = {
    "ix_pedidos_numero": "numero",
    "ix_pedidos_sistema_origem_id": "sistema_origem_id",
}


def _existentes() -> set[str]:
    return {indice["name"] for indice in sa.inspect(op.get_bind()).get_indexes("pedidos")}


def upgrade() -> None:
    existentes = _existentes()
    for nome in _REDUNDANTES:
        if nome in existentes:
            op.drop_index(op.f(nome), table_name="pedidos")


def downgrade() -> None:
    existentes = _existentes()
    for nome, coluna in _REDUNDANTES.items():
        if nome not in existentes:
            op.create_index(op.f(nome), "pedidos", [coluna], unique=False)
