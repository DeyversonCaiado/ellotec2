from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin

# `estoque_lotes` é tabela do domínio `estoque`. A FK abaixo aponta pra ela só
# pelo nome — nenhum model de lá é importado aqui, e nenhum service daqui
# escreve lá (ver ARCHITECTURE.md → "Regras de import entre domínios").


class EstoqueEndereco(Base, IdMixin, SyncMixin):
    """Um lugar físico do galpão: rua, prédio, nível, apartamento — o que o
    operador lê na etiqueta da prateleira ("07-14-08-03-01").

    É cadastro, não documento: a descrição é o nome do lugar, e ele continua o
    mesmo depois que a mercadoria sai.
    """

    __tablename__ = "estoque_enderecos"
    __table_args__ = (
        # O mesmo código de endereço existe em cada filial (toda uma tem a rua
        # 07), então quem identifica é o par com a empresa, não a descrição.
        UniqueConstraint("empresa_id", "descricao", name="uq_estoque_enderecos_empresa_descricao"),
    )

    descricao: Mapped[str] = mapped_column(String(100), nullable=False)

    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    empresa_sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class EstoqueEnderecoLote(Base, IdMixin, SyncMixin):
    """Onde cada lote está guardado — a tabela de ligação entre endereço e lote.

    Existe como tabela própria (e não como uma coluna `endereco` no lote ou na
    linha do pedido) porque a relação é muitos-para-muitos de verdade: o mesmo
    lote se espalha por vários endereços, e o mesmo endereço guarda lotes de
    produtos diferentes. Foi justamente confundir isso com um campo só que
    encheu `pedido_itens` de linhas repetidas — uma por endereço, cada uma
    carregando a quantidade inteira (ver a migração c9e4a71f5b38).
    """

    __tablename__ = "estoque_endereco_lote"
    __table_args__ = (
        UniqueConstraint(
            "estoque_enderecos_id",
            "estoque_lotes_id",
            name="uq_estoque_endereco_lote_endereco_lote",
        ),
    )

    estoque_enderecos_id: Mapped[str] = mapped_column(
        ForeignKey("estoque_enderecos.id"), nullable=False, index=True
    )
    estoque_lotes_id: Mapped[str] = mapped_column(
        ForeignKey("estoque_lotes.id"), nullable=False, index=True
    )

    # Quanto daquele lote está NESTE endereço. É o saldo que a expedição mostra
    # item a item e do qual ela baixa ao finalizar a separação.
    #
    # Repare que `estoque_lotes.quantidade` é o total do lote na empresa e este
    # é o mesmo saldo repartido pelos endereços — a soma daqui deveria fechar
    # com lá. Não existe constraint que force isso: as duas informações chegam
    # da integração em momentos diferentes, e recusar a segunda porque a
    # primeira ainda não chegou travaria a carga inteira. Quem cobra a diferença
    # é a consistência da expedição, na hora de iniciar o processo.
    #
    # Mesma precisão de `estoque_lotes`: produto vendido em quilo ou metro tem
    # saldo fracionado, e arredondar aqui perderia mercadoria.
    quantidade: Mapped[float] = mapped_column(
        Numeric(14, 3), nullable=False, default=0, server_default="0"
    )

    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    empresa_sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
