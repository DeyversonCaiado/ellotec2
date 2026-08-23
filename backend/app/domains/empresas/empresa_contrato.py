from datetime import datetime

from pydantic import Field
from app.shared.contrato_base import ContratoBase


class EmpresaBaseSchema(ContratoBase):
    codigo: str | None = Field(default=None, max_length=10)
    razao_social: str = Field(min_length=1, max_length=200)
    nome_fantasia: str = Field(min_length=1, max_length=150)
    apelido: str | None = Field(default=None, max_length=60)
    cnpj: str = Field(min_length=1, max_length=18)
    sistema_origem_id: str | None = Field(default=None, max_length=100)
    ativo: bool = True


class EmpresaCriarSchema(EmpresaBaseSchema):
    pass


class EmpresaAtualizarSchema(EmpresaBaseSchema):
    pass


class EmpresaRespostaSchema(ContratoBase):
    id: str
    codigo: str | None
    razao_social: str
    nome_fantasia: str
    apelido: str | None
    cnpj: str
    sistema_origem_id: str | None
    ativo: bool
    criado_em: datetime


class EmpresaListaPaginadaSchema(ContratoBase):
    items: list[EmpresaRespostaSchema]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str
