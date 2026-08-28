"""entregas: data_interacao — a linha do tempo deixa de usar campo de sync

Revision ID: e2c7f4a08b19
Revises: c9a5b213e8d0
Create Date: 2026-08-23 00:00:00.000000

A timeline ordenava e exibia por `sync_created_at`, que é campo de auditoria da
LINHA e não do FATO. Isso viola a regra registrada nos dois ARCHITECTURE.md
("Os campos sync_* nunca entram na regra de negócio"): um reprocessamento da
integração ou a futura rotina de replicação tocam a linha, e o que a tela mostra
como "quando aconteceu" muda sozinho.

`data_interacao` passa a ser o instante do evento, com coluna própria. Hoje
nasce igual à data de inclusão; quando existir lançamento retroativo (ocorrência
que a transportadora informa dois dias depois), é nela que a data real entra.

O backfill copia `sync_created_at`, que para as linhas migradas do sistema
antigo já é o `data_cadastro` original de `nota_interacao` — ou seja, a data
verdadeira de cada interação é preservada.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e2c7f4a08b19"
down_revision: Union[str, Sequence[str], None] = "c9a5b213e8d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Entra nullable para o backfill caber em tabela que já tem linhas — só
    # depois vira NOT NULL.
    op.add_column(
        "entrega_nota_interacoes", sa.Column("data_interacao", sa.DateTime(), nullable=True)
    )
    op.execute(
        "UPDATE entrega_nota_interacoes SET data_interacao = sync_created_at "
        "WHERE data_interacao IS NULL"
    )
    op.alter_column(
        "entrega_nota_interacoes",
        "data_interacao",
        existing_type=sa.DateTime(),
        nullable=False,
    )

    op.create_index(
        "ix_entrega_nota_interacoes_data", "entrega_nota_interacoes", ["data_interacao"]
    )
    # O índice antigo existia para ordenar a timeline por sync_created_at —
    # exatamente o uso que esta migração elimina.
    op.drop_index("ix_entrega_nota_interacoes_criado", table_name="entrega_nota_interacoes")


def downgrade() -> None:
    op.create_index(
        "ix_entrega_nota_interacoes_criado", "entrega_nota_interacoes", ["sync_created_at"]
    )
    op.drop_index("ix_entrega_nota_interacoes_data", table_name="entrega_nota_interacoes")
    op.drop_column("entrega_nota_interacoes", "data_interacao")
