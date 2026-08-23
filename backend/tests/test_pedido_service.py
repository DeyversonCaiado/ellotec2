"""
Testes do domínio pedidos (app/domains/pedidos), com foco no que mudou
quando `pedidos` deixou de importar `clientes` e `produtos`:

- o snapshot (cliente e itens) é gravado a partir do payload, sem consultar
  os outros domínios;
- a integridade de `cliente_id`/`produto_id` passa a ser garantida pela FK
  do banco, não por uma busca prévia no service;
- alterar o cadastro de cliente/produto depois NÃO altera pedido já emitido.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.clientes.cliente_model import Cliente
from app.domains.pedidos import pedido_service
from app.domains.pedidos.pedido_contrato import PedidoAtualizarSchema, PedidoCriarSchema
from app.domains.produtos.produto_model import Produto


@pytest.fixture()
def cliente(sessao_db) -> Cliente:
    registro = Cliente(
        razao_social="Distribuidora Saúde Total Ltda",
        nome_fantasia="Saúde Total",
        cnpj="12.345.678/0001-90",
    )
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


@pytest.fixture()
def produto(sessao_db) -> Produto:
    registro = Produto(codigo="MED-0012", descricao="Luva de Procedimento P", preco_unitario=32.90, estoque=10)
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


def _dados_criar(cliente, produto, **overrides) -> PedidoCriarSchema:
    base = dict(
        cliente_id=cliente.id,
        cliente_nome_fantasia=cliente.nome_fantasia,
        cliente_cnpj=cliente.cnpj,
        itens=[
            dict(
                produto_id=produto.id,
                produto_codigo=produto.codigo,
                produto_descricao=produto.descricao,
                preco_unitario="32.90",
                quantidade=2,
            )
        ],
        observacoes="",
    )
    base.update(overrides)
    return PedidoCriarSchema(**base)


class TestCriar:
    def test_grava_snapshot_do_cliente_vindo_do_payload(self, sessao_db, cliente, produto):
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto))

        assert pedido.cliente_id == cliente.id
        assert pedido.cliente_nome_fantasia == "Saúde Total"
        assert pedido.cliente_cnpj == "12.345.678/0001-90"

    def test_grava_snapshot_do_item_vindo_do_payload(self, sessao_db, cliente, produto):
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto))

        item = pedido.itens[0]
        assert item.produto_codigo == "MED-0012"
        assert item.produto_descricao == "Luva de Procedimento P"
        assert float(item.preco_unitario) == 32.90
        assert item.quantidade == 2

    def test_numero_sequencial(self, sessao_db, cliente, produto):
        primeiro = pedido_service.criar(sessao_db, _dados_criar(cliente, produto))
        segundo = pedido_service.criar(sessao_db, _dados_criar(cliente, produto))

        assert primeiro.numero == "PED-00001"
        assert segundo.numero == "PED-00002"

    def test_cliente_inexistente_viola_fk(self, sessao_db, cliente, produto):
        """A barreira é a FK do banco — o service não consulta clientes."""
        with pytest.raises(IntegrityError):
            pedido_service.criar(sessao_db, _dados_criar(cliente, produto, cliente_id="id-que-nao-existe"))

    def test_produto_inexistente_viola_fk(self, sessao_db, cliente, produto):
        itens = [
            dict(
                produto_id="id-que-nao-existe",
                produto_codigo="X",
                produto_descricao="X",
                preco_unitario="1.00",
                quantidade=1,
            )
        ]
        with pytest.raises(IntegrityError):
            pedido_service.criar(sessao_db, _dados_criar(cliente, produto, itens=itens))


class TestSnapshotEhImutavel:
    def test_mudar_cadastro_do_cliente_nao_altera_pedido_emitido(self, sessao_db, cliente, produto):
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto))

        cliente.nome_fantasia = "Saúde Total Distribuidora"
        sessao_db.commit()

        relido = pedido_service.obter_por_id(sessao_db, pedido.id)
        assert relido.cliente_nome_fantasia == "Saúde Total"

    def test_mudar_preco_do_produto_nao_altera_pedido_emitido(self, sessao_db, cliente, produto):
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto))

        produto.preco_unitario = 99.90
        sessao_db.commit()

        relido = pedido_service.obter_por_id(sessao_db, pedido.id)
        assert float(relido.itens[0].preco_unitario) == 32.90


class TestAtualizar:
    def test_substitui_itens_e_incrementa_versao(self, sessao_db, cliente, produto):
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto))

        dados = PedidoAtualizarSchema(
            cliente_id=cliente.id,
            cliente_nome_fantasia=cliente.nome_fantasia,
            cliente_cnpj=cliente.cnpj,
            itens=[
                dict(
                    produto_id=produto.id,
                    produto_codigo=produto.codigo,
                    produto_descricao=produto.descricao,
                    preco_unitario="10.00",
                    quantidade=7,
                )
            ],
            observacoes="revisado",
        )
        atualizado = pedido_service.atualizar(sessao_db, pedido.id, dados)

        assert len(atualizado.itens) == 1
        assert atualizado.itens[0].quantidade == 7
        assert atualizado.observacoes == "revisado"
        assert atualizado.sync_version == 2

    def test_pedido_inexistente_gera_404(self, sessao_db, cliente, produto):
        from fastapi import HTTPException

        dados = PedidoAtualizarSchema(**_dados_criar(cliente, produto).model_dump())
        with pytest.raises(HTTPException) as excinfo:
            pedido_service.atualizar(sessao_db, "id-que-nao-existe", dados)
        assert excinfo.value.status_code == 404


class TestApagar:
    def test_apagar_marca_soft_delete(self, sessao_db, cliente, produto):
        from fastapi import HTTPException

        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto))
        pedido_service.apagar(sessao_db, pedido.id)

        with pytest.raises(HTTPException) as excinfo:
            pedido_service.obter_por_id(sessao_db, pedido.id)
        assert excinfo.value.status_code == 404
