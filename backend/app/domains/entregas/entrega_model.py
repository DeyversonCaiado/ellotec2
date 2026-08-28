from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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


class Entrega(Base, IdMixin, SyncMixin):
    """O mapa de carga: um despacho, várias notas dentro.

    É o `fat_mapadecarga` do ERP espelhado aqui. Chega pela API (o ERP faz
    POST) — este backend nunca consulta o Oracle do GESTCOM.

    A data do mapa é o marco zero do prazo de entrega: antes dela a mercadoria
    ainda não saiu, e nota sem mapa não tem como estar atrasada.
    """

    __tablename__ = "entregas"
    __table_args__ = (
        # Único POR EMPRESA, mesma razão de pedidos: cada filial numera o
        # próprio mapa de carga, e o mesmo número existe em duas delas.
        UniqueConstraint("empresa_id", "numero_mapa", name="uq_entregas_empresa_numero"),
        UniqueConstraint(
            "empresa_id", "sistema_origem_id", name="uq_entregas_empresa_sistema_origem"
        ),
        Index("ix_entregas_data_mapa", "data_mapa"),
    )

    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    numero_mapa: Mapped[str] = mapped_column(String(30), nullable=False)
    # Quando a carga foi despachada. Nullable porque o mapa pode ser criado no
    # ERP antes de fechar — e um mapa aberto é informação legítima.
    data_mapa: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)

    # Snapshot: a transportadora que levou ESTA carga. Se o cadastro dela mudar
    # de nome depois, o histórico do despacho não pode mudar junto.
    transportadora_nome: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    transportadora_cnpj: Mapped[str | None] = mapped_column(String(18), nullable=True, default=None)
    motorista: Mapped[str | None] = mapped_column(String(150), nullable=True, default=None)
    placa_veiculo: Mapped[str | None] = mapped_column(String(10), nullable=True, default=None)

    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)

    notas: Mapped[list["EntregaNota"]] = relationship(
        back_populates="entrega", lazy="selectin", order_by="EntregaNota.numero_nota"
    )


class EntregaNota(Base, IdMixin, SyncMixin):
    """Uma nota acompanhada pela gestão de entregas — em SNAPSHOT completo.

    Cliente, valor, itens: tudo copiado do que a API mandou, não lido de
    `notas_fiscais`. A decisão é deliberada: a integração de logística e a
    fiscal rodam em ritmos diferentes, e amarrar uma na outra faria a tela de
    entregas ficar vazia sempre que a sincronização fiscal atrasasse.

    A contrapartida assumida é que o mesmo documento existe em dois lugares.
    Por isso NADA aqui é fonte da verdade fiscal — quem responde sobre imposto,
    chave de acesso e XML é `notas_fiscais`. Esta tabela responde apenas sobre
    a ENTREGA daquela mercadoria.
    """

    __tablename__ = "entrega_notas"
    __table_args__ = (
        # A chave natural do documento na visão da logística. `serie` entra
        # aqui mesmo não existindo na tabela legada (migra como string vazia):
        # sem ela, duas notas de séries diferentes com o mesmo número colidem.
        UniqueConstraint(
            "empresa_id", "numero_nota", "serie", "pedido", name="uq_entrega_notas_documento"
        ),
        Index("ix_entrega_notas_data_nota", "data_nota"),
        Index("ix_entrega_notas_status_atual", "status_atual"),
        Index("ix_entrega_notas_sync_updated_at", "sync_updated_at"),
    )

    # Nullable: a nota é faturada antes de entrar num mapa de carga. Enquanto
    # não entra, ela existe aqui com status_prazo "sem_mapa" — que é
    # exatamente uma das situações que a tela precisa mostrar.
    entrega_id: Mapped[str | None] = mapped_column(
        ForeignKey("entregas.id"), nullable=True, default=None, index=True
    )
    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)

    numero_nota: Mapped[str] = mapped_column(String(20), nullable=False)
    serie: Mapped[str] = mapped_column(String(5), nullable=False, default="")
    pedido: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    # venda | bonificacao | devolucao_cliente | complementar | perda | outros —
    # a classificação que o SQL do sistema antigo montava por CFOP e status.
    tipo_nota: Mapped[str] = mapped_column(String(30), nullable=False, default="outros")
    data_nota: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)
    # Situação da nota no ERP (N1, NF, CP, Cancelada...). Texto livre de
    # propósito: é código do outro sistema, e fechar num enum aqui quebraria a
    # integração no dia em que o ERP criar um status novo.
    situacao: Mapped[str | None] = mapped_column(String(30), nullable=True, default=None)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)

    # A chave de acesso da NF-e, em SNAPSHOT como todo o resto desta tabela.
    # Não faz desta tabela fonte da verdade fiscal — quem responde por imposto,
    # XML e situação na SEFAZ continua sendo `notas_fiscais`. Aqui ela serve
    # para identificar o documento sem ambiguidade e para casar esta linha com
    # a nota fiscal correspondente quando alguém precisar cruzar os dois lados.
    #
    # 44 posições porque é o tamanho fixo definido pelo layout da NF-e (o mesmo
    # `String(44)` de `notas_fiscais.chave_acesso`), e nullable porque a
    # integração pode mandar a nota antes de a chave ser conhecida.
    chave_acesso_nota: Mapped[str | None] = mapped_column(String(44), nullable=True, default=None)
    # A chave da nota REFERENCIADA por esta. É o que amarra uma devolução ou uma
    # nota complementar ao documento de origem: sem ela, a devolução chega aqui
    # como um papel solto, e não dá para dizer qual entrega ela desfaz.
    chave_acesso_referenciada: Mapped[str | None] = mapped_column(
        String(44), nullable=True, default=None
    )

    cliente_codigo: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    cliente_nome: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    cliente_cidade: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    cliente_uf: Mapped[str | None] = mapped_column(String(2), nullable=True, default=None)

    # FK viva para usuarios: é por ela que o vendedor sem `entregas.ver_todas`
    # enxerga só as próprias notas. Nullable porque nem toda nota tem vendedor
    # (bonificação, transferência) e porque o código pode não existir aqui.
    vendedor_id: Mapped[str | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True, default=None, index=True
    )
    transportadora_nome: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)

    # Produto refrigerado tem SLA menor — entra no cálculo do prazo.
    termolabil: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # CONGELADOS quando o mapa de carga chega: são o prazo que valia naquele
    # dia. Recalcular depois mudaria o passado — se a tabela de SLA for
    # revisada, as entregas antigas continuam medidas pelo prazo prometido.
    prazo_dias: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    data_prevista_entrega: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)

    # Desnormalizado do último evento da timeline. O evento é a verdade; esta
    # coluna existe porque a listagem filtra por status sobre a base inteira, e
    # buscar o último evento de cada nota por subquery não escala.
    # Quem mantém em dia é o service, a cada interação registrada.
    status_atual: Mapped[str] = mapped_column(String(30), nullable=False, default="aguardando_embarque")
    data_entrega_realizada: Mapped[datetime | None] = mapped_column(
        DateTime(), nullable=True, default=None
    )

    sistema_origem_id: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)

    entrega: Mapped["Entrega | None"] = relationship(back_populates="notas")
    itens: Mapped[list["EntregaNotaItem"]] = relationship(
        back_populates="nota",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="EntregaNotaItem.numero_item",
    )
    interacoes: Mapped[list["EntregaNotaInteracao"]] = relationship(
        back_populates="nota",
        cascade="all, delete-orphan",
        lazy="selectin",
        # Mais recente primeiro, pela SEQUÊNCIA do evento — não por data de
        # alteração (editar não reordena) nem por data de criação (que empata
        # dentro do mesmo segundo). Ver a docstring de EntregaNotaInteracao.
        order_by="EntregaNotaInteracao.sequencia.desc()",
    )


class EntregaNotaItem(Base, IdMixin, SyncMixin):
    """Os produtos da nota, em snapshot, mais o que foi conferido na entrega."""

    __tablename__ = "entrega_nota_itens"
    __table_args__ = (
        UniqueConstraint("entrega_nota_id", "numero_item", name="uq_entrega_nota_itens_numero"),
    )

    entrega_nota_id: Mapped[str] = mapped_column(
        ForeignKey("entrega_notas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero_item: Mapped[int] = mapped_column(Integer, nullable=False)

    produto_codigo: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    produto_descricao: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    marca_nome: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)

    # Mesmas precisões da NF-e: quantidade com 4 casas, preço unitário com 10.
    # `Numeric()` sem parâmetros vira DECIMAL(10, 0) no MySQL e arredonda em
    # silêncio — e o SQLite dos testes não pegaria o erro.
    quantidade: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, default=0)
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(21, 10), nullable=False, default=0)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)

    lote: Mapped[str | None] = mapped_column(String(60), nullable=True, default=None)
    validade: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)

    # "Devolução parcial" é um dos status possíveis. Sem este campo dá para
    # dizer que houve devolução, mas não O QUÊ voltou — que é justamente o que
    # o cliente pergunta.
    quantidade_devolvida: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, default=0
    )
    observacao: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    nota: Mapped["EntregaNota"] = relationship(back_populates="itens")


class EntregaNotaInteracao(Base, IdMixin, SyncMixin):
    """Um evento na linha do tempo da entrega: status + observação + autor.

    A interação É EDITÁVEL — decisão de negócio: quem lança digita errado, e
    obrigar a lançar um segundo evento só para corrigir uma palavra sujaria a
    timeline mais do que a edição. Quem editou e quando fica registrado, e a
    tela mostra isso ao lado do card: corrigir texto é legítimo, corrigir texto
    em silêncio não é.

    A timeline ordena e exibe por `data_interacao`, um campo de NEGÓCIO — nunca
    pelos campos `sync_*`, que são auditoria da linha e não do fato (ver "Os
    campos sync_* nunca entram na regra de negócio" no ARCHITECTURE.md).
    """

    __tablename__ = "entrega_nota_interacoes"
    __table_args__ = (
        UniqueConstraint(
            "entrega_nota_id", "sequencia", name="uq_entrega_nota_interacoes_sequencia"
        ),
        Index("ix_entrega_nota_interacoes_data", "data_interacao"),
    )

    entrega_nota_id: Mapped[str] = mapped_column(
        ForeignKey("entrega_notas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # QUANDO O EVENTO ACONTECEU — campo de negócio, com coluna própria.
    #
    # Hoje nasce igual ao instante da inclusão, mas não é `sync_created_at`
    # disfarçado: é ele que a timeline ordena e exibe, e no dia em que a
    # interação puder ser lançada com data retroativa (ocorrência que a
    # transportadora informa dois dias depois), é aqui que a data real vai —
    # sem que a auditoria da linha precise mentir.
    #
    # Editar a interação NÃO altera este campo: corrigir o texto de ontem não
    # pode empurrar aquele evento para o topo de hoje.
    data_interacao: Mapped[datetime] = mapped_column(DateTime(), nullable=False, index=True)

    # A ordem do evento DENTRO da nota: 1, 2, 3... Existe porque `DATETIME` tem
    # resolução de SEGUNDO (tanto no MySQL quanto no SQLite dos testes), e duas
    # interações lançadas no mesmo segundo empatam em `data_interacao`. No
    # empate o desempate cairia no `id`, que é UUID — aleatório, não
    # cronológico —, e "o último evento" passaria a ser sorteado: o
    # `status_atual` da nota podia virar o do evento errado.
    sequencia: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Slug fechado (aguardando_embarque, em_transito, ...), não a frase. A
    # tabela legada guardava o texto exibido, com e sem acento na mesma coluna
    # ("Em trânsito" e "Devolucao parcial"), o que tornava o filtro por status
    # não confiável.
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    observacao: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # FK real. No sistema antigo isto era `usuario_alteracao varchar(5)` — o
    # código do funcionário em texto solto, sem garantia de existir.
    usuario_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    editado_por_usuario_id: Mapped[str | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True, default=None
    )
    editado_em: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)

    nota: Mapped["EntregaNota"] = relationship(back_populates="interacoes")
