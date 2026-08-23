"""adiciona campos de endereco, codigo, status e renomeia cnpj para cpf_cnpj em clientes

Revision ID: 5842cb829e35
Revises: 25a4ba40be2f
Create Date: 2026-08-13 22:47:25.362915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '5842cb829e35'
down_revision: Union[str, Sequence[str], None] = '25a4ba40be2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nota: o autogenerate também detectou drift preexistente e não relacionado
    # (tipo de cidades.id, índices de usuarios) — removido manualmente desta
    # revisão para manter o escopo só nos novos campos de clientes.
    op.add_column('clientes', sa.Column('codigo', sa.String(length=10), nullable=True))
    op.add_column('clientes', sa.Column('cpf_cnpj', sa.String(length=18), nullable=False))
    op.add_column('clientes', sa.Column('celular', sa.String(length=50), nullable=True))
    op.add_column('clientes', sa.Column('logradouro', sa.String(length=255), nullable=True))
    op.add_column('clientes', sa.Column('numero', sa.String(length=50), nullable=True))
    op.add_column('clientes', sa.Column('complemento', sa.String(length=255), nullable=True))
    op.add_column('clientes', sa.Column('bairro', sa.String(length=100), nullable=True))
    op.add_column('clientes', sa.Column('cep', sa.String(length=10), nullable=True))
    op.add_column('clientes', sa.Column('status', sa.String(length=20), nullable=True))
    op.alter_column('clientes', 'email',
               existing_type=mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=180),
               type_=sa.String(length=255),
               nullable=True)
    op.drop_index(op.f('ix_clientes_cnpj'), table_name='clientes')
    op.create_index(op.f('ix_clientes_cpf_cnpj'), 'clientes', ['cpf_cnpj'], unique=True)
    op.drop_column('clientes', 'cnpj')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('clientes', sa.Column('cnpj', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=18), nullable=False))
    op.drop_index(op.f('ix_clientes_cpf_cnpj'), table_name='clientes')
    op.create_index(op.f('ix_clientes_cnpj'), 'clientes', ['cnpj'], unique=True)
    op.alter_column('clientes', 'email',
               existing_type=sa.String(length=255),
               type_=mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=180),
               nullable=False)
    op.drop_column('clientes', 'status')
    op.drop_column('clientes', 'cep')
    op.drop_column('clientes', 'bairro')
    op.drop_column('clientes', 'complemento')
    op.drop_column('clientes', 'numero')
    op.drop_column('clientes', 'logradouro')
    op.drop_column('clientes', 'celular')
    op.drop_column('clientes', 'cpf_cnpj')
    op.drop_column('clientes', 'codigo')
