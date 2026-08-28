import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.auth.auth_router import router as auth_router
from app.core.database import erros_integridade
from app.core.settings import obter_settings
from app.domains.cidades.cidade_router import router as cidade_router
from app.domains.clientes.cliente_router import router as cliente_router
from app.domains.empresas.empresa_router import router as empresa_router
from app.domains.enderecamento.enderecamento_router import router as enderecamento_router
from app.domains.entregas.entrega_router import router as entrega_router
from app.domains.estoque.estoque_router import router as estoque_router
from app.domains.expedicao.expedicao_router import router as expedicao_router
from app.domains.marcas.marca_router import router as marca_router
from app.domains.notas_fiscais.nota_fiscal_router import router as nota_fiscal_router
from app.domains.pedidos.pedido_router import router as pedido_router
from app.domains.produtos.produto_router import router as produto_router
from app.domains.usuarios.cargo_router import router as cargo_router
from app.domains.usuarios.usuario_router import router as usuario_router

settings = obter_settings()
logger = logging.getLogger(__name__)

DESCRICAO = """
API do **ELLOTEC ERP** — backend do sistema de gestão (usuários, clientes, produtos e pedidos).

## Autenticação

Toda rota fora de `/auth/*` exige um Bearer token (JWT), obtido em `POST /auth/login`.
Todo request também precisa do header `X-Device-Id` (UUID estável gerado pelo cliente),
usado para vincular sessões a dispositivos e permitir revogação granular.

## Permissões

Cada permissão é uma chave nomeada no padrão `dominio.contexto.acao`
(ex: `produtos.acessar`, `pedidos.gravar.incluir`), definida no catálogo
`PERMISSOES_VALIDAS` (`core/permissions/permission_model.py`). O backend verifica a
permissão do usuário autenticado em **todo** endpoint — o front nunca é a única
barreira de controle de acesso.
"""

app = FastAPI(
    title=settings.app_name,
    description=DESCRICAO,
    version="1.0.0",
    contact={"name": "ELLOTEC"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origens,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(usuario_router)
app.include_router(cargo_router)
app.include_router(cliente_router)
app.include_router(empresa_router)
app.include_router(cidade_router)
app.include_router(produto_router)
app.include_router(marca_router)
app.include_router(pedido_router)
app.include_router(nota_fiscal_router)
app.include_router(expedicao_router)
app.include_router(entrega_router)
app.include_router(estoque_router)
app.include_router(enderecamento_router)


@app.exception_handler(IntegrityError)
def tratar_violacao_de_integridade(request: Request, exc: IntegrityError) -> JSONResponse:
    """
    Sem isso, um id inexistente numa FK (ex: criar pedido com `cliente_id` que
    não existe) estoura como erro não tratado e vira 500. Como os domínios não
    consultam uns aos outros para validar id — a FK do banco é a barreira —,
    esse handler é o que transforma a recusa do banco numa resposta limpa.

    A resposta diz QUAL restrição reprovou (ver `erros_integridade.descrever`).
    Antes era sempre a mesma frase para dois problemas opostos — id inexistente
    e registro duplicado —, e quem integra ficava sem saber para que lado olhar:

        RuntimeError: Falha ao atualizar pedido '0210517': 422
        {"detail":"Registro referenciado não existe ou viola uma restrição
        de unicidade."}

    O log do servidor recebe o erro completo com stack: a resposta HTTP é para
    quem chama, o log é para quem mantém.
    """
    logger.warning("Violação de integridade em %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=erros_integridade.descrever(exc),
    )


@app.get("/", tags=["Status"], summary="Healthcheck")
def raiz() -> dict[str, str]:
    return {"status": "ok", "aplicacao": settings.app_name, "ambiente": settings.ambiente}
