"""pedido_itens: uma linha por (pedido, produto, lote)

Revision ID: c9e4a71f5b38
Revises: c1f83b06d29a
Create Date: 2026-08-25 00:00:00.000000

A linha do pedido é o que o cliente comprou: produto, lote, quantidade. O
endereço não faz parte disso — ele é onde a mercadoria está guardada no NOSSO
galpão. Um lote realmente se espalha por vários endereços, mas esse fato
pertence à separação (`expedicao_separacao_itens`), não ao pedido; é assim que
os ERPs grandes modelam, e a linha de pedido deles nem carrega endereço.

Sem a constraint, entraram 90 linhas duplicadas em 24 pedidos. A causa é
produto cartesiano na consulta da integração: a linha do pedido cruzada com o
estoque por endereço, devolvendo uma linha por endereço — cada uma com a
quantidade INTEIRA, não uma fração dela. O pedido 0186250, de 14.000 unidades,
estava gravado com 56.000.

A prova de que não é espalhamento legítimo está nos próprios dados: nos 62
grupos duplicados, TODOS têm a mesma quantidade em todas as linhas. Um
espalhamento real dividiria (8.000 + 6.000); estes repetem (14.000 + 14.000).

Por isso a limpeza é DELETE físico, e não `marcar_apagado()`. A regra do
soft delete existe para o dado de negócio que um dia foi verdade; estas linhas
nunca foram — são defeito de importação, e mantê-las soft-deletadas só deixaria
lixo ocupando a chave nova. Decisão tomada com o Deyverson, sabendo que nenhuma
delas é referenciada pela expedição (verificado: zero linhas em
`expedicao_separacao_itens` e `expedicao_conferencia_itens` apontam para elas).

Sobrevive a de menor `id` de cada grupo. Como as linhas do grupo são idênticas
em produto, lote e quantidade, qual delas fica é indiferente — só precisa ser
determinístico.

O índice do trio de origem (`ix_pedido_itens_sistema_origem`) sai junto: ele
existia como chave de busca, papel que agora é da constraint. As três colunas
continuam na tabela — elas dizem como o ERP CHAMA esta linha, o que continua
útil, só não é a identidade dela aqui dentro.

Sem downgrade das linhas apagadas: dado excluído não volta. O downgrade
recria só o índice e larga a constraint.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c9e4a71f5b38"
down_revision: Union[str, Sequence[str], None] = "c1f83b06d29a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# `<=>` é o igual NULL-safe do MySQL: sem ele, grupo com lote nulo não casaria
# consigo mesmo e as duplicatas sem lote escapariam da limpeza.
_LIMPEZA = """
DELETE i FROM pedido_itens i
JOIN (
    SELECT pedido_id, produto_id, lote, MIN(id) AS manter
    FROM pedido_itens
    GROUP BY pedido_id, produto_id, lote
) k
  ON k.pedido_id = i.pedido_id
 AND k.produto_id = i.produto_id
 AND (k.lote <=> i.lote)
WHERE i.id <> k.manter
"""


def upgrade() -> None:
    op.execute(_LIMPEZA)

    op.drop_index("ix_pedido_itens_sistema_origem", table_name="pedido_itens")
    op.create_unique_constraint(
        "uq_pedido_itens_pedido_produto_lote",
        "pedido_itens",
        ["pedido_id", "produto_id", "lote"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_pedido_itens_pedido_produto_lote", "pedido_itens", type_="unique"
    )
    op.create_index(
        "ix_pedido_itens_sistema_origem",
        "pedido_itens",
        ["pedido_sistema_origem_id", "empresa_sistema_origem_id", "produto_sistema_origem_id"],
    )
