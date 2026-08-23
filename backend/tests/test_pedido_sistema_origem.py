"""
Testes do domínio pedidos com foco em `sistema_origem_id`: obter e atualizar
um pedido por esse campo em vez do id da URL — mesmo padrão de
usuarios/produtos/clientes. Também cobre a resolução de item por
`produtoSistemaOrigemId` e de capa por `empresaSistemaOrigemId`.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.domains.cidades.cidade_model import Cidade
from app.domains.clientes.cliente_model import Cliente
from app.domains.empresas.empresa_model import Empresa
from app.domains.marcas.marca_model import Marca
from app.domains.pedidos import pedido_service
from app.domains.pedidos.pedido_contrato import PedidoAtualizarSchema, PedidoCriarSchema
from app.domains.produtos.produto_model import Produto


@pytest.fixture()
def cliente(sessao_db) -> Cliente:
    cidade = Cidade(codigo_municipio=5208707, nome="Goiânia", uf="GO")
    sessao_db.add(cidade)
    sessao_db.commit()

    registro = Cliente(
        razao_social="Distribuidora Saúde Total Ltda",
        nome_fantasia="Saúde Total",
        cpf_cnpj="12.345.678/0001-90",
        cidade_id=cidade.id,
    )
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


@pytest.fixture()
def empresa(sessao_db) -> Empresa:
    registro = Empresa(razao_social="Ellotec Matriz Ltda", nome_fantasia="Ellotec", cnpj="00.000.000/0001-00")
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


@pytest.fixture()
def produto(sessao_db) -> Produto:
    marca = Marca(nome="Marca Teste")
    sessao_db.add(marca)
    sessao_db.commit()

    registro = Produto(codigo="MED-0012", descricao="Luva de Procedimento P", marca_id=marca.id)
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


def _dados_criar(cliente, produto, empresa, **overrides) -> PedidoCriarSchema:
    base = dict(
        cliente_id=cliente.id,
        cliente_nome_fantasia=cliente.nome_fantasia,
        cliente_cnpj=cliente.cpf_cnpj,
        empresa_id=empresa.id,
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


class TestObterPorSistemaOrigemId:
    def test_obtem_por_sistema_origem_id(self, sessao_db, cliente, produto, empresa):
        criado = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa, sistema_origem_id="ERP-77"))
        encontrado = pedido_service.obter_por_sistema_origem_id(sessao_db, "ERP-77")
        assert encontrado.id == criado.id

    def test_sistema_origem_id_inexistente_gera_404(self, sessao_db):
        with pytest.raises(HTTPException) as exc:
            pedido_service.obter_por_sistema_origem_id(sessao_db, "nao-existe")
        assert exc.value.status_code == 404


class TestAtualizar:
    def test_atualiza_por_sistema_origem_id_quando_informado(self, sessao_db, cliente, produto, empresa):
        criado = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa, sistema_origem_id="ERP-77"))

        dados = PedidoAtualizarSchema(**_dados_criar(cliente, produto, empresa, observacoes="revisado").model_dump())
        atualizado = pedido_service.atualizar(
            sessao_db, pedido_id="id-invalido", dados=dados, sistema_origem_id="ERP-77"
        )
        assert atualizado.id == criado.id
        assert atualizado.observacoes == "revisado"

    def test_nao_apaga_sistema_origem_id_quando_corpo_nao_o_repete(self, sessao_db, cliente, produto, empresa):
        criado = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa, sistema_origem_id="ERP-77"))

        dados = PedidoAtualizarSchema(**_dados_criar(cliente, produto, empresa, observacoes="revisado").model_dump())
        assert dados.sistema_origem_id is None

        atualizado = pedido_service.atualizar(
            sessao_db, pedido_id="irrelevante", dados=dados, sistema_origem_id="ERP-77"
        )
        assert atualizado.sistema_origem_id == "ERP-77"

    def test_sistema_origem_id_duplicado_gera_409(self, sessao_db, cliente, produto, empresa):
        pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa, sistema_origem_id="ERP-77"))

        dados = _dados_criar(cliente, produto, empresa, sistema_origem_id="ERP-77")
        with pytest.raises(HTTPException) as exc:
            pedido_service.criar(sessao_db, dados)
        assert exc.value.status_code == 409


class TestResolucaoPorSistemaOrigem:
    def test_resolve_empresa_por_empresa_sistema_origem_id(self, sessao_db, cliente, produto, empresa):
        empresa.sistema_origem_id = "EMP-ERP-1"
        sessao_db.commit()

        dados = _dados_criar(cliente, produto, empresa).model_dump(exclude={"empresa_id"})
        dados["empresa_sistema_origem_id"] = "EMP-ERP-1"
        pedido = pedido_service.criar(sessao_db, PedidoCriarSchema(**dados))

        assert pedido.empresa_id == empresa.id

    def test_empresa_sistema_origem_id_inexistente_gera_404(self, sessao_db, cliente, produto, empresa):
        dados = _dados_criar(cliente, produto, empresa).model_dump(exclude={"empresa_id"})
        dados["empresa_sistema_origem_id"] = "nao-existe"

        with pytest.raises(HTTPException) as exc:
            pedido_service.criar(sessao_db, PedidoCriarSchema(**dados))
        assert exc.value.status_code == 404

    def test_resolve_item_por_produto_sistema_origem_id(self, sessao_db, cliente, produto, empresa):
        produto.sistema_origem_id = "PROD-ERP-1"
        sessao_db.commit()

        dados = _dados_criar(cliente, produto, empresa)
        dados.itens[0].produto_id = None
        dados.itens[0].produto_sistema_origem_id = "PROD-ERP-1"

        pedido = pedido_service.criar(sessao_db, dados)

        assert pedido.itens[0].produto_id == produto.id

    def test_produto_sistema_origem_id_inexistente_gera_404(self, sessao_db, cliente, produto, empresa):
        dados = _dados_criar(cliente, produto, empresa)
        dados.itens[0].produto_id = None
        dados.itens[0].produto_sistema_origem_id = "nao-existe"

        with pytest.raises(HTTPException) as exc:
            pedido_service.criar(sessao_db, dados)
        assert exc.value.status_code == 404

    def test_item_invalido_nao_grava_a_capa(self, sessao_db, cliente, produto, empresa):
        """Se a resolução de um item falhar antes do commit, nada foi
        persistido ainda — nem capa nem item. Prova que a rejeição não
        deixa rastro no banco (a transação nunca chegou a abrir escrita)."""
        total_antes = pedido_service.listar_paginado(sessao_db, 1, 1, "data_pedido", "desc")[1]

        dados = _dados_criar(cliente, produto, empresa)
        dados.itens[0].produto_id = None
        dados.itens[0].produto_sistema_origem_id = "nao-existe"

        with pytest.raises(HTTPException):
            pedido_service.criar(sessao_db, dados)

        assert pedido_service.listar_paginado(sessao_db, 1, 1, "data_pedido", "desc")[1] == total_antes

    def test_violacao_de_fk_no_insert_nao_deixa_capa_orfa(self, sessao_db, cliente, produto, empresa):
        """Aqui o item passa pela resolução (produto_id informado direto,
        sem sistema_origem_id) mas aponta pra um id que não existe de fato —
        só a FK do banco recusa, no INSERT. Prova que capa e itens estão na
        mesma transação: a falha no item derruba o commit inteiro, a capa
        não fica gravada sem os itens."""
        total_antes = pedido_service.listar_paginado(sessao_db, 1, 1, "data_pedido", "desc")[1]

        dados = _dados_criar(cliente, produto, empresa)
        dados.itens[0].produto_id = "id-que-nao-existe"

        with pytest.raises(IntegrityError):
            pedido_service.criar(sessao_db, dados)

        sessao_db.rollback()
        assert pedido_service.listar_paginado(sessao_db, 1, 1, "data_pedido", "desc")[1] == total_antes
