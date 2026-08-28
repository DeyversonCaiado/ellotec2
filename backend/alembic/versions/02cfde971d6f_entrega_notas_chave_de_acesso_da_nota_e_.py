"""entrega_notas: chave de acesso da nota e da referenciada

Duas colunas novas em `entrega_notas`, ambas `VARCHAR(44)` e nullable:

- `chave_acesso_nota`: a chave de acesso da NF-e desta nota, em SNAPSHOT como
  todo o resto da tabela. Não faz de `entrega_notas` fonte da verdade fiscal —
  quem responde por imposto, XML e situação na SEFAZ continua sendo
  `notas_fiscais`. Serve para identificar o documento sem ambiguidade e para
  casar esta linha com a nota fiscal quando alguém precisar cruzar os dois lados.
- `chave_acesso_referenciada`: a chave da nota que ESTA referencia. É o que
  amarra uma devolução ou uma complementar ao documento de origem.

44 posições porque é o tamanho fixo do layout da NF-e — o mesmo `String(44)` de
`notas_fiscais.chave_acesso`. Nullable porque a integração pode mandar a nota
antes de a chave ser conhecida.

**Esta migração foi enxugada à mão, e isso é deliberado.** O `--autogenerate`
detectou, além das duas colunas, um conjunto de diferenças PREEXISTENTES entre
os models e o banco, sem relação nenhuma com esta mudança:

- `alter_column` em `cidades.id` (CHAR -> VARCHAR);
- `create_index ix_entrega_nota_interacoes_data_interacao`;
- `drop_index ix_expedicao_atribuicoes_usuario_vivas`;
- `drop_index usuario` em `usuarios`, com `create_index` de dois índices únicos
  no lugar.

Carregar isso junto faria uma migração de "adicionar duas colunas" derrubar um
índice único de `usuarios` — o tipo de efeito colateral que ninguém procura
quando algo quebra depois. A divergência continua lá e precisa ser tratada numa
migração própria, decidida item a item.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '02cfde971d6f'
down_revision: Union[str, Sequence[str], None] = 'f3b8d2e60a94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'entrega_notas', sa.Column('chave_acesso_nota', sa.String(length=44), nullable=True)
    )
    op.add_column(
        'entrega_notas',
        sa.Column('chave_acesso_referenciada', sa.String(length=44), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('entrega_notas', 'chave_acesso_referenciada')
    op.drop_column('entrega_notas', 'chave_acesso_nota')
