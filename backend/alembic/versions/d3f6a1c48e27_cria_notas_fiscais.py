"""notas_fiscais: cria as tabelas de documento fiscal (entradas e saidas)

Revision ID: d3f6a1c48e27
Revises: c2f7a4e18b93
Create Date: 2026-08-23 00:00:00.000000

Uma tabela só para entrada e saída: o que distingue as duas é `tipo_operacao`,
não a estrutura — é o mesmo documento visto dos dois lados. `modelo` guarda o
leiaute de origem ('55', '65', '57', 'NFSE') para que a nota de serviço caiba
aqui amanhã sem renomear coluna nenhuma.

O XML autorizado é gravado em LONGTEXT, e não TEXT: uma NF-e com muitos itens
passa dos 64 KB do TEXT e seria truncada no MySQL — documento fiscal corrompido
em silêncio, justamente o que a coluna existe para evitar.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = "d3f6a1c48e27"
down_revision: Union[str, Sequence[str], None] = "c2f7a4e18b93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mesmo tipo declarado em nota_fiscal_model.XmlLongo — LONGTEXT no MySQL, TEXT
# em qualquer outro banco.
_XML_LONGO = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")


def upgrade() -> None:
    op.create_table(
        "notas_fiscais",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
        sa.Column("empresa_id", sa.String(length=36), nullable=False),
        # Nullable: toda nota de ENTRADA (e as de devolução, remessa e
        # transferência) nasce sem pedido deste lado.
        sa.Column("pedido_id", sa.String(length=36), nullable=True),
        # --- Identificação do documento ---
        sa.Column("modelo", sa.String(length=5), nullable=False),
        sa.Column("tipo_operacao", sa.String(length=10), nullable=False),
        sa.Column("finalidade", sa.String(length=20), nullable=True),
        sa.Column("chave_acesso", sa.String(length=44), nullable=True),
        sa.Column("numero", sa.String(length=20), nullable=False),
        sa.Column("serie", sa.String(length=5), nullable=False),
        sa.Column("natureza_operacao", sa.String(length=60), nullable=False),
        sa.Column("data_emissao", sa.DateTime(), nullable=False),
        sa.Column("data_saida_entrada", sa.DateTime(), nullable=True),
        # --- Situação na SEFAZ ---
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("protocolo_autorizacao", sa.String(length=20), nullable=True),
        sa.Column("data_autorizacao", sa.DateTime(), nullable=True),
        # --- Emitente e destinatário (snapshot) ---
        sa.Column("emitente_cnpj_cpf", sa.String(length=18), nullable=False),
        sa.Column("emitente_razao_social", sa.String(length=200), nullable=False),
        sa.Column("emitente_nome_fantasia", sa.String(length=150), nullable=True),
        sa.Column("emitente_inscricao_estadual", sa.String(length=20), nullable=True),
        sa.Column("emitente_municipio", sa.String(length=100), nullable=True),
        sa.Column("emitente_uf", sa.String(length=2), nullable=True),
        sa.Column("destinatario_cnpj_cpf", sa.String(length=18), nullable=False),
        sa.Column("destinatario_razao_social", sa.String(length=200), nullable=False),
        sa.Column("destinatario_inscricao_estadual", sa.String(length=20), nullable=True),
        sa.Column("destinatario_municipio", sa.String(length=100), nullable=True),
        sa.Column("destinatario_uf", sa.String(length=2), nullable=True),
        # --- Totais ---
        sa.Column("valor_produtos", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("valor_frete", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("valor_seguro", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("valor_desconto", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("valor_outras_despesas", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("valor_icms", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("valor_ipi", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("valor_total", sa.Numeric(precision=15, scale=2), nullable=False),
        # --- Transporte e volumes ---
        sa.Column("transportadora_nome", sa.String(length=200), nullable=True),
        sa.Column("transportadora_cnpj_cpf", sa.String(length=18), nullable=True),
        sa.Column("modalidade_frete", sa.String(length=20), nullable=True),
        sa.Column("quantidade_volumes", sa.Integer(), nullable=True),
        sa.Column("peso_bruto", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("peso_liquido", sa.Numeric(precision=12, scale=3), nullable=True),
        # --- Integração e documento original ---
        sa.Column("sistema_origem_id", sa.String(length=100), nullable=True),
        sa.Column("informacoes_complementares", sa.Text(), nullable=True),
        sa.Column("xml_original", _XML_LONGO, nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.ForeignKeyConstraint(["pedido_id"], ["pedidos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chave_acesso", "empresa_id", name="uq_notas_fiscais_chave_empresa_id"),
        sa.UniqueConstraint(
            "empresa_id",
            "modelo",
            "serie",
            "numero",
            "emitente_cnpj_cpf",
            name="uq_notas_fiscais_documento",
        ),
    )
    op.create_index("ix_notas_fiscais_data_emissao", "notas_fiscais", ["data_emissao"])
    op.create_index(
        "ix_notas_fiscais_empresa_tipo", "notas_fiscais", ["empresa_id", "tipo_operacao"]
    )
    op.create_index("ix_notas_fiscais_sync_updated_at", "notas_fiscais", ["sync_updated_at"])
    op.create_index(op.f("ix_notas_fiscais_empresa_id"), "notas_fiscais", ["empresa_id"])
    op.create_index(op.f("ix_notas_fiscais_pedido_id"), "notas_fiscais", ["pedido_id"])
    op.create_index(op.f("ix_notas_fiscais_emitente_cnpj_cpf"), "notas_fiscais", ["emitente_cnpj_cpf"])
    op.create_index(
        op.f("ix_notas_fiscais_destinatario_cnpj_cpf"), "notas_fiscais", ["destinatario_cnpj_cpf"]
    )
    op.create_index(op.f("ix_notas_fiscais_sistema_origem_id"), "notas_fiscais", ["sistema_origem_id"])

    op.create_table(
        "nota_fiscal_itens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sync_created_at", sa.DateTime(), nullable=False),
        sa.Column("sync_updated_at", sa.DateTime(), nullable=False),
        sa.Column("sync_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.Column("sync_synced_at", sa.DateTime(), nullable=True),
        sa.Column("nota_fiscal_id", sa.String(length=36), nullable=False),
        sa.Column("numero_item", sa.Integer(), nullable=False),
        # Nullable: numa nota de entrada o produto é do fornecedor e pode não
        # existir no cadastro daqui. Ver comentário em nota_fiscal_model.py.
        sa.Column("produto_id", sa.String(length=36), nullable=True),
        sa.Column("produto_codigo", sa.String(length=40), nullable=False),
        sa.Column("produto_descricao", sa.String(length=255), nullable=False),
        sa.Column("codigo_barras", sa.String(length=20), nullable=True),
        sa.Column("ncm", sa.String(length=8), nullable=True),
        sa.Column("cfop", sa.String(length=4), nullable=True),
        sa.Column("unidade", sa.String(length=6), nullable=False),
        # 4 casas em quantidade e 10 em preço unitário porque é o que o leiaute
        # da NF-e define (qCom 11v0-4, vUnCom 11v0-10). Precisão implícita não
        # existe no MySQL: DECIMAL sem parâmetros é DECIMAL(10, 0).
        sa.Column("quantidade", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("preco_unitario", sa.Numeric(precision=21, scale=10), nullable=False),
        sa.Column("valor_total_item", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("valor_frete", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("valor_desconto", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("cst_icms", sa.String(length=3), nullable=True),
        sa.Column("aliquota_icms", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("valor_icms", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("valor_icms_st", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("cst_ipi", sa.String(length=3), nullable=True),
        sa.Column("aliquota_ipi", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("valor_ipi", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("lote", sa.String(length=60), nullable=True),
        sa.Column("validade", sa.Date(), nullable=True),
        sa.Column("informacoes_adicionais", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["nota_fiscal_id"], ["notas_fiscais.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["produto_id"], ["produtos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nota_fiscal_id", "numero_item", name="uq_nota_fiscal_itens_numero"),
    )
    op.create_index(
        op.f("ix_nota_fiscal_itens_nota_fiscal_id"), "nota_fiscal_itens", ["nota_fiscal_id"]
    )
    op.create_index(op.f("ix_nota_fiscal_itens_produto_id"), "nota_fiscal_itens", ["produto_id"])
    op.create_index(op.f("ix_nota_fiscal_itens_codigo_barras"), "nota_fiscal_itens", ["codigo_barras"])


def downgrade() -> None:
    # Itens primeiro: a FK aponta para notas_fiscais.
    op.drop_table("nota_fiscal_itens")
    op.drop_table("notas_fiscais")
