"""
Testes do domínio pedidos (app/domains/pedidos), com foco no que mudou
quando `pedidos` deixou de importar `clientes` e `produtos`:

- o snapshot (cliente e itens) é gravado a partir do payload, sem consultar
  os outros domínios;
- a integridade de `cliente_id`/`produto_id` passa a ser garantida pela FK
  do banco, não por uma busca prévia no service;
- alterar o cadastro de cliente/produto depois NÃO altera pedido já emitido.

`TestAtualizar` cobre a reconciliação: o PUT compara o payload com o que já
está gravado e atualiza NO LUGAR, em vez de apagar e recriar as linhas.
"""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.cidades.cidade_model import Cidade
from app.domains.clientes.cliente_model import Cliente
from app.domains.empresas.empresa_model import Empresa
from app.domains.marcas.marca_model import Marca
from app.domains.pedidos import pedido_service
from app.domains.pedidos.pedido_contrato import PedidoAtualizarSchema, PedidoCriarSchema
from app.domains.pedidos.pedido_model import PedidoStatus
from app.domains.produtos.produto_model import Produto

# Id fixo em vez de gerado: assim `_dados_criar` monta o payload sem receber a
# fixture do status em todos os testes do arquivo.
STATUS_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def status_pedido(sessao_db) -> PedidoStatus:
    """Todo pedido aponta para uma linha do catálogo — sem ela o INSERT viola a
    FK. Autouse porque vale para o arquivo inteiro."""
    registro = PedidoStatus(id=STATUS_ID, chave="PED")
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


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
    registro = Empresa(
        razao_social="Ellotec Matriz Ltda", nome_fantasia="Ellotec", cnpj="00.000.000/0001-00"
    )
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


@pytest.fixture()
def outro_produto(sessao_db, produto) -> Produto:
    registro = Produto(
        codigo="MED-0099", descricao="Seringa 5ml", marca_id=produto.marca_id
    )
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


def _item(produto, **overrides) -> dict:
    base = dict(
        produto_id=produto.id,
        produto_codigo=produto.codigo,
        produto_descricao=produto.descricao,
        preco_unitario="32.90",
        quantidade=2,
        lote="L-001",
    )
    base.update(overrides)
    return base


def _dados_criar(cliente, produto, empresa, **overrides) -> PedidoCriarSchema:
    base = dict(
        data_pedido=date(2026, 8, 20),
        status_id=STATUS_ID,
        cliente_id=cliente.id,
        cliente_nome_fantasia=cliente.nome_fantasia,
        cliente_cnpj=cliente.cpf_cnpj,
        empresa_id=empresa.id,
        itens=[_item(produto)],
        observacoes="",
    )
    base.update(overrides)
    return PedidoCriarSchema(**base)


def _dados_atualizar(cliente, produto, empresa, **overrides) -> PedidoAtualizarSchema:
    return PedidoAtualizarSchema(
        **_dados_criar(cliente, produto, empresa, **overrides).model_dump()
    )


class TestCriar:
    def test_grava_snapshot_do_cliente_vindo_do_payload(self, sessao_db, cliente, produto, empresa):
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))

        assert pedido.cliente_nome_fantasia == "Saúde Total"
        assert pedido.cliente_cnpj == "12.345.678/0001-90"

    def test_grava_snapshot_do_item_vindo_do_payload(self, sessao_db, cliente, produto, empresa):
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))

        assert pedido.itens[0].produto_codigo == "MED-0012"
        assert float(pedido.itens[0].preco_unitario) == 32.90

    def test_numero_sequencial(self, sessao_db, cliente, produto, empresa):
        """Sequencial numérico, sem prefixo.

        Já foi "PED-00001". O prefixo saiu porque o número do pedido é o que o
        cliente e o vendedor falam ao telefone, e código de ERP também é
        numérico — os dois no mesmo formato. Pedido que vem do ERP nem passa por
        aqui: o número dele é o `sistema_origem_id` (ver TestNumeroDoPedido em
        test_pedido_sistema_origem.py).
        """
        primeiro = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))
        segundo = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))

        assert primeiro.numero == "1"
        assert segundo.numero == "2"

    def test_cliente_inexistente_viola_fk(self, sessao_db, cliente, produto, empresa):
        dados = _dados_criar(cliente, produto, empresa, cliente_id="nao-existe")

        with pytest.raises(IntegrityError):
            pedido_service.criar(sessao_db, dados)
        sessao_db.rollback()

    def test_produto_inexistente_viola_fk(self, sessao_db, cliente, produto, empresa):
        dados = _dados_criar(cliente, produto, empresa)
        dados.itens[0].produto_id = "nao-existe"

        with pytest.raises(IntegrityError):
            pedido_service.criar(sessao_db, dados)
        sessao_db.rollback()


class TestSnapshotEhImutavel:
    def test_mudar_cadastro_do_cliente_nao_altera_pedido_emitido(
        self, sessao_db, cliente, produto, empresa
    ):
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))

        cliente.nome_fantasia = "Outro Nome"
        sessao_db.commit()

        relido = pedido_service.obter_por_id(sessao_db, pedido.id)
        assert relido.cliente_nome_fantasia == "Saúde Total"

    def test_mudar_preco_do_produto_nao_altera_pedido_emitido(
        self, sessao_db, cliente, produto, empresa
    ):
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))

        produto.descricao = "Descrição nova"
        sessao_db.commit()

        relido = pedido_service.obter_por_id(sessao_db, pedido.id)
        assert relido.itens[0].produto_descricao == "Luva de Procedimento P"
        assert float(relido.itens[0].preco_unitario) == 32.90


class TestAtualizar:
    """A reconciliação: o PUT compara o payload com o que está gravado.

    O comportamento antigo (apagar todas as linhas e inserir outras) trocava o
    id do item a cada chamada, e `expedicao_separacao_itens.pedido_item_id`
    aponta para ele — uma integração que reenviasse a capa sem mudar nada
    destruía o vínculo com a separação.
    """

    def test_o_id_do_item_sobrevive_ao_put(self, sessao_db, cliente, produto, empresa):
        """O teste central. Se este quebrar, a expedição perde o vínculo com o
        pedido em silêncio."""
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))
        id_original = pedido.itens[0].id

        atualizado = pedido_service.atualizar(
            sessao_db,
            pedido.id,
            _dados_atualizar(cliente, produto, empresa, observacoes="revisado"),
        )

        assert [item.id for item in atualizado.itens] == [id_original]

    def test_atualiza_a_linha_no_lugar_e_incrementa_versao(
        self, sessao_db, cliente, produto, empresa
    ):
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))
        id_original = pedido.itens[0].id

        dados = _dados_atualizar(
            cliente,
            produto,
            empresa,
            itens=[_item(produto, quantidade=7, preco_unitario="10.00")],
            observacoes="revisado",
        )
        atualizado = pedido_service.atualizar(sessao_db, pedido.id, dados)

        assert len(atualizado.itens) == 1
        assert atualizado.itens[0].id == id_original
        assert atualizado.itens[0].quantidade == 7
        assert float(atualizado.itens[0].preco_unitario) == 10.00
        assert atualizado.itens[0].sync_version == 2
        assert atualizado.observacoes == "revisado"
        assert atualizado.sync_version == 2

    def test_linha_nova_no_payload_e_inserida(
        self, sessao_db, cliente, produto, outro_produto, empresa
    ):
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))

        dados = _dados_atualizar(
            cliente, produto, empresa, itens=[_item(produto), _item(outro_produto)]
        )
        atualizado = pedido_service.atualizar(sessao_db, pedido.id, dados)

        vivos = [item for item in atualizado.itens if item.sync_deleted_at is None]
        assert {item.produto_id for item in vivos} == {produto.id, outro_produto.id}

    def test_linha_que_sai_do_payload_e_soft_delete(
        self, sessao_db, cliente, produto, outro_produto, empresa
    ):
        """Nunca DELETE físico: a FK da expedição aponta para esta linha, e o
        ARCHITECTURE.md proíbe `delete()` em model com SyncMixin."""
        pedido = pedido_service.criar(
            sessao_db,
            _dados_criar(cliente, produto, empresa, itens=[_item(produto), _item(outro_produto)]),
        )
        id_removido = next(i.id for i in pedido.itens if i.produto_id == outro_produto.id)

        atualizado = pedido_service.atualizar(
            sessao_db, pedido.id, _dados_atualizar(cliente, produto, empresa)
        )

        removido = next(i for i in atualizado.itens if i.id == id_removido)
        assert removido.sync_deleted_at is not None

    def test_linha_apagada_que_volta_e_revivida_no_mesmo_id(
        self, sessao_db, cliente, produto, outro_produto, empresa
    ):
        """Reinserir bateria no unique `(pedido, produto, lote)`, que enxerga a
        linha soft-deletada ocupando a chave. E reviver preserva o id, que é o
        que a expedição referencia."""
        pedido = pedido_service.criar(
            sessao_db,
            _dados_criar(cliente, produto, empresa, itens=[_item(produto), _item(outro_produto)]),
        )
        id_original = next(i.id for i in pedido.itens if i.produto_id == outro_produto.id)

        pedido_service.atualizar(
            sessao_db, pedido.id, _dados_atualizar(cliente, produto, empresa)
        )
        atualizado = pedido_service.atualizar(
            sessao_db,
            pedido.id,
            _dados_atualizar(
                cliente, produto, empresa, itens=[_item(produto), _item(outro_produto)]
            ),
        )

        revivida = next(i for i in atualizado.itens if i.produto_id == outro_produto.id)
        assert revivida.id == id_original
        assert revivida.sync_deleted_at is None

    def test_o_mesmo_produto_em_lote_diferente_e_outra_linha(
        self, sessao_db, cliente, produto, empresa
    ):
        """A chave é `(produto, lote)`. Trocar o lote não é editar a linha, é
        outra mercadoria."""
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))
        id_original = pedido.itens[0].id

        dados = _dados_atualizar(cliente, produto, empresa, itens=[_item(produto, lote="L-002")])
        atualizado = pedido_service.atualizar(sessao_db, pedido.id, dados)

        vivos = [item for item in atualizado.itens if item.sync_deleted_at is None]
        assert len(vivos) == 1
        assert vivos[0].id != id_original
        assert vivos[0].lote == "L-002"

    def test_reenviar_a_capa_sem_mudar_nada_nao_mexe_nos_itens(
        self, sessao_db, cliente, produto, empresa
    ):
        """O caso mais comum da integração — e o que mais doía: cada reenvio
        recriava as linhas."""
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))
        antes = [(item.id, item.quantidade) for item in pedido.itens]

        pedido_service.atualizar(
            sessao_db, pedido.id, _dados_atualizar(cliente, produto, empresa)
        )
        pedido_service.atualizar(
            sessao_db, pedido.id, _dados_atualizar(cliente, produto, empresa)
        )
        relido = pedido_service.obter_por_id(sessao_db, pedido.id)

        vivos = [item for item in relido.itens if item.sync_deleted_at is None]
        assert [(item.id, item.quantidade) for item in vivos] == antes

    def test_pedido_inexistente_gera_404(self, sessao_db, cliente, produto, empresa):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            pedido_service.atualizar(
                sessao_db, "id-que-nao-existe", _dados_atualizar(cliente, produto, empresa)
            )
        assert excinfo.value.status_code == 404


class TestApagar:
    def test_apagar_marca_soft_delete(self, sessao_db, cliente, produto, empresa):
        from fastapi import HTTPException

        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))
        pedido_service.apagar(sessao_db, pedido.id)

        with pytest.raises(HTTPException) as excinfo:
            pedido_service.obter_por_id(sessao_db, pedido.id)
        assert excinfo.value.status_code == 404
