"""expedição: execução delegada — quem executou vs. quem gerenciou

Revision ID: b7e3a9d51c04
Revises: a4d9c2f70b13
Create Date: 2026-08-25 00:00:00.000000

O galpão nem sempre tem coletor para todo mundo. O gerente despacha uma pessoa
para separar no papel; quando ela termina, avisa, e o gerente registra o fim no
sistema. Até aqui não havia como gravar isso: `usuario_inicio_id` e
`usuario_fim_id` guardavam uma pessoa só, então ou o gerente aparecia como quem
separou (falso) ou o operador aparecia como quem operou o sistema (também
falso).

A separação é a mesma que qualquer sistema usa para "agir em nome de": o campo
que já existia continua sendo o SUJEITO (de quem é o trabalho — o operador
atribuído), e entra um campo novo para o ATOR (quem clicou). NULL no campo novo
significa que sujeito e ator são a mesma pessoa, que é o caso normal — por isso
não há backfill: toda linha existente foi mesmo aberta e fechada pelo próprio
operador.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b7e3a9d51c04"
down_revision: Union[str, Sequence[str], None] = "a4d9c2f70b13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABELAS = ("expedicao_separacoes", "expedicao_conferencias")
_COLUNAS = ("usuario_gestor_inicio_id", "usuario_gestor_fim_id")


def upgrade() -> None:
    for tabela in _TABELAS:
        for coluna in _COLUNAS:
            op.add_column(tabela, sa.Column(coluna, sa.String(length=36), nullable=True))
            op.create_index(f"ix_{tabela}_{coluna}", tabela, [coluna])
            op.create_foreign_key(
                f"fk_{tabela}_{coluna}", tabela, "usuarios", [coluna], ["id"]
            )


def downgrade() -> None:
    for tabela in _TABELAS:
        for coluna in _COLUNAS:
            op.drop_constraint(f"fk_{tabela}_{coluna}", tabela, type_="foreignkey")
            op.drop_index(f"ix_{tabela}_{coluna}", table_name=tabela)
            op.drop_column(tabela, coluna)
