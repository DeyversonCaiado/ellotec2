"""produtos.registro_anvisa

Revision ID: c2f7a4e18b93
Revises: b8d3f0a52c17
Create Date: 2026-08-21 00:00:00.000000

Registro do produto na ANVISA.

Texto, não número: o registro tem zeros à esquerda que fazem parte dele, e há
produto isento ou em processo de renovação, cujo campo o cadastro do ERP
preenche com texto livre. Guardar como inteiro perderia o zero da frente e
recusaria os casos que não são numéricos.

Nullable e sem valor padrão: nem todo item do catálogo é produto de saúde
registrado, e os que são ainda não têm o dado aqui. Campo em branco é estado
legítimo, não dado faltando.

Sem índice: ninguém busca produto por registro hoje. Se virar filtro de tela,
o índice entra junto com o filtro.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2f7a4e18b93"
down_revision: Union[str, Sequence[str], None] = "b8d3f0a52c17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("produtos", sa.Column("registro_anvisa", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("produtos", "registro_anvisa")
