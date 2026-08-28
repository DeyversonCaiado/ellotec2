from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, model_validator

from app.shared.contrato_base import ContratoBase


class _ReferenciasBaseSchema(ContratoBase):
    """As referências que toda linha de estoque carrega.

    Empresa e produto podem chegar pelo id daqui OU pelo id do sistema de
    origem — a integração conhece o código do ERP, a tela conhece o UUID.
    É o mesmo par de caminhos que `pedidos` já aceita.
    """

    empresa_id: str | None = None
    empresa_sistema_origem_id: str | None = Field(default=None, max_length=100)
    produto_id: str | None = None
    produto_sistema_origem_id: str | None = Field(default=None, max_length=100)
    sistema_origem_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validar_referencias(self) -> "_ReferenciasBaseSchema":
        if not self.empresa_id and not self.empresa_sistema_origem_id:
            raise ValueError("Informe empresaId ou empresaSistemaOrigemId.")
        if not self.produto_id and not self.produto_sistema_origem_id:
            raise ValueError("Informe produtoId ou produtoSistemaOrigemId.")
        return self


class SaldoEntradaSchema(_ReferenciasBaseSchema):
    """Saldo total do produto na empresa (tabela `estoque`)."""

    quantidade: Decimal = Field(default=Decimal(0), ge=0)


class SaldoRespostaSchema(ContratoBase):
    id: str
    produto_id: str
    # Código e descrição vêm do cadastro VIVO do produto, por
    # `produto_publico.obter_identificacoes`. Não são snapshot: uma listagem de
    # estoque quer o nome de hoje, ao contrário do pedido, que congela o que
    # foi vendido. Vazios quando o produto não tem mais cadastro vivo.
    produto_codigo: str
    produto_descricao: str
    empresa_id: str
    quantidade: float
    sistema_origem_id: str | None
    empresa_sistema_origem_id: str | None
    criado_em: datetime


class LoteEntradaSchema(_ReferenciasBaseSchema):
    """Saldo do produto aberto por lote (tabela `estoque_lotes`)."""

    lote: str = Field(min_length=1, max_length=100)
    quantidade: Decimal = Field(default=Decimal(0), ge=0)
    fabricacao: date | None = None
    vencimento: date | None = None


class LoteRespostaSchema(ContratoBase):
    id: str
    produto_id: str
    # Ver SaldoRespostaSchema — mesma origem, cadastro vivo.
    produto_codigo: str
    produto_descricao: str
    empresa_id: str
    lote: str
    quantidade: float
    fabricacao: date | None
    vencimento: date | None
    sistema_origem_id: str | None
    empresa_sistema_origem_id: str | None
    criado_em: datetime


class SaldoListaPaginadaSchema(ContratoBase):
    items: list[SaldoRespostaSchema]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str


class LoteListaPaginadaSchema(ContratoBase):
    items: list[LoteRespostaSchema]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str
