"""cria expedicao_configuracoes

Uma linha só, com os parâmetros do processo de expedição. Os dois primeiros
desligam, cada um por sua conta, as duas regras da trava de endereçamento:

- `permite_conferir_com_divergencia` — a soma dos endereços do lote é menor que
  a quantidade vendida;
- `permite_conferir_fora_do_multiplo_de_venda` — o saldo de um endereço não
  fecha em múltiplo da embalagem de venda do produto.

São colunas separadas porque são problemas diferentes do galpão, e um galpão
pode conviver com um e não com o outro.

Nascem `False` — as duas travas ligadas, que é como a expedição sempre
funcionou. A
tabela sobe vazia de propósito: `expedicao_configuracao_service.obter` cria a
linha com os padrões do model na primeira vez que o painel é aberto, e a
leitura da borda responde o padrão de fábrica enquanto ela não existir. Um
INSERT aqui gravaria os mesmos valores sem adiantar nada.

Escrita à mão em vez de `--autogenerate` pelo mesmo motivo das migrações
`02cfde971d6f`, `a4e91b7c0d52` e `b5f02c8d1a63`: o autogenerate desta base
ainda arrasta divergências preexistentes entre models e banco que não têm
relação com esta mudança.

Revision ID: a7c1d3e58f42
Revises: b5f02c8d1a63
Create Date: 2026-09-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c1d3e58f42"
down_revision: Union[str, Sequence[str], None] = "b5f02c8d1a63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expedicao_configuracoes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("permite_conferir_com_divergencia", sa.Boolean(), nullable=False),
        sa.Column(
            "permite_conferir_fora_do_multiplo_de_venda", sa.Boolean(), nullable=False
        ),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("expedicao_configuracoes")
