"""entregas: mapa de carga, notas acompanhadas, itens e a linha do tempo

Revision ID: b8d4e0f61a37
Revises: d3f6a1c48e27
Create Date: 2026-08-23 00:00:00.000000

Substitui o processo do sistema antigo em Streamlit, que lia o Oracle do
GESTCOM direto e juntava o resultado em memória com a tabela `nota_interacao`
deste banco. Aqui os dados chegam por POST na nossa API, e o vínculo entre
interação, nota e usuário é feito por FK em vez de por quatro campos de texto.

`entrega_notas` guarda SNAPSHOT da nota (cliente, valor, itens) em vez de
apontar para `notas_fiscais`: as duas integrações rodam em ritmos diferentes, e
amarrar uma na outra deixaria a tela de entregas vazia sempre que a
sincronização fiscal atrasasse.

A migração de DADOS do legado (`nota_interacao`) é a revisão seguinte — esta
cria só a estrutura.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b8d4e0f61a37"
down_revision: Union[str, Sequence[str], None] = "d3f6a1c48e27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entregas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
        sa.Column("empresa_id", sa.String(length=36), nullable=False),
        sa.Column("numero_mapa", sa.String(length=30), nullable=False),
        sa.Column("data_mapa", sa.DateTime(), nullable=True),
        sa.Column("transportadora_nome", sa.String(length=200), nullable=True),
        sa.Column("transportadora_cnpj", sa.String(length=18), nullable=True),
        sa.Column("motorista", sa.String(length=150), nullable=True),
        sa.Column("placa_veiculo", sa.String(length=10), nullable=True),
        sa.Column("sistema_origem_id", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "numero_mapa", name="uq_entregas_empresa_numero"),
        sa.UniqueConstraint(
            "empresa_id", "sistema_origem_id", name="uq_entregas_empresa_sistema_origem"
        ),
    )
    op.create_index("ix_entregas_data_mapa", "entregas", ["data_mapa"])
    op.create_index(op.f("ix_entregas_empresa_id"), "entregas", ["empresa_id"])

    op.create_table(
        "entrega_notas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
        # Nullable: a nota é faturada antes de entrar num mapa de carga.
        sa.Column("entrega_id", sa.String(length=36), nullable=True),
        sa.Column("empresa_id", sa.String(length=36), nullable=False),
        sa.Column("numero_nota", sa.String(length=20), nullable=False),
        sa.Column("serie", sa.String(length=5), nullable=False),
        sa.Column("pedido", sa.String(length=50), nullable=False),
        sa.Column("tipo_nota", sa.String(length=30), nullable=False),
        sa.Column("data_nota", sa.DateTime(), nullable=True),
        sa.Column("situacao", sa.String(length=30), nullable=True),
        sa.Column("valor_total", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("cliente_codigo", sa.String(length=20), nullable=True),
        sa.Column("cliente_nome", sa.String(length=200), nullable=False),
        sa.Column("cliente_cidade", sa.String(length=100), nullable=True),
        sa.Column("cliente_uf", sa.String(length=2), nullable=True),
        sa.Column("vendedor_id", sa.String(length=36), nullable=True),
        sa.Column("transportadora_nome", sa.String(length=200), nullable=True),
        sa.Column("termolabil", sa.Boolean(), nullable=False),
        sa.Column("prazo_dias", sa.Integer(), nullable=True),
        sa.Column("data_prevista_entrega", sa.Date(), nullable=True),
        sa.Column("status_atual", sa.String(length=30), nullable=False),
        sa.Column("data_entrega_realizada", sa.DateTime(), nullable=True),
        sa.Column("sistema_origem_id", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["entrega_id"], ["entregas.id"]),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.ForeignKeyConstraint(["vendedor_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        # A chave natural do documento na visão da logística.
        sa.UniqueConstraint(
            "empresa_id", "numero_nota", "serie", "pedido", name="uq_entrega_notas_documento"
        ),
    )
    op.create_index("ix_entrega_notas_data_nota", "entrega_notas", ["data_nota"])
    op.create_index("ix_entrega_notas_status_atual", "entrega_notas", ["status_atual"])
    op.create_index("ix_entrega_notas_sync_updated_at", "entrega_notas", ["sync_updated_at"])
    op.create_index(op.f("ix_entrega_notas_entrega_id"), "entrega_notas", ["entrega_id"])
    op.create_index(op.f("ix_entrega_notas_empresa_id"), "entrega_notas", ["empresa_id"])
    op.create_index(op.f("ix_entrega_notas_vendedor_id"), "entrega_notas", ["vendedor_id"])

    op.create_table(
        "entrega_nota_itens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
        sa.Column("entrega_nota_id", sa.String(length=36), nullable=False),
        sa.Column("numero_item", sa.Integer(), nullable=False),
        sa.Column("produto_codigo", sa.String(length=40), nullable=False),
        sa.Column("produto_descricao", sa.String(length=255), nullable=False),
        sa.Column("marca_nome", sa.String(length=100), nullable=True),
        # Mesmas precisões da NF-e (qCom 4 casas, vUnCom 10). DECIMAL sem
        # parâmetros no MySQL é DECIMAL(10,0) e arredondaria em silêncio.
        sa.Column("quantidade", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("preco_unitario", sa.Numeric(precision=21, scale=10), nullable=False),
        sa.Column("valor_total", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("lote", sa.String(length=60), nullable=True),
        sa.Column("validade", sa.Date(), nullable=True),
        sa.Column("quantidade_devolvida", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("observacao", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["entrega_nota_id"], ["entrega_notas.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entrega_nota_id", "numero_item", name="uq_entrega_nota_itens_numero"
        ),
    )
    op.create_index(
        op.f("ix_entrega_nota_itens_entrega_nota_id"), "entrega_nota_itens", ["entrega_nota_id"]
    )

    op.create_table(
        "entrega_nota_interacoes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
        sa.Column("entrega_nota_id", sa.String(length=36), nullable=False),
        # A ordem do evento dentro da nota. Não dá para confiar em
        # sync_created_at para isso: DATETIME tem resolução de segundo, duas
        # interações no mesmo segundo empatam, e o desempate cairia no id
        # (UUID, aleatório) — fazendo "o último evento" ser sorteado.
        sa.Column("sequencia", sa.Integer(), nullable=False),
        # Slug fechado, não a frase exibida — o legado guardava "Em trânsito" e
        # "Devolucao parcial" na mesma coluna, com e sem acento.
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=False),
        # Antes era `usuario_alteracao varchar(5)`, texto solto sem FK.
        sa.Column("usuario_id", sa.String(length=36), nullable=False),
        sa.Column("editado_por_usuario_id", sa.String(length=36), nullable=True),
        sa.Column("editado_em", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["entrega_nota_id"], ["entrega_notas.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["editado_por_usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entrega_nota_id", "sequencia", name="uq_entrega_nota_interacoes_sequencia"
        ),
    )
    op.create_index(
        op.f("ix_entrega_nota_interacoes_entrega_nota_id"),
        "entrega_nota_interacoes",
        ["entrega_nota_id"],
    )
    op.create_index(
        op.f("ix_entrega_nota_interacoes_usuario_id"), "entrega_nota_interacoes", ["usuario_id"]
    )
    # A timeline ordena por data de CRIAÇÃO, não de alteração — editar um
    # evento antigo não pode empurrá-lo para o topo.
    op.create_index(
        "ix_entrega_nota_interacoes_criado", "entrega_nota_interacoes", ["sync_created_at"]
    )


def downgrade() -> None:
    # Ordem inversa da criação: as FKs apontam para cima.
    op.drop_table("entrega_nota_interacoes")
    op.drop_table("entrega_nota_itens")
    op.drop_table("entrega_notas")
    op.drop_table("entregas")
