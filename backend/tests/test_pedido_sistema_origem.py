"""
Testes do domínio pedidos com foco em `sistema_origem_id`: obter e atualizar
um pedido por esse campo em vez do id da URL — mesmo padrão de
usuarios/produtos/clientes. Também cobre a resolução de item por
`produtoSistemaOrigemId` e de capa por `empresaSistemaOrigemId`.
"""

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.domains.cidades.cidade_model import Cidade
from app.domains.clientes.cliente_model import Cliente
from app.domains.empresas.empresa_model import Empresa
from app.domains.marcas.marca_model import Marca
from app.domains.pedidos import pedido_service
from app.domains.pedidos.pedido_contrato import PedidoAtualizarSchema, PedidoCriarSchema
from app.domains.pedidos.pedido_model import PedidoStatus
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


# Id fixo em vez de gerado: assim `_dados_criar` monta o payload sem receber a
# fixture do status em todos os testes do arquivo.
STATUS_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def status_pedido(sessao_db) -> PedidoStatus:
    """Todo pedido aponta para uma linha do catálogo `pedido_status` — sem ela
    o INSERT viola a FK. Autouse porque vale para o arquivo inteiro."""
    registro = PedidoStatus(id=STATUS_ID, chave="PED")
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


def _dados_criar(cliente, produto, empresa, **overrides) -> PedidoCriarSchema:
    base = dict(
        data_pedido=date(2026, 8, 20),
        status_id=STATUS_ID,
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


class TestChaveNaturalDoItemNoErp:
    """O ERP não dá id próprio à linha do item: ele a identifica pela chave
    natural **empresa + pedido + produto**. As três colunas existem para essa
    linha poder ser localizada pelo que o ERP conhece — ver pedido_model.py."""

    def test_grava_o_trio_informado_no_item(self, sessao_db, cliente, produto, empresa):
        produto.sistema_origem_id = "PROD-ERP-1"
        sessao_db.commit()

        dados = _dados_criar(cliente, produto, empresa)
        dados.itens[0].empresa_sistema_origem_id = "EMP-ERP-1"
        dados.itens[0].pedido_sistema_origem_id = "PED-ERP-1"
        dados.itens[0].produto_sistema_origem_id = "PROD-ERP-1"

        pedido = pedido_service.criar(sessao_db, dados)

        assert pedido.itens[0].empresa_sistema_origem_id == "EMP-ERP-1"
        assert pedido.itens[0].pedido_sistema_origem_id == "PED-ERP-1"
        assert pedido.itens[0].produto_sistema_origem_id == "PROD-ERP-1"

    def test_item_herda_empresa_e_pedido_da_capa(self, sessao_db, cliente, produto, empresa):
        """Todos os itens de um pedido são da mesma empresa e do mesmo pedido.
        Obrigar a integração a repetir os dois textos em cada linha só criaria
        chance de divergir, então a capa serve de padrão."""
        empresa.sistema_origem_id = "EMP-ERP-1"
        sessao_db.commit()

        dados = _dados_criar(cliente, produto, empresa).model_dump(exclude={"empresa_id"})
        dados["empresa_sistema_origem_id"] = "EMP-ERP-1"
        dados["sistema_origem_id"] = "PED-ERP-1"
        pedido = pedido_service.criar(sessao_db, PedidoCriarSchema(**dados))

        assert pedido.itens[0].empresa_sistema_origem_id == "EMP-ERP-1"
        assert pedido.itens[0].pedido_sistema_origem_id == "PED-ERP-1"

    def test_item_manda_no_proprio_valor_quando_informa(self, sessao_db, cliente, produto, empresa):
        empresa.sistema_origem_id = "EMP-ERP-1"
        sessao_db.commit()

        dados = _dados_criar(cliente, produto, empresa).model_dump(exclude={"empresa_id"})
        dados["empresa_sistema_origem_id"] = "EMP-ERP-1"
        dados["sistema_origem_id"] = "PED-ERP-1"
        dados["itens"][0]["empresa_sistema_origem_id"] = "EMP-ERP-2"
        dados["itens"][0]["pedido_sistema_origem_id"] = "PED-ERP-2"
        pedido = pedido_service.criar(sessao_db, PedidoCriarSchema(**dados))

        assert pedido.itens[0].empresa_sistema_origem_id == "EMP-ERP-2"
        assert pedido.itens[0].pedido_sistema_origem_id == "PED-ERP-2"

    def test_produto_sistema_origem_id_resolve_a_fk_e_fica_gravado(
        self, sessao_db, cliente, produto, empresa
    ):
        """O mesmo campo faz as duas coisas: acha o produto e vira a terceira
        perna da chave. Antes ele só resolvia a FK e era descartado."""
        produto.sistema_origem_id = "PROD-ERP-1"
        sessao_db.commit()

        dados = _dados_criar(cliente, produto, empresa)
        dados.itens[0].produto_id = None
        dados.itens[0].produto_sistema_origem_id = "PROD-ERP-1"

        pedido = pedido_service.criar(sessao_db, dados)

        assert pedido.itens[0].produto_id == produto.id
        assert pedido.itens[0].produto_sistema_origem_id == "PROD-ERP-1"

    def test_item_da_tela_fica_sem_chave_de_origem(self, sessao_db, cliente, produto, empresa):
        """Nulo significa "não veio de integração", e isso é verdade — não é
        dado faltando."""
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))

        assert pedido.itens[0].empresa_sistema_origem_id is None
        assert pedido.itens[0].pedido_sistema_origem_id is None
        assert pedido.itens[0].produto_sistema_origem_id is None

    def test_o_mesmo_produto_em_pedidos_diferentes_convive(
        self, sessao_db, cliente, produto, empresa
    ):
        """A razão de a perna do PEDIDO existir: sem ela, (empresa, produto)
        casaria com a linha de qualquer pedido da mesma empresa."""
        primeiro = _dados_criar(cliente, produto, empresa)
        primeiro.itens[0].empresa_sistema_origem_id = "EMP-ERP-1"
        primeiro.itens[0].pedido_sistema_origem_id = "PED-ERP-1"
        pedido_service.criar(sessao_db, primeiro)

        segundo = _dados_criar(cliente, produto, empresa)
        segundo.itens[0].empresa_sistema_origem_id = "EMP-ERP-1"
        segundo.itens[0].pedido_sistema_origem_id = "PED-ERP-2"
        criado = pedido_service.criar(sessao_db, segundo)

        assert criado.itens[0].pedido_sistema_origem_id == "PED-ERP-2"

    def test_atualizar_regrava_o_trio_dos_itens(self, sessao_db, cliente, produto, empresa):
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))

        dados = _dados_criar(cliente, produto, empresa).model_dump()
        dados["itens"][0]["empresa_sistema_origem_id"] = "EMP-ERP-1"
        dados["itens"][0]["pedido_sistema_origem_id"] = "PED-ERP-9"
        atualizado = pedido_service.atualizar(sessao_db, pedido.id, PedidoAtualizarSchema(**dados))

        assert atualizado.itens[0].empresa_sistema_origem_id == "EMP-ERP-1"
        assert atualizado.itens[0].pedido_sistema_origem_id == "PED-ERP-9"

    def test_atualizar_preserva_o_pedido_de_origem_usado_para_localizar(
        self, sessao_db, cliente, produto, empresa
    ):
        """No PUT que acha o pedido pela query string, o corpo pode não repetir
        o `sistemaOrigemId`. Os itens não podem ficar sem a perna do pedido por
        causa desse detalhe de transporte."""
        criacao = _dados_criar(cliente, produto, empresa).model_dump()
        criacao["sistema_origem_id"] = "PED-ERP-7"
        pedido_service.criar(sessao_db, PedidoCriarSchema(**criacao))

        # corpo SEM sistema_origem_id — ele vem só na query string
        dados = _dados_criar(cliente, produto, empresa).model_dump()
        atualizado = pedido_service.atualizar(
            sessao_db, "ignorado", PedidoAtualizarSchema(**dados), sistema_origem_id="PED-ERP-7"
        )

        assert atualizado.itens[0].pedido_sistema_origem_id == "PED-ERP-7"


class TestNumeroDoPedido:
    """Um pedido tem UM identificador: o do ERP quando ele vem de lá, e um
    sequencial numérico daqui quando nasce na tela.

    Antes o pedido integrado ficava com dois códigos — "PED-00918" aqui e
    "0000148" no ERP — e todo mundo tinha que saber os dois. A correção não foi
    copiar um no outro: foi deixar `numero` NULO quando existe
    `sistema_origem_id`, para não haver duas colunas que possam divergir.
    """

    def test_numero_fica_nulo_quando_o_pedido_vem_do_erp(self, sessao_db, cliente, produto, empresa):
        pedido = pedido_service.criar(
            sessao_db, _dados_criar(cliente, produto, empresa, sistema_origem_id="0186657")
        )

        assert pedido.numero is None
        assert pedido.sistema_origem_id == "0186657"

    def test_sem_sistema_origem_id_o_numero_e_sequencial_numerico(
        self, sessao_db, cliente, produto, empresa
    ):
        """Sem prefixo: o número é o que se fala ao telefone, e ninguém dita
        'pê-é-dê-traço'."""
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))

        assert pedido.numero.isdigit(), pedido.numero
        assert pedido.sistema_origem_id is None

    def test_varios_pedidos_do_erp_convivem_com_numero_nulo(
        self, sessao_db, cliente, produto, empresa
    ):
        """No MySQL dois NULL não colidem num índice único, então
        `uq_pedidos_numero_empresa_id` não barra vários pedidos sem número na
        mesma empresa. Este teste roda em SQLite, que se comporta igual nisso."""
        primeiro = pedido_service.criar(
            sessao_db, _dados_criar(cliente, produto, empresa, sistema_origem_id="0186657")
        )
        segundo = pedido_service.criar(
            sessao_db, _dados_criar(cliente, produto, empresa, sistema_origem_id="0186658")
        )

        assert primeiro.numero is None
        assert segundo.numero is None
        assert primeiro.id != segundo.id

    def test_ganhar_sistema_origem_id_solta_o_numero_local(
        self, sessao_db, cliente, produto, empresa
    ):
        """Pedido criado aqui e integrado depois larga o sequencial local: quem
        identifica passa a ser o ERP, e manter os dois recria a pergunta "qual
        dos dois vale?"."""
        pedido = pedido_service.criar(sessao_db, _dados_criar(cliente, produto, empresa))
        assert pedido.numero is not None

        atualizado = pedido_service.atualizar(
            sessao_db,
            pedido.id,
            PedidoAtualizarSchema(
                **_dados_criar(
                    cliente, produto, empresa, sistema_origem_id="0186657"
                ).model_dump()
            ),
        )

        assert atualizado.numero is None
        assert atualizado.sistema_origem_id == "0186657"
