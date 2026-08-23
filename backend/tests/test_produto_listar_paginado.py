"""
Testes de app.domains.produtos.produto_service.listar_paginado — mesmo
padrão de paginação + busca (`q`) usado em clientes e usuarios, substituindo
o antigo endpoint /produtos/busca.
"""

import pytest
from fastapi import HTTPException

from app.domains.marcas.marca_model import Marca
from app.domains.produtos import produto_service
from app.domains.produtos.produto_contrato import ProdutoCriarSchema


def _criar_marca(sessao_db) -> Marca:
    marca = Marca(nome="Marca Teste")
    sessao_db.add(marca)
    sessao_db.commit()
    sessao_db.refresh(marca)
    return marca


def _dados(marca_id: str, **overrides) -> dict:
    base = dict(codigo="MED-0012", descricao="Luva de Procedimento P", unidade="CX", marca_id=marca_id)
    base.update(overrides)
    return base


class TestListarPaginado:
    def test_lista_paginado_sem_filtro(self, sessao_db):
        marca_id = _criar_marca(sessao_db).id
        produto_service.criar(sessao_db, ProdutoCriarSchema(**_dados(marca_id)))
        produto_service.criar(sessao_db, ProdutoCriarSchema(**_dados(marca_id, codigo="MED-0045", descricao="Seringa 5ml")))

        itens, total = produto_service.listar_paginado(sessao_db, page=1, per_page=20, sort="descricao", sort_type="asc")
        assert total == 2
        assert len(itens) == 2

    def test_filtra_por_q_em_codigo_ou_descricao(self, sessao_db):
        marca_id = _criar_marca(sessao_db).id
        produto_service.criar(sessao_db, ProdutoCriarSchema(**_dados(marca_id)))
        produto_service.criar(sessao_db, ProdutoCriarSchema(**_dados(marca_id, codigo="MED-0045", descricao="Seringa 5ml")))

        itens, total = produto_service.listar_paginado(sessao_db, page=1, per_page=20, sort="descricao", sort_type="asc", q="seringa")
        assert total == 1
        assert itens[0].codigo == "MED-0045"

    def test_sort_invalido_gera_422(self, sessao_db):
        with pytest.raises(HTTPException) as exc:
            produto_service.listar_paginado(sessao_db, page=1, per_page=20, sort="campo_inexistente", sort_type="asc")
        assert exc.value.status_code == 422
