"""migra usuario_permissoes de (dominio, ler/criar/editar/apagar) para chave flat

Revision ID: a1f5c9d3e7b2
Revises: 9f4a7d2c1b88
Create Date: 2026-08-12 00:00:00.000000

"""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1f5c9d3e7b2"
down_revision: Union[str, Sequence[str], None] = "9f4a7d2c1b88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mesma conversão CRUD -> chave usada em toda a base:
# ler -> dominio.acessar, criar -> dominio.gravar.incluir,
# editar -> dominio.gravar.editar, apagar -> dominio.apagar.
_ACOES = {
    "ler": "acessar",
    "criar": "gravar.incluir",
    "editar": "gravar.editar",
    "apagar": "apagar",
}


def upgrade() -> None:
    op.add_column("usuario_permissoes", sa.Column("chave", sa.String(length=100), nullable=True))

    # A constraint única antiga é (usuario_id, dominio) — como o loop abaixo
    # insere várias linhas novas para o MESMO (usuario_id, dominio) quando um
    # usuário tinha mais de uma ação marcada no mesmo domínio (cada ação vira
    # uma chave/linha própria), ela precisa sair ANTES do loop, não depois.
    op.drop_constraint("uq_usuario_dominio", "usuario_permissoes", type_="unique")

    conexao = op.get_bind()
    linhas = conexao.execute(
        sa.text("SELECT id, usuario_id, dominio, ler, criar, editar, apagar FROM usuario_permissoes")
    ).fetchall()

    agora = datetime.now(timezone.utc)

    for linha_id, usuario_id, dominio, ler, criar, editar, apagar in linhas:
        marcadas = [acao for acao, valor in (("ler", ler), ("criar", criar), ("editar", editar), ("apagar", apagar)) if valor]

        if not marcadas:
            conexao.execute(sa.text("DELETE FROM usuario_permissoes WHERE id = :id"), {"id": linha_id})
            continue

        primeira, *demais = marcadas
        conexao.execute(
            sa.text("UPDATE usuario_permissoes SET chave = :chave WHERE id = :id"),
            {"chave": f"{dominio}.{_ACOES[primeira]}", "id": linha_id},
        )
        for acao in demais:
            conexao.execute(
                sa.text(
                    "INSERT INTO usuario_permissoes "
                    "(id, usuario_id, dominio, ler, criar, editar, apagar, chave, sync_created_at, sync_updated_at, sync_version) "
                    "VALUES (:id, :usuario_id, :dominio, 0, 0, 0, 0, :chave, :agora, :agora, 1)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "usuario_id": usuario_id,
                    "dominio": dominio,
                    "chave": f"{dominio}.{_ACOES[acao]}",
                    "agora": agora,
                },
            )

    op.drop_column("usuario_permissoes", "ler")
    op.drop_column("usuario_permissoes", "criar")
    op.drop_column("usuario_permissoes", "editar")
    op.drop_column("usuario_permissoes", "apagar")

    op.alter_column("usuario_permissoes", "chave", existing_type=sa.String(length=100), nullable=False)
    op.drop_column("usuario_permissoes", "dominio")
    op.create_unique_constraint("uq_usuario_chave", "usuario_permissoes", ["usuario_id", "chave"])


def downgrade() -> None:
    op.add_column("usuario_permissoes", sa.Column("dominio", sa.String(length=30), nullable=True))
    op.add_column("usuario_permissoes", sa.Column("ler", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("usuario_permissoes", sa.Column("criar", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("usuario_permissoes", sa.Column("editar", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("usuario_permissoes", sa.Column("apagar", sa.Boolean(), nullable=False, server_default=sa.false()))

    conexao = op.get_bind()
    linhas = conexao.execute(sa.text("SELECT id, chave FROM usuario_permissoes")).fetchall()
    acao_por_sufixo = {v: k for k, v in _ACOES.items()}

    for linha_id, chave in linhas:
        dominio, resto = chave.split(".", 1)
        acao = acao_por_sufixo.get(resto, "ler")
        conexao.execute(
            sa.text(f"UPDATE usuario_permissoes SET dominio = :dominio, {acao} = 1 WHERE id = :id"),
            {"dominio": dominio, "id": linha_id},
        )

    op.drop_constraint("uq_usuario_chave", "usuario_permissoes", type_="unique")
    op.alter_column("usuario_permissoes", "dominio", existing_type=sa.String(length=30), nullable=False)
    op.drop_column("usuario_permissoes", "chave")
    op.create_unique_constraint("uq_usuario_dominio", "usuario_permissoes", ["usuario_id", "dominio"])
