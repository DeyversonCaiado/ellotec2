"""expedicao_conferencias: quem tentou finalizar no ERP, e quando

Duas colunas novas em `expedicao_conferencias`, ambas nullable:

- `tentativa_origem_usuario_id` (FK `usuarios.id`): quem clicou em "Finalizar
  pedido" na ÚLTIMA tentativa.
- `tentativa_origem_em` (DATETIME): quando essa tentativa aconteceu.

Existem porque `motivo_falha_origem` (migração `a4e91b7c0d52`) conta o QUE
aconteceu, mas não em nome de quem nem a que horas — e a pergunta que aparece
depois é sempre essa: "quem tentou fechar este pedido e não conseguiu?". O caso
concreto que gerou a necessidade foi uma recusa por conta sem vínculo no ERP:
saber QUAL conta clicou é o que resolve, e o motivo gravado não dizia.

São sobrescritas a cada tentativa e **não** são limpas no sucesso: aí passam a
responder "quem fechou o pedido, e quando", junto com `finalizado_origem_em`.

`tentativa_origem_em` é coluna de negócio própria e não `sync_updated_at`: a
linha é tocada por outras escritas, e a hora da tentativa é um fato que não pode
se mexer sozinho (ver ARCHITECTURE.md → "Os campos `sync_*` nunca entram na
regra de negócio").

Escrita à mão em vez de `--autogenerate` pelo mesmo motivo das migrações
`02cfde971d6f` e `a4e91b7c0d52`: o autogenerate desta base ainda arrasta
divergências preexistentes entre models e banco que não têm relação com esta
mudança.

Revision ID: b5f02c8d1a63
Revises: a4e91b7c0d52
Create Date: 2026-09-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5f02c8d1a63"
down_revision: Union[str, Sequence[str], None] = "a4e91b7c0d52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "expedicao_conferencias",
        sa.Column("tentativa_origem_usuario_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "expedicao_conferencias",
        sa.Column("tentativa_origem_em", sa.DateTime(), nullable=True),
    )
    op.create_index(
        op.f("ix_expedicao_conferencias_tentativa_origem_usuario_id"),
        "expedicao_conferencias",
        ["tentativa_origem_usuario_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_expedicao_conferencias_tentativa_origem_usuario_id",
        "expedicao_conferencias",
        "usuarios",
        ["tentativa_origem_usuario_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_expedicao_conferencias_tentativa_origem_usuario_id",
        "expedicao_conferencias",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_expedicao_conferencias_tentativa_origem_usuario_id"),
        table_name="expedicao_conferencias",
    )
    op.drop_column("expedicao_conferencias", "tentativa_origem_em")
    op.drop_column("expedicao_conferencias", "tentativa_origem_usuario_id")
