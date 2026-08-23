from datetime import datetime

from pydantic import Field, field_validator, model_validator
from app.shared.contrato_base import ContratoBase


class ProdutoBaseSchema(ContratoBase):
    codigo: str = Field(min_length=1, max_length=40)
    descricao: str = Field(min_length=3, max_length=255)
    unidade: str = Field(default="UN", max_length=10)
    # O código que vem do ERP e sai na nota. Um só, porque no ERP é um só.
    codigo_barra_notas: str | None = Field(default=None, max_length=60)
    # Os códigos que o coletor lê no galpão. Lista inteira a cada gravação: o
    # que vier aqui é o cadastro final do produto, e o service resolve o diff
    # (ver `_sincronizar_codigos_logistica`). Mesmo padrão das permissões de
    # usuário — o cliente manda o conjunto desejado, não operações.
    codigos_barras_logistica: list[str] = Field(default_factory=list)
    dun_14: str | None = Field(default=None, max_length=60)
    quantidade_multipla_venda: int = Field(default=1, ge=1)
    registro_anvisa: str | None = Field(default=None, max_length=30)
    marca_id: str | None = None
    marca_sistema_origem_id: str | None = None
    sistema_origem_id: str | None = Field(default=None, max_length=100)
    ativo: bool = True

    @field_validator("codigos_barras_logistica", mode="after")
    @classmethod
    def normalizar_codigos_logistica(cls, valores: list[str]) -> list[str]:
        """Tira espaço, descarta vazio e remove repetido preservando a ordem.

        O campo vem de um formulário onde o operador bipa um código atrás do
        outro: bipar duas vezes o mesmo é acidente comum, e não é erro que mereça
        recusar a gravação inteira."""
        limpos = [valor.strip() for valor in valores]
        unicos = list(dict.fromkeys(valor for valor in limpos if valor))
        for codigo in unicos:
            if len(codigo) > 60:
                raise ValueError("Código de barras de logística acima de 60 caracteres.")
        return unicos

    @model_validator(mode="after")
    def validar_referencia_de_marca(self) -> "ProdutoBaseSchema":
        if not self.marca_id and not self.marca_sistema_origem_id:
            raise ValueError("Informe marcaId ou marcaSistemaOrigemId.")
        return self


class ProdutoCriarSchema(ProdutoBaseSchema):
    pass


class ProdutoAtualizarSchema(ProdutoBaseSchema):
    pass


class ProdutoRespostaSchema(ContratoBase):
    id: str
    codigo: str
    descricao: str
    unidade: str
    codigo_barra_notas: str | None
    codigos_barras_logistica: list[str]
    dun_14: str | None
    quantidade_multipla_venda: int
    registro_anvisa: str | None
    marca_id: str
    marca_nome: str
    sistema_origem_id: str | None
    ativo: bool
    criado_em: datetime


class ProdutoListaPaginadaSchema(ContratoBase):
    items: list[ProdutoRespostaSchema]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str


class VincularAnvisaSchema(ContratoBase):
    """O que o coletor leu. É contra este valor que a CMED é conferida — sem
    ele a operação viraria "importe os códigos da CMED", que é outra coisa."""

    codigo_barras: str = Field(min_length=1, max_length=300)


class ConflitoCodigoBarrasSchema(ContratoBase):
    """Um código da CMED que já pertence a outro produto. Vai para a tela com o
    produto identificado: "já existe" sem dizer onde não ajuda ninguém."""

    codigo: str
    produto_id: str
    produto_codigo: str
    produto_descricao: str


class VincularAnvisaRespostaSchema(ContratoBase):
    """Sempre 200, mesmo quando nada foi vinculado.

    Não vinculado não é erro de requisição: é uma resposta de negócio que a tela
    precisa mostrar por extenso ("o registro não está na CMED", "o código não
    confere", "já é de outro produto"). Um 4xx daria à tela um `detail` solto e
    nenhuma forma de distinguir os casos.
    """

    situacao: str
    mensagem: str
    codigos_vinculados: list[str]
    conflitos: list[ConflitoCodigoBarrasSchema]
