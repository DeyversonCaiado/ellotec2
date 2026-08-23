from datetime import datetime

from pydantic import Field, model_validator
from app.shared.contrato_base import ContratoBase


class ClienteBaseSchema(ContratoBase):
    codigo: str | None = Field(default=None, max_length=10)
    razao_social: str = Field(min_length=3, max_length=200)
    nome_fantasia: str = Field(min_length=1, max_length=150)
    cpf_cnpj: str
    email: str | None = None
    telefone: str = Field(default="", max_length=30)
    celular: str | None = Field(default=None, max_length=50)
    logradouro: str | None = Field(default=None, max_length=255)
    numero: str | None = Field(default=None, max_length=50)
    complemento: str | None = Field(default=None, max_length=255)
    bairro: str | None = Field(default=None, max_length=100)
    cep: str | None = Field(default=None, max_length=10)
    sistema_origem_id: str | None = Field(default=None, max_length=100)
    cidade_id: str | None = None
    cidade_ibge: int | None = None
    ativo: bool = True

    @model_validator(mode="after")
    def validar_referencia_de_cidade(self) -> "ClienteBaseSchema":
        if not self.cidade_id and not self.cidade_ibge:
            raise ValueError("Informe cidade_id ou cidade_ibge.")
        return self


class ClienteCriarSchema(ClienteBaseSchema):
    pass


class ClienteAtualizarSchema(ClienteBaseSchema):
    pass


class ClienteRespostaSchema(ContratoBase):
    id: str
    codigo: str | None
    razao_social: str
    nome_fantasia: str
    cpf_cnpj: str
    email: str | None
    telefone: str
    celular: str | None
    logradouro: str | None
    numero: str | None
    complemento: str | None
    bairro: str | None
    cep: str | None
    sistema_origem_id: str | None
    cidade_id: str
    cidade_nome: str
    cidade_uf: str
    ativo: bool
    criado_em: datetime


class ClienteListaPaginadaSchema(ContratoBase):
    items: list[ClienteRespostaSchema]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str
