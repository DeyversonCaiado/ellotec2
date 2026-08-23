"""adiciona campo usuario em usuarios

Revision ID: 2c3d8f4a7c91
Revises: b9ee9602cf27
Create Date: 2026-08-10 16:30:00.000000

"""

from collections import Counter
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2c3d8f4a7c91"
down_revision: Union[str, Sequence[str], None] = "b9ee9602cf27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _gerar_usuario_base(email: str) -> str:
    base = (email.split("@", 1)[0] if email else "").strip().lower()
    return base[:50] or "usuario"


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("usuario", sa.String(length=50), nullable=True))

    conexao = op.get_bind()
    resultados = conexao.execute(sa.text("SELECT id, email FROM usuarios WHERE sync_deleted_at IS NULL ORDER BY email")).fetchall()

    usados = Counter()
    for usuario_id, email in resultados:
        base = _gerar_usuario_base(email)
        usados[base] += 1
        nome_usuario = base if usados[base] == 1 else f"{base[:47]}-{usados[base]}"
        conexao.execute(
            sa.text("UPDATE usuarios SET usuario = :usuario WHERE id = :id"),
            {"usuario": nome_usuario[:50], "id": usuario_id},
        )

    op.alter_column("usuarios", "usuario", existing_type=sa.String(length=50), nullable=False)
    op.create_index(op.f("ix_usuarios_usuario"), "usuarios", ["usuario"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_usuarios_usuario"), table_name="usuarios")
    op.drop_column("usuarios", "usuario")
