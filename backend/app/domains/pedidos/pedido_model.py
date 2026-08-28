from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin


class Pedido(Base, IdMixin, SyncMixin):
    __tablename__ = "pedidos"
    __table_args__ = (
        # numero e sistema_origem_id não são mais únicos globalmente — são
        # únicos POR EMPRESA. Faz sentido porque cada empresa/filial numera
        # (e integra com sistemas externos) de forma independente; o mesmo
        # "PED-00001" pode existir em duas empresas diferentes sem colidir.
        UniqueConstraint("numero", "empresa_id", name="uq_pedidos_numero_empresa_id"),
        UniqueConstraint(
            "sistema_origem_id", "empresa_id", name="uq_pedidos_sistema_origem_id_empresa_id"
        ),
        # A listagem da expedição filtra por data do pedido e ordena por data de
        # alteração. Declarados aqui, e não como `index=True` na coluna, porque
        # sync_updated_at vem do SyncMixin — indexá-lo lá criaria o índice em
        # toda tabela do sistema, e só esta precisa.
        Index("ix_pedidos_data_pedido", "data_pedido"),
        Index("ix_pedidos_sync_updated_at", "sync_updated_at"),
    )

    # Sem índice próprio: `uq_pedidos_numero_empresa_id` já começa por `numero`,
    # e o MySQL usa o prefixo à esquerda de um índice composto. O mesmo vale
    # para sistema_origem_id abaixo. Os índices avulsos que existiam custavam
    # ~64 MB sem servir a nenhuma consulta que o composto não sirva.
    # NULLABLE de propósito. O número é o do ERP quando ele existe
    # (`sistema_origem_id`), e um sequencial daqui quando o pedido nasce na tela
    # — mas nem toda origem externa tem um número no momento em que o pedido
    # chega. Recusar a carga por causa disso perderia o pedido inteiro por um
    # campo que o remetente ainda vai preencher.
    #
    # Duas consequências que já estão tratadas: no MySQL dois NULL não colidem
    # num índice único, então `uq_pedidos_numero_empresa_id` não barra vários
    # pedidos sem número; e a busca por `numero ILIKE` simplesmente não casa com
    # NULL, que é o comportamento certo.
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    data_pedido: Mapped[date] = mapped_column(Date, nullable=False)
    # Quando o pedido foi liberado (ex: análise de crédito aprovada no ERP).
    # É um MILESTONE, não auditoria: marca o instante em que o pedido passou a
    # existir para o armazém, e é a partir dele que se mede o ciclo da
    # expedição. Nulo = ainda não liberado, que é informação legítima.
    #
    # Chega pela integração (`liberacaoDataHora` do ERP). Não é escrito por
    # nenhuma tela daqui — quem libera é o financeiro, do lado de lá.
    liberado_em: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)

    # cliente_id é FK real (o banco recusa id inexistente), mas o nome e o CNPJ
    # são SNAPSHOT: cópia do que o cliente era no momento da emissão. Não existe
    # relationship() aqui de propósito — pedidos não importa nada de
    # domains/clientes, e um pedido antigo não pode mudar porque o cadastro do
    # cliente mudou depois.
    cliente_id: Mapped[str] = mapped_column(ForeignKey("clientes.id"), nullable=False, index=True)
    cliente_nome_fantasia: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    cliente_cnpj: Mapped[str] = mapped_column(String(18), nullable=False, default="")

    # empresa_id é FK real (cadastro vivo, não snapshot) — identifica de qual
    # empresa/filial o pedido é. Diferente de cliente_id acima, não tem
    # colunas de snapshot porque a empresa do pedido não é um dado que se
    # imprime numa nota fiscal antiga; é só um vínculo organizacional.
    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)

    # Vendedor é o usuário responsável pelo pedido — vínculo vivo (não
    # snapshot) com domains/usuarios, resolvido via usuario_publico.py
    # (ver "Regras de import entre domínios" no ARCHITECTURE.md do backend).
    vendedor_id: Mapped[str | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)

    # Ver comentário em `numero`: coberto por uq_pedidos_sistema_origem_id_empresa_id.
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Só existe UM status por pedido — é o próprio pedido que aponta pro
    # catálogo (status_id -> pedido_status.id), não o contrário. A tabela
    # pedido_status é um catálogo fixo (rascunho/enviado/aprovado/recusado),
    # não uma linha por pedido.
    status_id: Mapped[str] = mapped_column(ForeignKey("pedido_status.id"), nullable=False, index=True)
    observacoes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    itens: Mapped[list["PedidoItem"]] = relationship(
        back_populates="pedido",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PedidoItem.sync_created_at",
    )
    status: Mapped["PedidoStatus"] = relationship(lazy="joined")


class PedidoItem(Base, IdMixin, SyncMixin):
    __tablename__ = "pedido_itens"
    __table_args__ = (
        # A identidade da linha do pedido. O endereço NÃO entra: ele é onde a
        # mercadoria está guardada no nosso galpão, não o que o cliente comprou.
        # Um lote se espalha por vários endereços de verdade, mas isso é assunto
        # da separação — nos ERPs grandes a linha do pedido nem tem endereço.
        #
        # Foi a falta desta constraint que deixou entrar 90 linhas duplicadas:
        # a consulta da integração cruzava a linha do pedido com o estoque por
        # endereço e devolvia uma linha por endereço, cada uma carregando a
        # quantidade INTEIRA (ver a migração c9e4a71f5b38).
        #
        # Buraco conhecido: no MySQL dois NULL não colidem num unique, então
        # item sem lote escapa da constraint. Quem barra esse caso é
        # `itens_sem_linha_duplicada` no contrato, onde None == None. Hoje não
        # existe nenhuma linha sem lote no banco.
        UniqueConstraint(
            "pedido_id", "produto_id", "lote", name="uq_pedido_itens_pedido_produto_lote"
        ),
    )

    pedido_id: Mapped[str] = mapped_column(
        ForeignKey("pedidos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produto_id: Mapped[str] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)

    produto_codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    produto_descricao: Mapped[str] = mapped_column(String(255), nullable=False)

    quantidade: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    preco_unitario: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    # O lote é do NEGÓCIO: é ele que o cliente recebe, e é ele que a
    # rastreabilidade sanitária cobra da nota fiscal. Por isso fica aqui.
    #
    # O ENDEREÇO não fica, e essa é a diferença. Endereço é onde a mercadoria
    # está guardada no nosso galpão — informação nossa, do estoque, não do que
    # o cliente comprou. Ele mora em `estoque_enderecos` /
    # `estoque_endereco_lote` (domínio `enderecamento`), amarrado ao LOTE, e a
    # expedição chega nele partindo do par (produto, lote) desta linha.
    #
    # Havia uma coluna `endereco_produto` aqui, e ela era uma mentira de
    # cardinalidade: um lote está em vários endereços, e espremer isso num
    # campo só fazia a consulta da integração devolver uma linha de pedido por
    # endereço, cada uma com a quantidade inteira. Ver a migração c9e4a71f5b38.
    lote: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Como o ERP identifica esta linha: empresa + pedido + produto. É a chave
    # natural de lá, e são as TRÊS juntas que apontam para uma linha só —
    # nenhuma sozinha serve, porque cada empresa/filial numera pedido de forma
    # independente e o mesmo produto se repete em pedidos diferentes.
    #
    # Guardar o trio aqui (em vez de chegar na empresa e no pedido pela FK
    # `pedido_id`) é o que permite localizar o item direto pelo que o ERP
    # conhece, sem ter que resolver a capa antes.
    #
    # Note que o trio é como o ERP CHAMA esta linha, não a identidade dela aqui
    # dentro: quem identifica a linha é `uq_pedido_itens_pedido_produto_lote`,
    # acima. Por isso as três não têm índice próprio — nenhuma consulta parte
    # delas hoje (abstrai por dor).
    #
    # Repare que NÃO existe uma coluna `sistema_origem_id` nesta tabela, ao
    # contrário de `pedidos`, `produtos` e `empresas`. É deliberado: naquelas,
    # o nome significa "o id da própria linha no ERP", e a linha do item não
    # tem um id próprio de lá — ela é identificada pelo trio. Uma coluna com
    # aquele nome guardando o código do produto faria o mesmo nome significar
    # duas coisas diferentes no mesmo projeto.
    #
    # Todas nullable: item lançado pela tela não vem de sistema nenhum.
    empresa_sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pedido_sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    produto_sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    pedido: Mapped["Pedido"] = relationship(back_populates="itens")


class PedidoStatus(Base, IdMixin, SyncMixin):
    """
    Catálogo fixo dos status possíveis de um pedido (rascunho, enviado,
    aprovado, recusado — ver StatusPedido em pedido_contrato.py). É o
    pedido que referencia uma linha daqui (Pedido.status_id), nunca o
    contrário: um pedido tem exatamente um status, então não faz sentido
    a tabela de status guardar um pedido_id apontando de volta.

    Antes era uma tabela legada que localizava o pedido por
    `(empresa_id, pedido)` em texto solto, e depois virou (por engano) uma
    tabela 1:1 com `pedido_id`, que nunca chegou a ser usada por nenhum
    service — o texto do status ficava direto em `Pedido.status`,
    divergindo dessa tabela. Esta é a correção: uma tabela só, um dono só.
    """

    __tablename__ = "pedido_status"

    chave: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
