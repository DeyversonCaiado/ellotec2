from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.shared.contrato_base import ContratoBase

# Conjuntos fechados, declarados como Literal para que o Pydantic recuse na
# entrada (422) e o OpenAPI documente as opções. São valores traduzidos do
# XML — nunca o código cru do leiaute, que não diz nada para quem lê a tela.
TipoOperacao = Literal["entrada", "saida"]
StatusNota = Literal["autorizada", "cancelada", "denegada", "rejeitada"]
Finalidade = Literal["normal", "complementar", "ajuste", "devolucao"]
ModalidadeFrete = Literal["emitente", "destinatario", "terceiros", "sem_frete"]


class ItemNotaFiscalEntradaSchema(ContratoBase):
    """Um item como veio no documento. Tudo aqui é SNAPSHOT: o backend não
    consulta o cadastro de produtos para preencher código ou descrição (ver
    "Regras de import entre domínios" no ARCHITECTURE.md)."""

    numero_item: int = Field(gt=0)
    # Opcional: numa nota de entrada, o produto do fornecedor pode não existir
    # no seu cadastro. Ver o comentário em NotaFiscalItem.produto_id.
    produto_id: str | None = None
    produto_codigo: str = Field(default="", max_length=40)
    produto_descricao: str = Field(default="", max_length=255)
    codigo_barras: str | None = Field(default=None, max_length=20)
    ncm: str | None = Field(default=None, max_length=8)
    cfop: str | None = Field(default=None, max_length=4)
    unidade: str = Field(default="UN", max_length=6)

    quantidade: Decimal = Field(default=Decimal(0), ge=0)
    preco_unitario: Decimal = Field(default=Decimal(0), ge=0)
    valor_total_item: Decimal = Field(default=Decimal(0), ge=0)
    valor_frete: Decimal = Field(default=Decimal(0), ge=0)
    valor_desconto: Decimal = Field(default=Decimal(0), ge=0)

    cst_icms: str | None = Field(default=None, max_length=3)
    aliquota_icms: Decimal | None = None
    valor_icms: Decimal | None = None
    valor_icms_st: Decimal | None = None
    cst_ipi: str | None = Field(default=None, max_length=3)
    aliquota_ipi: Decimal | None = None
    valor_ipi: Decimal | None = None

    lote: str | None = Field(default=None, max_length=60)
    validade: date | None = None
    informacoes_adicionais: str | None = None


class ItemNotaFiscalRespostaSchema(ContratoBase):
    id: str
    numero_item: int
    produto_id: str | None
    produto_codigo: str
    produto_descricao: str
    codigo_barras: str | None
    ncm: str | None
    cfop: str | None
    unidade: str
    # Serializados como number no JSON, igual a `preco_unitario` em pedidos: o
    # Pydantic v2 serializa Decimal como STRING em modo JSON, e o front faz
    # conta com esses valores. A precisão exata continua guardada no banco
    # (Numeric(21, 10)) — o float aqui é só a representação de saída.
    quantidade: float
    preco_unitario: float
    valor_total_item: float
    valor_frete: float
    valor_desconto: float
    cst_icms: str | None
    aliquota_icms: float | None
    valor_icms: float | None
    valor_icms_st: float | None
    cst_ipi: str | None
    aliquota_ipi: float | None
    valor_ipi: float | None
    lote: str | None
    validade: date | None
    informacoes_adicionais: str | None


class NotaFiscalBaseSchema(ContratoBase):
    """O que entra num POST/PUT de nota. Hoje quem preenche isso é a
    integração (ERP ou download do XML na SEFAZ), não uma tela — nota fiscal
    não se digita, se recebe."""

    modelo: str = Field(default="55", max_length=5)
    tipo_operacao: TipoOperacao
    finalidade: Finalidade | None = None
    # 44 dígitos exatos quando existe. Nulo em NFS-e, que não tem chave.
    chave_acesso: str | None = Field(default=None, min_length=44, max_length=44)
    numero: str = Field(max_length=20)
    serie: str = Field(default="", max_length=5)
    natureza_operacao: str = Field(default="", max_length=60)
    data_emissao: datetime
    data_saida_entrada: datetime | None = None

    status: StatusNota = "autorizada"
    protocolo_autorizacao: str | None = Field(default=None, max_length=20)
    data_autorizacao: datetime | None = None

    empresa_id: str | None = None
    # Se informado, a empresa é resolvida por esse campo em vez de empresa_id —
    # mesmo padrão de `empresa_sistema_origem_id` em pedidos.
    empresa_sistema_origem_id: str | None = None
    # O pedido que originou a nota, quando existe um. Opcional: toda nota de
    # entrada e as de devolução/remessa não têm pedido deste lado. Não é
    # validado por consulta — a FK recusa id inexistente no INSERT.
    pedido_id: str | None = None

    emitente_cnpj_cpf: str = Field(max_length=18)
    emitente_razao_social: str = Field(default="", max_length=200)
    emitente_nome_fantasia: str | None = Field(default=None, max_length=150)
    emitente_inscricao_estadual: str | None = Field(default=None, max_length=20)
    emitente_municipio: str | None = Field(default=None, max_length=100)
    emitente_uf: str | None = Field(default=None, max_length=2)

    destinatario_cnpj_cpf: str = Field(max_length=18)
    destinatario_razao_social: str = Field(default="", max_length=200)
    destinatario_inscricao_estadual: str | None = Field(default=None, max_length=20)
    destinatario_municipio: str | None = Field(default=None, max_length=100)
    destinatario_uf: str | None = Field(default=None, max_length=2)

    valor_produtos: Decimal = Field(default=Decimal(0), ge=0)
    valor_frete: Decimal = Field(default=Decimal(0), ge=0)
    valor_seguro: Decimal = Field(default=Decimal(0), ge=0)
    valor_desconto: Decimal = Field(default=Decimal(0), ge=0)
    valor_outras_despesas: Decimal = Field(default=Decimal(0), ge=0)
    valor_icms: Decimal = Field(default=Decimal(0), ge=0)
    valor_ipi: Decimal = Field(default=Decimal(0), ge=0)
    valor_total: Decimal = Field(default=Decimal(0), ge=0)

    transportadora_nome: str | None = Field(default=None, max_length=200)
    transportadora_cnpj_cpf: str | None = Field(default=None, max_length=18)
    modalidade_frete: ModalidadeFrete | None = None
    quantidade_volumes: int | None = Field(default=None, ge=0)
    peso_bruto: Decimal | None = Field(default=None, ge=0)
    peso_liquido: Decimal | None = Field(default=None, ge=0)

    sistema_origem_id: str | None = Field(default=None, max_length=100)
    informacoes_complementares: str | None = None
    # O XML como veio. Opcional no contrato porque uma nota lançada à mão (raro,
    # mas acontece com documento de fornecedor que só chegou em papel) não tem
    # XML nenhum — e recusar por isso seria impedir de guardar o documento.
    xml_original: str | None = None

    itens: list[ItemNotaFiscalEntradaSchema] = Field(min_length=1)

    @field_validator("itens")
    @classmethod
    def itens_sem_numero_repetido(
        cls, itens: list[ItemNotaFiscalEntradaSchema]
    ) -> list[ItemNotaFiscalEntradaSchema]:
        """`numero_item` é o nItem do documento — a posição do item DENTRO da
        nota, definida por quem emitiu. Dois itens com o mesmo número é erro de
        parser, não caso de negócio: é por esse número que a conferência casa o
        item com o que o fornecedor mandou."""
        numeros = {item.numero_item for item in itens}
        if len(numeros) != len(itens):
            raise ValueError("Existem dois itens com o mesmo numeroItem na nota.")
        return itens

    @model_validator(mode="after")
    def validar_referencia_de_empresa(self) -> "NotaFiscalBaseSchema":
        if not self.empresa_id and not self.empresa_sistema_origem_id:
            raise ValueError("Informe empresaId ou empresaSistemaOrigemId.")
        return self


class NotaFiscalCriarSchema(NotaFiscalBaseSchema):
    pass


class NotaFiscalAtualizarSchema(NotaFiscalBaseSchema):
    pass


class NotaFiscalResumoSchema(ContratoBase):
    """O que a LISTAGEM devolve — sem os itens e sem o XML.

    Uma nota tem dezenas de itens e o XML tem dezenas de KB; devolver os dois
    numa página de 20 notas seriam centenas de linhas e megabytes que a lista
    não mostra. Quem precisa do detalhe chama GET /notas-fiscais/{id}.
    """

    id: str
    modelo: str
    tipo_operacao: str
    chave_acesso: str | None
    numero: str
    serie: str
    natureza_operacao: str
    data_emissao: datetime
    status: str
    empresa_id: str
    emitente_cnpj_cpf: str
    emitente_razao_social: str
    destinatario_cnpj_cpf: str
    destinatario_razao_social: str
    valor_total: float
    quantidade_volumes: int | None
    sistema_origem_id: str | None
    # NÃO existe um `criadoEm` aqui de propósito. Ele existia, lido de
    # `sync_created_at`, e isso é justamente o que a regra "os campos sync_*
    # nunca entram na regra de negócio" (ARCHITECTURE.md) proíbe: publicar
    # auditoria da LINHA como se fosse um fato do documento. A data de negócio
    # da nota é `data_emissao`, que é o que a tela mostra e filtra. Se um dia
    # for preciso saber quando o registro entrou no sistema, isso é uma coluna
    # própria — não o campo de sincronização.


class NotaFiscalRespostaSchema(NotaFiscalResumoSchema):
    """O detalhe de uma nota: o resumo + tudo que a listagem não carrega.

    `xml_original` NÃO vem aqui — é dezenas de KB que a tela de detalhe não
    exibe. Quem quer o XML cru chama GET /notas-fiscais/{id}/xml.
    """

    pedido_id: str | None
    finalidade: str | None
    data_saida_entrada: datetime | None
    protocolo_autorizacao: str | None
    data_autorizacao: datetime | None
    emitente_nome_fantasia: str | None
    emitente_inscricao_estadual: str | None
    emitente_municipio: str | None
    emitente_uf: str | None
    destinatario_inscricao_estadual: str | None
    destinatario_municipio: str | None
    destinatario_uf: str | None
    valor_produtos: float
    valor_frete: float
    valor_seguro: float
    valor_desconto: float
    valor_outras_despesas: float
    valor_icms: float
    valor_ipi: float
    transportadora_nome: str | None
    transportadora_cnpj_cpf: str | None
    modalidade_frete: str | None
    peso_bruto: float | None
    peso_liquido: float | None
    informacoes_complementares: str | None
    itens: list[ItemNotaFiscalRespostaSchema]


class NotaFiscalListaPaginadaSchema(ContratoBase):
    """Mesmo formato de página dos outros domínios (ver
    PedidoListaPaginadaSchema) — a tela não inventa um contrato próprio."""

    items: list[NotaFiscalResumoSchema]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str


class NotaFiscalXmlSchema(ContratoBase):
    id: str
    chave_acesso: str | None
    xml_original: str | None
