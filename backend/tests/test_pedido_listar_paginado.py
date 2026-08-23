"""
Paginação da listagem de pedidos.

Existe porque `listar` devolvia a tabela inteira com `.all()`. Com ~230 mil
pedidos — e `Pedido.itens` sendo `lazy="selectin"`, o que carrega junto os itens
de todos eles — a API caía antes de o navegador receber qualquer coisa.
"""

from datetime import date

import pytest
from fastapi import HTTPException

from app.domains.cidades.cidade_model import Cidade
from app.domains.clientes.cliente_model import Cliente
from app.domains.empresas.empresa_model import Empresa
from app.domains.pedidos import pedido_service
from app.domains.pedidos.pedido_model import Pedido, PedidoStatus


@pytest.fixture()
def cenario(sessao_db):
    """Cliente, empresa e status — as três FKs obrigatórias de um pedido."""
    cidade = Cidade(codigo_municipio=5208707, nome="Goiânia", uf="GO")
    sessao_db.add(cidade)
    sessao_db.commit()

    cliente = Cliente(
        razao_social="Distribuidora Saúde Total Ltda",
        nome_fantasia="Saúde Total",
        cpf_cnpj="12.345.678/0001-90",
        cidade_id=cidade.id,
    )
    empresa = Empresa(
        razao_social="Ellotec Matriz Ltda", nome_fantasia="Ellotec", cnpj="00.000.000/0001-00"
    )
    status = PedidoStatus(chave="PED")
    sessao_db.add_all([cliente, empresa, status])
    sessao_db.commit()
    return cliente, empresa, status


def _semear(sessao_db, cenario, quantidade: int) -> None:
    cliente, empresa, status = cenario
    for indice in range(quantidade):
        sessao_db.add(
            Pedido(
                numero=f"PED-{indice:05d}",
                data_pedido=date(2026, 8, 1 + (indice % 28)),
                cliente_id=cliente.id,
                cliente_nome_fantasia=f"Cliente {indice}",
                cliente_cnpj="12.345.678/0001-90",
                empresa_id=empresa.id,
                status_id=status.id,
                observacoes="",
            )
        )
    sessao_db.commit()


def _listar(sessao_db, **kw):
    parametros = {"page": 1, "per_page": 5, "sort": "numero", "sort_type": "asc"}
    parametros.update(kw)
    return pedido_service.listar_paginado(sessao_db, **parametros)


class TestListarPaginado:
    def test_devolve_apenas_a_pagina_pedida_e_o_total_real(self, sessao_db, cenario):
        _semear(sessao_db, cenario, 12)

        itens, total = _listar(sessao_db)

        # O total é da consulta inteira; os itens, só da página.
        assert total == 12
        assert len(itens) == 5

    def test_paginas_nao_se_sobrepoem(self, sessao_db, cenario):
        _semear(sessao_db, cenario, 12)

        pagina1, _ = _listar(sessao_db, page=1)
        pagina2, _ = _listar(sessao_db, page=2)

        assert {p.id for p in pagina1}.isdisjoint({p.id for p in pagina2})
        assert [p.numero for p in pagina1] == [f"PED-{i:05d}" for i in range(5)]
        assert [p.numero for p in pagina2] == [f"PED-{i:05d}" for i in range(5, 10)]

    def test_busca_filtra_no_banco_e_o_total_acompanha(self, sessao_db, cenario):
        _semear(sessao_db, cenario, 12)

        itens, total = _listar(sessao_db, q="PED-00003")

        assert total == 1
        assert itens[0].numero == "PED-00003"

    def test_sort_invalido_gera_422(self, sessao_db, cenario):
        # A coluna vem da query string: lista fechada, senão é injeção no ORDER BY.
        with pytest.raises(HTTPException) as excecao:
            _listar(sessao_db, sort="; drop table pedidos")

        assert excecao.value.status_code == 422
