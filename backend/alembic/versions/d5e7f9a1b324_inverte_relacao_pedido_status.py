"""inverte relação pedido <-> pedido_status: pedido_status vira catálogo

Revision ID: d5e7f9a1b324
Revises: c4d6e8f0a213
Create Date: 2026-08-17 00:00:00.000000

"""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d5e7f9a1b324"
down_revision: Union[str, Sequence[str], None] = "c4d6e8f0a213"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHAVES_STATUS = ["rascunho", "enviado", "aprovado", "recusado"]


def upgrade() -> None:
    # `pedido_status` guardava (por engano) pedido_id apontando pra
    # `pedidos`, como se cada pedido tivesse sua própria linha de status —
    # mas nunca foi usada por nenhum service (Pedido.status era uma coluna
    # de texto solta, gravada e lida direto, sem relação com essa tabela).
    # Ela vira catálogo fixo: uma linha por status possível, referenciada
    # pelo pedido, não o contrário.
    op.drop_constraint("pedido_status_ibfk_1", "pedido_status", type_="foreignkey")
    op.drop_index(op.f("ix_pedido_status_pedido_id"), table_name="pedido_status")
    op.drop_column("pedido_status", "pedido_id")
    op.drop_column("pedido_status", "status")
    op.add_column("pedido_status", sa.Column("chave", sa.String(length=20), nullable=True))

    pedido_status_tabela = sa.table(
        "pedido_status",
        sa.column("id", sa.String),
        sa.column("chave", sa.String),
        sa.column("sync_created_at", sa.DateTime),
        sa.column("sync_updated_at", sa.DateTime),
        sa.column("sync_version", sa.Integer),
    )
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    conexao = op.get_bind()
    for chave in CHAVES_STATUS:
        conexao.execute(
            pedido_status_tabela.insert().values(
                id=str(uuid.uuid4()),
                chave=chave,
                sync_created_at=agora,
                sync_updated_at=agora,
                sync_version=1,
            )
        )

    op.alter_column("pedido_status", "chave", existing_type=sa.String(length=20), nullable=False)
    op.create_index(op.f("ix_pedido_status_chave"), "pedido_status", ["chave"], unique=True)

    # pedidos.status (texto livre) -> pedidos.status_id (FK pro catálogo).
    # A tabela pedidos está vazia neste ambiente (ver migração anterior que
    # criou empresa_id), então o swap é direto, sem dado a migrar.
    op.add_column("pedidos", sa.Column("status_id", sa.String(length=36), nullable=False))
    op.create_index(op.f("ix_pedidos_status_id"), "pedidos", ["status_id"], unique=False)
    op.create_foreign_key(
        "fk_pedidos_status_id_pedido_status", "pedidos", "pedido_status", ["status_id"], ["id"]
    )
    op.drop_column("pedidos", "status")


def downgrade() -> None:
    op.add_column("pedidos", sa.Column("status", sa.String(length=20), nullable=False, server_default="rascunho"))
    op.drop_constraint("fk_pedidos_status_id_pedido_status", "pedidos", type_="foreignkey")
    op.drop_index(op.f("ix_pedidos_status_id"), table_name="pedidos")
    op.drop_column("pedidos", "status_id")

    op.drop_index(op.f("ix_pedido_status_chave"), table_name="pedido_status")
    op.drop_column("pedido_status", "chave")
    op.add_column("pedido_status", sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDENTE"))
    op.add_column("pedido_status", sa.Column("pedido_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_pedido_status_pedido_id"), "pedido_status", ["pedido_id"], unique=True)
    op.create_foreign_key(
        "pedido_status_ibfk_1", "pedido_status", "pedidos", ["pedido_id"], ["id"], ondelete="CASCADE"
    )
