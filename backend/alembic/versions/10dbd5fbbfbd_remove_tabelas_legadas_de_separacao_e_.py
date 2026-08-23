"""remove tabelas legadas de separacao e conferencia

Revision ID: 10dbd5fbbfbd
Revises: 246589e040dc
Create Date: 2026-08-17 13:38:08.247731

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10dbd5fbbfbd'
down_revision: Union[str, Sequence[str], None] = '246589e040dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Remove as tabelas legadas de separação/conferência (`pedido_separacao*`,
    `pedido_conferencia*`), substituídas pelas novas tabelas do domínio de
    expedição (`expedicao_separacoes`/`expedicao_conferencias`, ver revisão
    4b6689082a41). Tabelas-filha primeiro, por causa da FK.
    """
    op.drop_table('pedido_separacao_item')
    op.drop_table('pedido_conferencia_item')
    op.drop_table('pedido_separacao')
    op.drop_table('pedido_conferencia')


def downgrade() -> None:
    """Downgrade schema."""
    raise NotImplementedError(
        "Downgrade não suportado: as tabelas legadas foram removidas em definitivo. "
        "Restaure a partir de um backup se precisar reverter."
    )
