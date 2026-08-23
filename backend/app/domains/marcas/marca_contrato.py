from datetime import datetime

from pydantic import Field
from app.shared.contrato_base import ContratoBase


class MarcaBaseSchema(ContratoBase):
    nome: str = Field(min_length=1, max_length=100)
    sistema_origem_id: str | None = Field(default=None, max_length=100)
    ativo: bool = True


class MarcaCriarSchema(MarcaBaseSchema):
    pass


class MarcaAtualizarSchema(MarcaBaseSchema):
    pass


class MarcaRespostaSchema(ContratoBase):
    id: str
    nome: str
    sistema_origem_id: str | None
    ativo: bool
    criado_em: datetime


class MarcaListaPaginadaSchema(ContratoBase):
    items: list[MarcaRespostaSchema]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str
