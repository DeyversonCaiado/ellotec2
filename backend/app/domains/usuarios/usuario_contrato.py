from datetime import datetime

from pydantic import EmailStr, Field, field_validator
from app.shared.contrato_base import ContratoBase

from app.core.permissions.permission_contrato import validar_chaves_permissao


class UsuarioBaseSchema(ContratoBase):
    usuario: str = Field(min_length=3, max_length=50)
    sistema_origem_id: str | None = Field(default=None, max_length=100)
    nome: str = Field(min_length=3, max_length=150)
    email: EmailStr
    cargo_id: str
    ativo: bool = True


class UsuarioCriarSchema(UsuarioBaseSchema):
    senha: str = Field(min_length=6, max_length=100)
    permissoes: list[str] = []

    _validar_permissoes = field_validator("permissoes")(validar_chaves_permissao)


class UsuarioAtualizarSchema(UsuarioBaseSchema):
    """Senha é opcional na atualização: omitida = mantém a senha atual."""

    senha: str | None = Field(default=None, min_length=6, max_length=100)
    permissoes: list[str] = []

    _validar_permissoes = field_validator("permissoes")(validar_chaves_permissao)


class UsuarioRespostaSchema(ContratoBase):
    id: str
    usuario: str
    sistema_origem_id: str | None
    nome: str
    email: str
    cargo_id: str
    cargo_nome: str
    ativo: bool
    permissoes: list[str]
    criado_em: datetime


class UsuarioResumoSchema(ContratoBase):
    """Versão enxuta de Usuario (só id + nome) pra domínios que precisam
    resolver "quem é esse usuário" (ex: vendedor de um pedido) sem exigir
    a permissão usuarios.acessar — quem cria um pedido nem sempre tem
    permissão pra administrar usuários."""

    id: str
    nome: str


class UsuarioListaPaginadaSchema(ContratoBase):
    items: list[UsuarioRespostaSchema]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str
