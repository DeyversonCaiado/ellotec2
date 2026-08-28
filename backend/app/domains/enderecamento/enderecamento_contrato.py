from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from app.shared.contrato_base import ContratoBase


class _EmpresaBaseSchema(ContratoBase):
    """A empresa chega pelo id daqui OU pelo id do sistema de origem — mesmo
    par de caminhos que `pedidos` e `estoque` já aceitam."""

    empresa_id: str | None = None
    empresa_sistema_origem_id: str | None = Field(default=None, max_length=100)
    sistema_origem_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validar_empresa(self) -> "_EmpresaBaseSchema":
        if not self.empresa_id and not self.empresa_sistema_origem_id:
            raise ValueError("Informe empresaId ou empresaSistemaOrigemId.")
        return self


class EnderecoEntradaSchema(_EmpresaBaseSchema):
    """Um lugar do galpão (tabela `estoque_enderecos`)."""

    descricao: str = Field(min_length=1, max_length=100)


class EnderecoRespostaSchema(ContratoBase):
    id: str
    descricao: str
    empresa_id: str
    sistema_origem_id: str | None
    empresa_sistema_origem_id: str | None
    criado_em: datetime


class VinculoEntradaSchema(_EmpresaBaseSchema):
    """Onde um lote está guardado (tabela `estoque_endereco_lote`).

    As duas pontas aceitam dois caminhos, porque a integração conhece os dados
    do ERP e a tela conhece os UUIDs daqui:

    - endereço: `estoqueEnderecosId` **ou** `enderecoDescricao` (o texto da
      etiqueta, resolvido dentro da empresa);
    - lote: `estoqueLotesId` **ou** o par produto + `lote`, onde o produto vem
      por `produtoId` ou `produtoSistemaOrigemId`.
    """

    estoque_enderecos_id: str | None = None
    endereco_descricao: str | None = Field(default=None, max_length=100)

    estoque_lotes_id: str | None = None
    produto_id: str | None = None
    produto_sistema_origem_id: str | None = Field(default=None, max_length=100)
    lote: str | None = Field(default=None, max_length=100)

    # Quanto daquele lote está NESTE endereço. É o número que a expedição
    # mostra por endereço e do qual ela baixa ao fechar a separação.
    quantidade: Decimal = Field(default=Decimal(0), ge=0)

    @model_validator(mode="after")
    def validar_pontas(self) -> "VinculoEntradaSchema":
        if not self.estoque_enderecos_id and not self.endereco_descricao:
            raise ValueError("Informe estoqueEnderecosId ou enderecoDescricao.")
        if not self.estoque_lotes_id:
            if not self.lote:
                raise ValueError("Informe estoqueLotesId ou o par produto + lote.")
            if not self.produto_id and not self.produto_sistema_origem_id:
                raise ValueError("Informe produtoId ou produtoSistemaOrigemId junto com o lote.")
        return self


class VinculoRespostaSchema(ContratoBase):
    id: str
    estoque_enderecos_id: str
    estoque_lotes_id: str
    # A descrição vai junto porque quem lê esta resposta quer o nome da
    # etiqueta, não o UUID do endereço — evita um GET a mais por linha.
    endereco_descricao: str
    quantidade: float
    # Lote e produto vêm resolvidos das bordas de `estoque` e `produtos`: a
    # consulta é "onde está este produto", e uma linha só com UUID não responde
    # isso para ninguém.
    lote: str
    produto_id: str
    produto_codigo: str
    produto_descricao: str
    empresa_id: str
    sistema_origem_id: str | None
    empresa_sistema_origem_id: str | None
    criado_em: datetime


class EnderecoListaPaginadaSchema(ContratoBase):
    items: list[EnderecoRespostaSchema]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str


class VinculoListaPaginadaSchema(ContratoBase):
    items: list[VinculoRespostaSchema]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str
