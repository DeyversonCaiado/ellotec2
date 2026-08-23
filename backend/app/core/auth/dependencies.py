from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.auth.dispositivo_service import validar_dispositivo_da_requisicao
from app.core.auth.seguranca import decodificar_access_token
from app.core.database.conexao import obter_sessao
from app.domains.usuarios.usuario_model import Usuario

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ContextoRequisicao:
    """Carrega tudo que um endpoint protegido precisa saber sobre quem
    está chamando: o usuário, e o id do dispositivo já validado contra o
    token e o header X-Device-Id da requisição atual."""

    usuario: Usuario
    dispositivo_id: str


def obter_usuario_atual(
    request: Request,
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    sessao_db: Session = Depends(obter_sessao),
) -> ContextoRequisicao:
    """
    Dependency base de autenticação. Faz, nesta ordem:
      1. Garante que veio um Bearer token.
      2. Decodifica e valida a assinatura/expiração do JWT.
      3. Confirma que o usuário do token existe, está ativo e não foi
         apagado (soft delete) — um JWT antigo de um usuário desativado
         depois da emissão não deve continuar funcionando até expirar.
      4. Confirma que o dispositivo gravado no token bate com o
         X-Device-Id desta requisição (ver dispositivo_service).

    Isso roda em TODO endpoint protegido — é o ponto único de verdade
    de "quem está autenticado", nunca reimplementado em cada domínio.
    """
    if credenciais is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação ausente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decodificar_access_token(credenciais.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    usuario_id = payload.get("sub")
    dispositivo_id_token = payload.get("dispositivo_id")

    usuario = (
        sessao_db.query(Usuario)
        .filter(Usuario.id == usuario_id, Usuario.sync_deleted_at.is_(None))
        .first()
    )
    if usuario is None or not usuario.ativo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado ou inativo.")

    validar_dispositivo_da_requisicao(sessao_db, request, dispositivo_id_token)

    return ContextoRequisicao(usuario=usuario, dispositivo_id=dispositivo_id_token)


def exigir_permissao(chave: str):
    """
    Fábrica de dependency — mesma ideia do permissionGuard(chave) do front,
    mas aqui é a barreira que REALMENTE importa: o front pode ser
    contornado (chamando a API direto), isso aqui não pode.

    `chave` é uma string do catálogo `PERMISSOES_VALIDAS`
    (`core/permissions/permission_model.py`), no padrão `dominio.contexto.acao`.

    Uso num endpoint:
        @router.get("/", dependencies=[Depends(exigir_permissao("produtos.acessar"))])

    Ou, se o endpoint também precisa do usuário:
        def listar(ctx: ContextoRequisicao = Depends(exigir_permissao("produtos.acessar"))): ...
    """

    def verificar(ctx: ContextoRequisicao = Depends(obter_usuario_atual)) -> ContextoRequisicao:
        tem_permissao = any(p.chave == chave for p in ctx.usuario.permissoes)

        if not tem_permissao:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permissão negada: requer '{chave}'.",
            )

        return ctx

    return verificar
