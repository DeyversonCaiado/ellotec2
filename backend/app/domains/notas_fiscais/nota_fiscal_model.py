from datetime import date, datetime
from decimal import Decimal

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
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin

# O XML autorizado de uma NF-e com muitos itens passa de 64 KB, que é o teto do
# TEXT no MySQL — um INSERT acima disso é truncado (ou recusado em modo estrito),
# e o documento fiscal fica corrompido em silêncio. LONGTEXT resolve com folga.
# O `with_variant` mantém TEXT puro no SQLite dos testes, que não tem esse limite
# e não conhece LONGTEXT.
XmlLongo = Text().with_variant(mysql.LONGTEXT(), "mysql")


class NotaFiscal(Base, IdMixin, SyncMixin):
    """Documento fiscal — entrada e saída na MESMA tabela.

    O que distingue uma da outra não é a estrutura, é quem emitiu:
    `tipo_operacao='saida'` quando o emitente é a sua empresa (você vendeu),
    `'entrada'` quando o emitente é o fornecedor (compra de mercadoria). É
    literalmente o mesmo documento visto dos dois lados — separar em duas
    tabelas duplicaria 100% do schema para variar uma coluna.

    Nenhum campo cita "NFe" no nome, de propósito: `modelo` diz qual leiaute
    originou a linha ('55' NF-e, '65' NFC-e, '57' CT-e, 'NFSE' nota de
    serviço), e todo campo aqui é conceito de negócio que existe nos quatro.
    O que é específico de um leiaute não vira coluna — fica no `xml_original`.

    Esta tabela guarda o DOCUMENTO, não o PROCESSO. Pedido de compra, título a
    pagar e entrada de estoque são outros domínios (nenhum existe hoje); nota
    de devolução, remessa e bonificação também são entradas e não geram compra
    nenhuma. Ver "Regras de import entre domínios" no ARCHITECTURE.md.
    """

    __tablename__ = "notas_fiscais"
    __table_args__ = (
        # A chave de acesso é única na SEFAZ, mas aqui a unicidade é POR
        # EMPRESA — mesma razão de `uq_pedidos_numero_empresa_id`: cada
        # empresa/filial guarda a sua própria cópia do documento e integra com
        # o ERP de forma independente. Coluna nullable: NFS-e não tem chave de
        # 44 dígitos, e o MySQL permite NULL repetido em constraint única.
        UniqueConstraint("chave_acesso", "empresa_id", name="uq_notas_fiscais_chave_empresa_id"),
        # A chave natural de QUALQUER documento fiscal, inclusive os que não
        # têm chave de acesso. É ela que impede a mesma nota de ser importada
        # duas vezes quando `modelo='NFSE'`.
        UniqueConstraint(
            "empresa_id",
            "modelo",
            "serie",
            "numero",
            "emitente_cnpj_cpf",
            name="uq_notas_fiscais_documento",
        ),
        # A listagem filtra por período de EMISSÃO (data de negócio, nunca
        # sync_updated_at) e separa entrada de saída; ordena por data de
        # alteração. Declarados aqui, e não como `index=True` na coluna, pelo
        # mesmo motivo de pedidos: sync_updated_at vem do SyncMixin, e indexá-lo
        # lá criaria o índice em toda tabela do sistema.
        Index("ix_notas_fiscais_data_emissao", "data_emissao"),
        Index("ix_notas_fiscais_empresa_tipo", "empresa_id", "tipo_operacao"),
        Index("ix_notas_fiscais_sync_updated_at", "sync_updated_at"),
    )

    # empresa_id é FK real (cadastro vivo, não snapshot): diz de qual
    # empresa/filial SUA é esta nota. Mesmo tratamento que em pedidos.
    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)

    # O pedido que originou a nota. FK real, mas NULLABLE e sem relationship():
    #
    # - nullable porque a maioria das notas não tem pedido nenhum deste lado —
    #   toda nota de ENTRADA (compra do fornecedor) e as de devolução, remessa
    #   e transferência nascem sem pedido daqui;
    # - sem relationship() porque notas_fiscais não importa nada de
    #   domains/pedidos. É só a referência: quem precisar exibir o pedido
    #   pergunta ao dono dele por `pedido_publico.py` (ver "Regras de import
    #   entre domínios" no ARCHITECTURE.md). O id inexistente quem recusa é a
    #   própria FK, no INSERT.
    pedido_id: Mapped[str | None] = mapped_column(
        ForeignKey("pedidos.id"), nullable=True, default=None, index=True
    )

    # --- Identificação do documento ---
    # Texto e não inteiro: '55', '65', '57', 'NFSE'. O modelo é um código, não
    # um número — nunca se soma nem se ordena por ele.
    modelo: Mapped[str] = mapped_column(String(5), nullable=False, default="55")
    # 'entrada' | 'saida' — ver docstring da classe.
    tipo_operacao: Mapped[str] = mapped_column(String(10), nullable=False)
    # finNFe traduzido: 'normal' | 'complementar' | 'ajuste' | 'devolucao'.
    # Nullable porque nem todo modelo de documento declara finalidade.
    finalidade: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    chave_acesso: Mapped[str | None] = mapped_column(String(44), nullable=True, default=None)
    numero: Mapped[str] = mapped_column(String(20), nullable=False)
    serie: Mapped[str] = mapped_column(String(5), nullable=False, default="")
    natureza_operacao: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    data_emissao: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    # dhSaiEnt — quando a mercadoria efetivamente saiu/entrou. Nullable porque
    # o emitente não é obrigado a informar, e frequentemente não informa.
    data_saida_entrada: Mapped[datetime | None] = mapped_column(
        DateTime(), nullable=True, default=None
    )

    # --- Situação na SEFAZ ---
    # 'autorizada' | 'cancelada' | 'denegada' | 'rejeitada' — traduzido do
    # cStat do protocolo, não o código cru: '100' não significa nada para quem
    # lê a tela, e o código original continua no xml_original.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="autorizada")
    protocolo_autorizacao: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )
    data_autorizacao: Mapped[datetime | None] = mapped_column(
        DateTime(), nullable=True, default=None
    )

    # --- Emitente e destinatário: SNAPSHOT, não FK ---
    # Nota fiscal é fato histórico. Se o fornecedor mudar de razão social em
    # 2030, a nota de 2026 continua tendo que mostrar o nome que estava impresso
    # nela. Por isso não existe fornecedor_id/cliente_id aqui com relationship()
    # — o vínculo com o cadastro, quando alguém precisar, se faz pelo CNPJ.
    emitente_cnpj_cpf: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    emitente_razao_social: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    emitente_nome_fantasia: Mapped[str | None] = mapped_column(
        String(150), nullable=True, default=None
    )
    emitente_inscricao_estadual: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )
    emitente_municipio: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    emitente_uf: Mapped[str | None] = mapped_column(String(2), nullable=True, default=None)

    destinatario_cnpj_cpf: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    destinatario_razao_social: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    destinatario_inscricao_estadual: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )
    destinatario_municipio: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    destinatario_uf: Mapped[str | None] = mapped_column(String(2), nullable=True, default=None)

    # --- Totais ---
    # Dinheiro é SEMPRE Numeric(15, 2) com precisão explícita. `Numeric()` sem
    # argumentos vira DECIMAL(10, 0) no MySQL — zero casas decimais — e grava o
    # valor arredondado com um simples warning, sem falhar o INSERT. Como os
    # testes rodam em SQLite, que ignora precisão de DECIMAL, esse tipo de erro
    # passa verde no teste e só aparece em produção.
    valor_produtos: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    valor_frete: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    valor_seguro: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    valor_desconto: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    valor_outras_despesas: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=0
    )
    valor_icms: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    valor_ipi: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)

    # --- Transporte e volumes ---
    # Existe porque no recebimento de compra alguém confere "chegaram mesmo os
    # 43 volumes?" — é o único uso operacional do grupo <transp> hoje.
    transportadora_nome: Mapped[str | None] = mapped_column(
        String(200), nullable=True, default=None
    )
    transportadora_cnpj_cpf: Mapped[str | None] = mapped_column(
        String(18), nullable=True, default=None
    )
    # modFrete traduzido: 'emitente' | 'destinatario' | 'terceiros' | 'sem_frete'.
    modalidade_frete: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    quantidade_volumes: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    peso_bruto: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True, default=None)
    peso_liquido: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3), nullable=True, default=None
    )

    # --- Integração e documento original ---
    sistema_origem_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None, index=True
    )
    informacoes_complementares: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    # O XML inteiro, como veio. Guardar é obrigação legal (5 anos) e é o que
    # permite NÃO modelar como coluna tudo que a tela não usa: PIS, COFINS,
    # IBS, CBS, gRed, duplicatas, assinatura. No dia em que o contador pedir um
    # relatório desses, cria-se a tabela e reprocessa-se o que já está aqui —
    # em vez de descobrir que o dado nunca foi guardado.
    #
    # Fica nesta tabela, e não numa `nota_fiscal_xml` separada, porque hoje o
    # volume não dói (ver princípio nº 3 do ARCHITECTURE.md). Se doer, a coluna
    # vira tabela — e o `deferred` já garante que nenhuma listagem carrega
    # esses KBs por engano: o SELECT só busca a coluna se alguém pedir por ela.
    xml_original: Mapped[str | None] = mapped_column(
        XmlLongo, nullable=True, default=None, deferred=True
    )

    itens: Mapped[list["NotaFiscalItem"]] = relationship(
        back_populates="nota_fiscal",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="NotaFiscalItem.numero_item",
    )


class NotaFiscalItem(Base, IdMixin, SyncMixin):
    __tablename__ = "nota_fiscal_itens"
    __table_args__ = (
        UniqueConstraint("nota_fiscal_id", "numero_item", name="uq_nota_fiscal_itens_numero"),
    )

    nota_fiscal_id: Mapped[str] = mapped_column(
        ForeignKey("notas_fiscais.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # nItem — a ordem do item DENTRO da nota, definida pelo emitente. Não é
    # sequência nossa: é por ele que se confere a nota item a item com o
    # fornecedor, então repetir o mesmo número na mesma nota é erro de parser.
    numero_item: Mapped[int] = mapped_column(Integer, nullable=False)

    # NULLABLE de propósito. Numa nota de entrada o produto é do fornecedor e
    # pode simplesmente não existir no seu cadastro — recusar a nota inteira
    # por causa disso impediria de guardar um documento fiscal que você é
    # obrigado a guardar. O vínculo é feito depois, quando (e se) alguém
    # cadastrar o produto.
    produto_id: Mapped[str | None] = mapped_column(
        ForeignKey("produtos.id"), nullable=True, default=None, index=True
    )

    # Snapshot do que veio na nota — nunca lido do cadastro de produtos. A
    # descrição impressa na nota de 2026 é a daquela data, não a de hoje.
    produto_codigo: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    produto_descricao: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    codigo_barras: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None, index=True
    )
    ncm: Mapped[str | None] = mapped_column(String(8), nullable=True, default=None)
    cfop: Mapped[str | None] = mapped_column(String(4), nullable=True, default=None)
    unidade: Mapped[str] = mapped_column(String(6), nullable=False, default="UN")

    # Diferente de `pedido_itens.quantidade`, que é Integer: a NF-e permite até
    # 4 casas decimais em qCom, e há item vendido em KG/L/M.
    quantidade: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, default=0)
    # 10 casas decimais porque é o que o leiaute da NF-e define para vUnCom
    # (11v0-10) — não porque o XML de hoje use todas. Escolher a escala pelo que
    # aparece num XML de exemplo é o caminho para truncar valor em silêncio no
    # primeiro fornecedor que usar mais casas, e aí o somatório dos itens deixa
    # de bater com o vNF da nota.
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(21, 10), nullable=False, default=0)
    valor_total_item: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    valor_frete: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    valor_desconto: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)

    # --- Impostos: só o mínimo que a operação usa ---
    # PIS, COFINS, IBS, CBS e os grupos de redução (gRed, pAliqEfet) ficam de
    # fora por enquanto e vivem no xml_original da capa. São ~40 colunas para
    # sustentar relatórios que ninguém pediu ainda — abstração por antecipação,
    # que o ARCHITECTURE.md proíbe. Quando doer, vira `nota_fiscal_item_impostos`.
    cst_icms: Mapped[str | None] = mapped_column(String(3), nullable=True, default=None)
    aliquota_icms: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 4), nullable=True, default=None
    )
    valor_icms: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True, default=None)
    valor_icms_st: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2), nullable=True, default=None
    )
    cst_ipi: Mapped[str | None] = mapped_column(String(3), nullable=True, default=None)
    aliquota_ipi: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True, default=None)
    valor_ipi: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True, default=None)

    # --- Rastreabilidade ---
    # Lote e validade chegam como texto livre em <infAdProd> ("| Lote:2512366503,
    # Validade:05/01/31, ..."), que é o costume do mercado apesar de existir o
    # grupo <rastro> no leiaute. Por isso os dois campos são nullable e o texto
    # cru fica guardado ao lado: quando o parser não conseguir extrair, ninguém
    # perde a informação — só deixa de ter ela em coluna.
    lote: Mapped[str | None] = mapped_column(String(60), nullable=True, default=None)
    validade: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    informacoes_adicionais: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    nota_fiscal: Mapped["NotaFiscal"] = relationship(back_populates="itens")
