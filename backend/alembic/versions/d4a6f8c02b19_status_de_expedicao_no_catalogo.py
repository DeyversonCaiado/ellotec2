"""pedido_status: etapas de expedição no catálogo

Revision ID: d4a6f8c02b19
Revises: c8f3d5b26e47
Create Date: 2026-08-19 00:00:00.000000

Quatro status novos, um por marco do galpão: em separação, separado, em
conferência e conferido. Entram no mesmo catálogo `pedido_status` que já
guarda os status vindos do ERP (PED, OK, ORC…), mas com `sistema_origem_id`
nulo, porque não vêm de lá — são nossos.

A chave segue a convenção dos status locais já existentes (`rascunho`,
`enviado`, `aprovado`, `recusado`): minúscula com underscore. Os códigos em
maiúscula de três letras são reservados ao ERP, e inventar um deles aqui
criaria colisão na próxima sincronização.

Migration só de dados — nenhuma coluna muda.

"""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4a6f8c02b19"
down_revision: Union[str, Sequence[str], None] = "c8f3d5b26e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHAVES_EXPEDICAO = ["em_separacao", "separado", "em_conferencia", "conferido"]

_TABELA = sa.table(
    "pedido_status",
    sa.column("id", sa.String),
    sa.column("chave", sa.String),
    sa.column("sync_created_at", sa.DateTime),
    sa.column("sync_updated_at", sa.DateTime),
    sa.column("sync_version", sa.Integer),
)


def upgrade() -> None:
    conexao = op.get_bind()
    agora = datetime.now(timezone.utc).replace(tzinfo=None)

    # Idempotente de propósito: `chave` é única, e um ambiente que já tenha
    # recebido esses status por outro caminho não pode fazer a migration
    # quebrar no meio.
    existentes = {
        linha[0]
        for linha in conexao.execute(
            sa.select(_TABELA.c.chave).where(_TABELA.c.chave.in_(CHAVES_EXPEDICAO))
        )
    }

    for chave in CHAVES_EXPEDICAO:
        if chave in existentes:
            continue
        conexao.execute(
            _TABELA.insert().values(
                id=str(uuid.uuid4()),
                chave=chave,
                sync_created_at=agora,
                sync_updated_at=agora,
                sync_version=1,
            )
        )


def downgrade() -> None:
    # Só remove se nenhum pedido tiver ficado apontando para eles — apagar um
    # status em uso deixaria pedidos com FK órfã.
    conexao = op.get_bind()
    conexao.execute(
        sa.text(
            """
            DELETE FROM pedido_status
             WHERE chave IN :chaves
               AND id NOT IN (SELECT DISTINCT status_id FROM pedidos)
            """
        ).bindparams(sa.bindparam("chaves", value=tuple(CHAVES_EXPEDICAO), expanding=True))
    )
