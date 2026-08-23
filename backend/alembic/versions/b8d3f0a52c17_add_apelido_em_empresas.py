"""empresas.apelido

Revision ID: b8d3f0a52c17
Revises: a1c4e7b90f26
Create Date: 2026-08-21 00:00:00.000000

Nome curto pelo qual a empresa é chamada no dia a dia — "Matriz", "BSB", "SP".
Razão social e nome fantasia continuam sendo os nomes oficiais; este é o atalho
que as pessoas usam quando falam entre si e que cabe num filtro ou num badge.

Nullable, e sem valor padrão: o cadastro já existe e as linhas atuais não têm
apelido nenhum. Preencher é trabalho de quem conhece as empresas, não de uma
migração que teria que adivinhar — e apelido em branco é um estado legítimo,
não dado faltando.

Sem índice: 6 empresas no cadastro. Índice aqui seria cerimônia.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8d3f0a52c17"
down_revision: Union[str, Sequence[str], None] = "a1c4e7b90f26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("empresas", sa.Column("apelido", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("empresas", "apelido")
