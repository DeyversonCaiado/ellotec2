from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator
from app.shared.contrato_base import ContratoBase


class ItemPedidoEntradaSchema(ContratoBase):
    """O que o front manda por item. Código, descrição e preço vêm no payload
    e são gravados como snapshot — o backend NÃO consulta o cadastro de
    produtos (ver "Regras de import entre domínios" no ARCHITECTURE.md).

    ATENÇÃO: isso significa que o preço é o que o cliente HTTP enviou. Ver a
    pendência "preço confiado do front" em ARCHITECTURE.md."""

    produto_id: str | None = None
    # Se informado, o item é resolvido por esse campo em vez de produto_id —
    # mesmo padrão de marca_sistema_origem_id em produtos. Além de resolver a
    # FK, agora ele fica GRAVADO: é uma das três pernas da chave natural do
    # item no ERP (ver pedido_model.py).
    produto_sistema_origem_id: str | None = Field(default=None, max_length=100)
    produto_codigo: str = Field(default="", max_length=40)
    produto_descricao: str = Field(default="", max_length=255)
    preco_unitario: Decimal = Field(default=Decimal(0), ge=0)
    quantidade: int = Field(gt=0)
    # Disponível apenas via API — não exibido nem editável no front hoje.
    # O endereço NÃO entra aqui: ele é do estoque, não do pedido (ver
    # pedido_model.py e o domínio `enderecamento`).
    lote: str | None = Field(default=None, max_length=100)

    # As outras duas pernas da chave natural. Ambas opcionais no item: os itens
    # de um pedido são todos da mesma empresa e do mesmo pedido, então a capa
    # serve de padrão e a integração não precisa repetir os dois textos em cada
    # linha (ver `_montar_itens` em pedido_service.py). Item que informar o
    # próprio valor manda nele.
    empresa_sistema_origem_id: str | None = Field(default=None, max_length=100)
    pedido_sistema_origem_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validar_referencia_de_produto(self) -> "ItemPedidoEntradaSchema":
        if not self.produto_id and not self.produto_sistema_origem_id:
            raise ValueError("Informe produtoId ou produtoSistemaOrigemId em cada item.")
        return self


class ItemPedidoRespostaSchema(ContratoBase):
    id: str
    produto_id: str
    produto_codigo: str
    produto_descricao: str
    quantidade: int
    preco_unitario: float  # serializado como number no JSON (front usa para calcular total)
    # Disponível apenas via API — não exibido nem editável no front hoje.
    lote: str | None
    # O trio que identifica a linha no ERP — devolvido para a integração casar
    # o item que ela mandou com a linha que nasceu aqui, sem ter que confiar na
    # ordem do array.
    empresa_sistema_origem_id: str | None
    pedido_sistema_origem_id: str | None
    produto_sistema_origem_id: str | None

class PedidoListaPaginadaSchema(ContratoBase):
    """Mesmo formato de página dos outros domínios (ver ProdutoListaPaginadaSchema)
    — a tela não inventa um contrato próprio."""

    items: list["PedidoRespostaSchema"]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str


class PedidoStatusRespostaSchema(ContratoBase):
    id: str
    chave: str


class ClientePedidoSchema(ContratoBase):
    id: str
    nome_fantasia: str
    cnpj: str


class PedidoBaseSchema(ContratoBase):
    data_pedido: date
    # Milestone vindo do ERP: quando o pedido foi liberado (ex: aprovação de
    # crédito). Opcional porque pedido não liberado ainda não tem a data — e
    # porque a integração pode mandar a capa antes da liberação acontecer.
    liberado_em: datetime | None = None
    cliente_id: str
    # Snapshot do cliente no momento da emissão, enviado pelo front (que já
    # tem o cliente selecionado em mãos). O backend não consulta o domínio
    # clientes — a FK de cliente_id é quem garante que o id existe.
    cliente_nome_fantasia: str = Field(default="", max_length=150)
    cliente_cnpj: str = Field(default="", max_length=18)
    empresa_id: str | None = None
    # Se informado, a empresa é resolvida por esse campo em vez de
    # empresa_id — mesmo padrão de marca_sistema_origem_id em produtos.
    empresa_sistema_origem_id: str | None = None
    vendedor_id: str | None = None
    # Se informado, o vendedor é resolvido por esse campo em vez de
    # vendedor_id — mesmo padrão de empresa_sistema_origem_id acima, mas
    # aqui equivale ao sistema_origem_id da tabela de USUÁRIOS (domains/
    # usuarios), não de pedidos.
    vendedor_sistema_origem_id: str | None = None
    sistema_origem_id: str | None = Field(default=None, max_length=100)
    itens: list[ItemPedidoEntradaSchema] = Field(min_length=1)
    # status não é enum fechado nem chave de texto livre — é referência ao
    # catálogo pedido_status, exatamente como empresa_id/empresa_sistema_origem_id
    # acima. O solicitante manda um dos dois; o service só confirma que o
    # registro existe (ver _resolver_status_id em pedido_service.py).
    status_id: str | None = None
    status_sistema_origem_id: str | None = None
    observacoes: str = ""

    @field_validator("itens")
    @classmethod
    def itens_sem_linha_duplicada(
        cls, itens: list[ItemPedidoEntradaSchema]
    ) -> list[ItemPedidoEntradaSchema]:
        """Uma linha por `(produto, lote)`. O mesmo produto só repete em lote
        diferente.

        O endereço NÃO entra na chave, e essa é a parte que engana. Ele é onde a
        mercadoria está guardada no nosso galpão — informação nossa, não do que
        o cliente comprou. Um lote realmente se espalha por vários endereços,
        mas isso é assunto da separação (`expedicao_separacao_itens`), não da
        linha do pedido; é assim que os ERPs grandes modelam, e a linha de
        pedido deles nem tem endereço.

        A regra anterior incluía o endereço e deixava passar exatamente o defeito
        que motivou esta: a consulta da integração cruzava a linha do pedido com
        o estoque por endereço e devolvia uma linha por endereço, cada uma com a
        quantidade INTEIRA. Um pedido de 14.000 un entrava com 42.000, e a
        validação aprovava.
        """
        chaves_vistas = {
            (item.produto_id or item.produto_sistema_origem_id, item.lote)
            for item in itens
        }
        if len(chaves_vistas) != len(itens):
            raise ValueError(
                "Duas linhas com o mesmo produto e lote — some a quantidade na mesma "
                "linha. O endereço não separa uma linha da outra: ele diz onde a "
                "mercadoria está, não o que foi pedido."
            )
        return itens

    @model_validator(mode="after")
    def validar_referencia_de_empresa(self) -> "PedidoBaseSchema":
        if not self.empresa_id and not self.empresa_sistema_origem_id:
            raise ValueError("Informe empresaId ou empresaSistemaOrigemId.")
        return self

    @model_validator(mode="after")
    def validar_referencia_de_status(self) -> "PedidoBaseSchema":
        if not self.status_id and not self.status_sistema_origem_id:
            raise ValueError("Informe statusId ou statusSistemaOrigemId.")
        return self


class PedidoCriarSchema(PedidoBaseSchema):
    pass


class PedidoAtualizarSchema(PedidoBaseSchema):
    pass


class PedidoRespostaSchema(ContratoBase):
    id: str
    # Nulo enquanto a origem externa não tiver dado um número ao pedido.
    numero: str | None
    data_pedido: date
    cliente_id: str
    cliente: ClientePedidoSchema
    empresa_id: str
    vendedor_id: str | None
    sistema_origem_id: str | None
    liberado_em: datetime | None
    itens: list[ItemPedidoRespostaSchema]
    status: str
    status_id: str
    observacoes: str
    criado_em: datetime
