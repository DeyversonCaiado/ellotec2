from pydantic import EmailStr
from app.shared.contrato_base import ContratoBase


class LoginPayload(ContratoBase):
    email: EmailStr | None = None
    usuario: str | None = None
    senha: str

    def identificador(self) -> str:
        if self.email:
            return self.email
        if self.usuario:
            return self.usuario
        return ""


class UsuarioLogadoSchema(ContratoBase):
    id: str
    usuario: str
    nome: str
    email: str
    permissoes: list[str]


class LoginResponse(ContratoBase):
    """Mesmo formato esperado pelo AuthService do front (auth.models.ts)."""

    token: str
    refresh_token: str
    usuario: UsuarioLogadoSchema


class RefreshPayload(ContratoBase):
    refresh_token: str
