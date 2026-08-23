from datetime import datetime

from pydantic import Field

from app.shared.contrato_base import ContratoBase


class CidadeBaseSchema(ContratoBase):
    codigo_municipio: int
    nome: str = Field(min_length=1, max_length=255)
    uf: str = Field(min_length=2, max_length=2)


class CidadeCriarSchema(CidadeBaseSchema):
    pass


class CidadeAtualizarSchema(CidadeBaseSchema):
    pass


class CidadeRespostaSchema(ContratoBase):
    id: str
    codigo_municipio: int
    nome: str
    uf: str
    criado_em: datetime


class CidadeListaPaginadaSchema(ContratoBase):
    items: list[CidadeRespostaSchema]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str
