from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.conexao import Base
from app.domains.marcas.marca_model import Marca
from app.shared.sync_mixin import IdMixin, SyncMixin


class Produto(Base, IdMixin, SyncMixin):
    __tablename__ = "produtos"

    codigo: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    unidade: Mapped[str] = mapped_column(String(10), nullable=False, default="UN")
    # O código de barras que vem no cadastro do ERP e sai impresso na nota — é a
    # coluna CODIGO_BARRA de `fat_produtos` espelhada aqui. É um só, porque lá é
    # um só. Os códigos que o coletor lê no galpão são outros e moram em
    # `produto_codigo_barras` (ver ProdutoCodigoBarras abaixo).
    #
    # Indexado mas NÃO único: cadastros duplicados vindos de integração podem
    # repetir o mesmo EAN, e uma constraint única faria a importação quebrar.
    codigo_barra_notas: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    # DUN-14 (GTIN-14): o código da embalagem de despacho, o que vem impresso na
    # caixa fechada. Mesma justificativa de índice sem unique acima — a expedição
    # procura por ele quando nenhum dos outros códigos resolve.
    dun_14: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    # Quantas unidades entram numa embalagem de venda. O estoque é sempre em
    # unidade, mas há produto que só se vende pela caixa fechada: um bipe no
    # coletor vale essa quantidade, não 1 (ver expedicao_service.bipar).
    # Default 1 = produto vendido na unidade, que é o caso da maioria.
    quantidade_multipla_venda: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # Registro do produto na ANVISA. Texto e não número: o registro tem zeros à
    # esquerda que fazem parte dele, e há produto isento ou em processo de
    # renovação, cujo campo o cadastro do ERP preenche com texto livre.
    # Nullable porque nem todo item do catálogo é produto de saúde registrado.
    registro_anvisa: Mapped[str | None] = mapped_column(String(30), nullable=True, default=None)
    marca_id: Mapped[str] = mapped_column(ForeignKey("marcas.id"), nullable=False, index=True)
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    marca: Mapped[Marca] = relationship(lazy="joined")

    # `viewonly` porque quem insere e apaga linha é `produto_service`, que
    # precisa fazer soft delete (`marcar_apagado`) e não delete físico — se a
    # coleção fosse gravável, o SQLAlchemy apagaria a linha de verdade ao
    # removê-la da lista. O primaryjoin esconde as linhas já apagadas.
    codigos_barras_logistica: Mapped[list["ProdutoCodigoBarras"]] = relationship(
        primaryjoin=(
            "and_(Produto.id == ProdutoCodigoBarras.produto_id, "
            "ProdutoCodigoBarras.sync_deleted_at.is_(None))"
        ),
        order_by="ProdutoCodigoBarras.codigo",
        lazy="selectin",
        viewonly=True,
    )


class ProdutoCodigoBarras(Base, IdMixin, SyncMixin):
    """Os códigos de barras de logística do produto — uma linha por código.

    Existe porque o mesmo produto chega ao galpão com mais de um código impresso:
    caixa do fabricante, caixa do distribuidor, reembalagem, troca de fornecedor.
    Todos são o mesmo produto e todos precisam bipar. Um campo só na tabela
    `produtos` obrigava a escolher qual deles valia.

    Não tem correspondente no ERP: `fat_produtos` guarda um código só, que é o
    `produtos.codigo_barra_notas`. Esta tabela nasce e vive neste banco.
    """

    __tablename__ = "produto_codigo_barras"

    produto_id: Mapped[str] = mapped_column(
        ForeignKey("produtos.id"), nullable=False, index=True
    )
    # Índice sem unique, pela mesma razão dos outros códigos em `produtos`:
    # cadastro duplicado vindo de integração pode repetir o número, e recusar o
    # segundo quebraria a importação inteira por causa de uma linha.
    codigo: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
