from fastapi import APIRouter
from fastapi.routing import APIRoute


class RouterBase(APIRouter):
    """
    APIRouter customizado que força response_model_by_alias=True em todas
    as rotas. Garante que todo endpoint serializa os schemas com os aliases
    camelCase (ex: razaoSocial, criadoEm) em vez dos nomes Python
    snake_case (razao_social, criado_em) — sem precisar declarar nada em
    cada endpoint individualmente.

    Uso: idêntico ao APIRouter normal.
        router = RouterBase(prefix="/clientes", tags=["Clientes"])
    """

    def add_api_route(self, path, endpoint, *, response_model_by_alias=True, **kwargs):
        return super().add_api_route(
            path, endpoint, response_model_by_alias=response_model_by_alias, **kwargs
        )
