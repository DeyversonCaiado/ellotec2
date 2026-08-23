"""
Testes do domínio produtos (app/domains/produtos), com foco na identificação
por `sistema_origem_id` no GET e no PUT — mesmo padrão usado em usuarios e
clientes: se o parâmetro vier preenchido, identifica o registro por ele;
senão, usa o id da URL.
"""

import pytest
from fastapi import HTTPException

from app.domains.marcas.marca_model import Marca
from app.domains.produtos import produto_service
from app.domains.produtos.produto_contrato import ProdutoAtualizarSchema, ProdutoCriarSchema


def _criar_marca(sessao_db) -> Marca:
    marca = Marca(nome="Marca Teste")
    sessao_db.add(marca)
    sessao_db.commit()
    sessao_db.refresh(marca)
    return marca


def _dados(marca_id: str, **overrides) -> dict:
    base = dict(codigo="MED-0012", descricao="Luva de Procedimento Látex P", unidade="CX", marca_id=marca_id)
    base.update(overrides)
    return base


class TestObterPorSistemaOrigemId:
    def test_obtem_por_sistema_origem_id(self, sessao_db):
        marca_id = _criar_marca(sessao_db).id
        criado = produto_service.criar(sessao_db, ProdutoCriarSchema(**_dados(marca_id, sistema_origem_id="ERP-9")))
        encontrado = produto_service.obter_por_sistema_origem_id(sessao_db, "ERP-9")
        assert encontrado.id == criado.id

    def test_sistema_origem_id_inexistente_gera_404(self, sessao_db):
        with pytest.raises(HTTPException) as exc:
            produto_service.obter_por_sistema_origem_id(sessao_db, "nao-existe")
        assert exc.value.status_code == 404


class TestAtualizar:
    def test_atualiza_por_id_quando_sistema_origem_id_nao_informado(self, sessao_db):
        marca_id = _criar_marca(sessao_db).id
        criado = produto_service.criar(sessao_db, ProdutoCriarSchema(**_dados(marca_id)))

        dados = ProdutoAtualizarSchema(**_dados(marca_id, descricao="Luva Atualizada"))
        atualizado = produto_service.atualizar(sessao_db, criado.id, dados)
        assert atualizado.descricao == "Luva Atualizada"

    def test_atualiza_por_sistema_origem_id_quando_informado(self, sessao_db):
        marca_id = _criar_marca(sessao_db).id
        criado = produto_service.criar(sessao_db, ProdutoCriarSchema(**_dados(marca_id, sistema_origem_id="ERP-9")))

        dados = ProdutoAtualizarSchema(**_dados(marca_id, descricao="Luva Atualizada"))
        atualizado = produto_service.atualizar(
            sessao_db, produto_id="id-invalido", dados=dados, sistema_origem_id="ERP-9"
        )
        assert atualizado.id == criado.id
        assert atualizado.descricao == "Luva Atualizada"

    def test_nao_apaga_sistema_origem_id_quando_corpo_nao_o_repete(self, sessao_db):
        marca_id = _criar_marca(sessao_db).id
        criado = produto_service.criar(sessao_db, ProdutoCriarSchema(**_dados(marca_id, sistema_origem_id="ERP-9")))

        dados = ProdutoAtualizarSchema(**_dados(marca_id, descricao="Luva Atualizada"))
        assert dados.sistema_origem_id is None

        atualizado = produto_service.atualizar(
            sessao_db, produto_id="irrelevante", dados=dados, sistema_origem_id="ERP-9"
        )
        assert atualizado.sistema_origem_id == "ERP-9"

    def test_sistema_origem_id_duplicado_gera_409(self, sessao_db):
        marca_id = _criar_marca(sessao_db).id
        produto_service.criar(sessao_db, ProdutoCriarSchema(**_dados(marca_id, sistema_origem_id="ERP-9")))

        dados = ProdutoCriarSchema(**_dados(marca_id, codigo="MED-0045", sistema_origem_id="ERP-9"))
        with pytest.raises(HTTPException) as exc:
            produto_service.criar(sessao_db, dados)
        assert exc.value.status_code == 409

    def test_resolve_marca_por_marca_sistema_origem_id(self, sessao_db):
        marca = _criar_marca(sessao_db)
        marca.sistema_origem_id = "MARCA-ERP-1"
        sessao_db.commit()

        dados = _dados(None, marca_sistema_origem_id="MARCA-ERP-1")
        criado = produto_service.criar(sessao_db, ProdutoCriarSchema(**dados))
        assert criado.marca_id == marca.id

    def test_marca_sistema_origem_id_tem_prioridade_sobre_marca_id(self, sessao_db):
        marca_id_errado = _criar_marca(sessao_db).id
        marca_certa = _criar_marca(sessao_db)
        marca_certa.nome = "Outra Marca"
        marca_certa.sistema_origem_id = "MARCA-ERP-2"
        sessao_db.commit()

        dados = _dados(marca_id_errado, marca_sistema_origem_id="MARCA-ERP-2")
        criado = produto_service.criar(sessao_db, ProdutoCriarSchema(**dados))
        assert criado.marca_id == marca_certa.id

    def test_sem_marca_id_e_sem_marca_sistema_origem_id_gera_erro_de_validacao(self):
        with pytest.raises(ValueError):
            ProdutoCriarSchema(**_dados(None))
