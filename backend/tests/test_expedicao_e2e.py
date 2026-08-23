"""
End-to-end da expedição, batendo na API por HTTP (TestClient) sobre um SQLite
em memória — não toca o MySQL de dev/produção.

O que fica de fora, de propósito: JWT, device_id e fingerprint. `obter_usuario_atual`
é substituído por um override que devolve o usuário "logado" da vez (trocável no
meio do teste, pra exercitar "quem começou termina"). Tudo o mais roda de verdade,
inclusive `exigir_permissao` — que depende do override e continua lendo as chaves
reais gravadas em `usuario_permissoes`.
"""

from collections.abc import Generator
from datetime import date  # noqa: F401  usado nos testes de período

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth.dependencies import ContextoRequisicao, obter_usuario_atual
from app.core.auth.seguranca import gerar_hash_senha
from app.core.database import todos_os_models  # noqa: F401
from app.core.database.conexao import Base, obter_sessao
from app.domains.cidades.cidade_model import Cidade
from app.domains.clientes.cliente_model import Cliente
from app.domains.empresas.empresa_model import Empresa
from app.domains.marcas.marca_model import Marca
from app.domains.pedidos import pedido_publico
from app.domains.pedidos.pedido_model import Pedido, PedidoItem, PedidoStatus
from app.domains.produtos.produto_model import Produto, ProdutoCodigoBarras
from app.domains.usuarios.cargo_model import Cargo
from app.domains.usuarios.usuario_model import Usuario, UsuarioPermissao
from app.main import app

SENHA_GERENTE = "gerente123"

PERMISSOES_OPERADOR = [
    "expedicao.acessar",
    "expedicao.separacao.executar",
    "expedicao.conferencia.executar",
    "expedicao.resetar",
]

# Quem distribui trabalho. A diferença é `expedicao.atribuir`, e ela decide o
# que a listagem devolve: coordenador vê a fila inteira, operador vê só o que
# foi atribuído a ele. O usuário padrão dos testes é o coordenador, porque a
# maioria deles exercita a fila completa.
PERMISSOES_COORDENADOR = [*PERMISSOES_OPERADOR, "expedicao.atribuir"]

CODIGO_BARRAS_A = "7891111111111"
CODIGO_BARRAS_B = "7892222222222"
DUN_14_A = "17891111111111"
CODIGO_LOGISTICA_A = "7893333333333"


class Cenario:
    """Ids do cenário montado no `dados`, pra não ficar procurando por índice."""

    def __init__(self, **ids: str) -> None:
        self.__dict__.update(ids)


@pytest.fixture()
def ambiente() -> Generator[tuple[TestClient, Session, Cenario, dict], None, None]:
    # StaticPool é obrigatório aqui (e não no conftest): o TestClient atende a
    # requisição em outra thread, e o pool padrão do SQLite in-memory dá uma
    # conexão — logo, um banco vazio — por thread.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _ativar_fk(conexao_dbapi, _registro):  # noqa: ANN001
        cursor = conexao_dbapi.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    SessaoTeste = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sessao = SessaoTeste()

    cargo_func = Cargo(nome="Funcionario")
    cargo_ger = Cargo(nome="Gerente")
    cidade = Cidade(codigo_municipio=5208707, nome="Goiânia", uf="GO")
    marca = Marca(nome="Danone")
    empresa = Empresa(razao_social="Ellotec LTDA", nome_fantasia="Ellotec", cnpj="00.000.000/0001-00")
    status_ped = PedidoStatus(chave="PED")
    status_orc = PedidoStatus(chave="ORC")
    # As etapas do galpão vêm da migration d4a6f8c02b19 em produção; aqui o
    # catálogo é criado do zero a cada teste.
    status_etapas = [PedidoStatus(chave=chave) for chave in pedido_publico.STATUS_DA_EXPEDICAO[1:]]
    sessao.add_all(
        [cargo_func, cargo_ger, cidade, marca, empresa, status_ped, status_orc, *status_etapas]
    )
    sessao.commit()

    separador = Usuario(
        usuario="separador",
        nome="Separador Um",
        email="sep@ellotec.local",
        senha_hash=gerar_hash_senha("x"),
        cargo_id=cargo_func.id,
        permissoes=[UsuarioPermissao(chave=chave) for chave in PERMISSOES_COORDENADOR],
    )
    outro = Usuario(
        usuario="outro",
        nome="Operador Dois",
        email="outro@ellotec.local",
        senha_hash=gerar_hash_senha("x"),
        cargo_id=cargo_func.id,
        permissoes=[UsuarioPermissao(chave=chave) for chave in PERMISSOES_OPERADOR],
    )
    sem_conferencia = Usuario(
        usuario="so.separa",
        nome="Só Separa",
        email="so@ellotec.local",
        senha_hash=gerar_hash_senha("x"),
        cargo_id=cargo_func.id,
        permissoes=[
            UsuarioPermissao(chave="expedicao.acessar"),
            UsuarioPermissao(chave="expedicao.separacao.executar"),
        ],
    )
    gerente = Usuario(
        usuario="gerente",
        nome="Gerente Chefe",
        email="ger@ellotec.local",
        senha_hash=gerar_hash_senha(SENHA_GERENTE),
        cargo_id=cargo_ger.id,
        permissoes=[UsuarioPermissao(chave=chave) for chave in PERMISSOES_OPERADOR],
    )
    cliente = Cliente(
        razao_social="Clinica Santa Monica LTDA",
        nome_fantasia="Santa Monica",
        cpf_cnpj="11.111.111/0001-11",
        logradouro="R EM 1S/N Quadra Area",
        numero="Lote 02",
        bairro="Villa Sul",
        cep="74910-520",
        cidade_id=cidade.id,
    )
    produto_a = Produto(
        codigo="A-001",
        descricao="Nutrison EN 1000ml",
        codigo_barra_notas=CODIGO_BARRAS_A,
        dun_14=DUN_14_A,
        marca_id=marca.id,
        # `codigo_pro` no ERP — é ele que vai no WHERE do update em fat_produtos.
        sistema_origem_id="PRO-A",
    )
    produto_b = Produto(
        codigo="B-002", descricao="Nutrison Prot Plus", codigo_barra_notas=CODIGO_BARRAS_B, marca_id=marca.id
    )
    sessao.add_all([separador, outro, sem_conferencia, gerente, cliente, produto_a, produto_b])
    sessao.commit()

    pedido = Pedido(
        numero="PED-00001",
        data_pedido=date(2026, 8, 17),
        cliente_id=cliente.id,
        cliente_nome_fantasia="Santa Monica",
        cliente_cnpj="11.111.111/0001-11",
        empresa_id=empresa.id,
        vendedor_id=separador.id,
        sistema_origem_id="0185972",
        status_id=status_ped.id,
        observacoes="PEDIDO ELETRONICO:1005879",
        itens=[
            PedidoItem(
                produto_id=produto_a.id,
                produto_codigo="A-001",
                produto_descricao="Nutrison EN 1000ml",
                quantidade=3,
                preco_unitario=10,
                endereco_produto="07-14-08-03-01",
                lote="111580721",
            ),
            PedidoItem(
                produto_id=produto_b.id,
                produto_codigo="B-002",
                produto_descricao="Nutrison Prot Plus",
                quantidade=2,
                preco_unitario=20,
                endereco_produto="07-14-08-03-02",
                lote="111616986",
            ),
        ],
    )
    # Pedido fora do status PED — não pode entrar na expedição.
    pedido_orcamento = Pedido(
        numero="PED-00002",
        data_pedido=date(2026, 8, 17),
        cliente_id=cliente.id,
        cliente_nome_fantasia="Santa Monica",
        cliente_cnpj="11.111.111/0001-11",
        empresa_id=empresa.id,
        status_id=status_orc.id,
        itens=[
            PedidoItem(
                produto_id=produto_a.id,
                produto_codigo="A-001",
                produto_descricao="Nutrison EN 1000ml",
                quantidade=1,
                preco_unitario=10,
            )
        ],
    )
    sessao.add_all([pedido, pedido_orcamento])
    sessao.commit()

    cenario = Cenario(
        pedido_id=pedido.id,
        pedido_orcamento_id=pedido_orcamento.id,
        item_a_id=pedido.itens[0].id,
        item_b_id=pedido.itens[1].id,
        separador_id=separador.id,
        outro_id=outro.id,
        sem_conferencia_id=sem_conferencia.id,
        gerente_id=gerente.id,
    )
    # Mutável de propósito: os testes trocam quem está "logado" só reatribuindo
    # `logado["id"]`, sem recriar o client.
    logado = {"id": separador.id}

    def _sessao_de_teste() -> Generator[Session, None, None]:
        yield sessao

    def _usuario_de_teste() -> ContextoRequisicao:
        usuario = sessao.query(Usuario).filter(Usuario.id == logado["id"]).one()
        return ContextoRequisicao(usuario=usuario, dispositivo_id="dispositivo-de-teste")

    app.dependency_overrides[obter_sessao] = _sessao_de_teste
    app.dependency_overrides[obter_usuario_atual] = _usuario_de_teste

    try:
        yield TestClient(app), sessao, cenario, logado
    finally:
        app.dependency_overrides.clear()
        sessao.close()
        engine.dispose()


def _bipar(client: TestClient, tipo: str, processo_id: str, item_id: str, codigo: str, mult: int = 1):
    return client.post(
        f"/expedicao/{tipo}/{processo_id}/itens/{item_id}/bipar",
        json={"codigoBarras": codigo, "multiplicador": mult},
    )


def _processar_item_completo(client: TestClient, tipo: str, processo_id: str, item_id: str, codigo: str, qtd: int):
    assert client.post(f"/expedicao/{tipo}/{processo_id}/itens/{item_id}/iniciar").status_code == 200
    assert _bipar(client, tipo, processo_id, item_id, codigo, qtd).status_code == 200
    return client.post(f"/expedicao/{tipo}/{processo_id}/itens/{item_id}/finalizar", json={})


def test_listagem_traz_pedido_de_qualquer_status(ambiente):
    """A tela lista tudo para consulta; o status é que decide quem pode ser
    trabalhado (campo `podeIniciar`)."""
    client, _, cenario, _ = ambiente

    resposta = client.get("/expedicao/pedidos")

    assert resposta.status_code == 200
    pagina = resposta.json()
    assert pagina["total"] == 2
    assert pagina["page"] == 1
    por_id = {p["pedidoId"]: p for p in pagina["items"]}
    assert set(por_id) == {cenario.pedido_id, cenario.pedido_orcamento_id}

    liberado = por_id[cenario.pedido_id]
    assert liberado["statusPedido"] == "PED"
    assert liberado["podeIniciar"] is True
    assert liberado["separacao"]["status"] == "nao_iniciada"
    assert liberado["conferencia"]["status"] == "nao_iniciada"
    assert liberado["quantidadeTotal"] == 5
    # cidade vem do cadastro vivo do cliente, não do snapshot do pedido
    assert liberado["clienteCidadeNome"] == "Goiânia"
    assert liberado["clienteCidadeUf"] == "GO"

    orcamento = por_id[cenario.pedido_orcamento_id]
    assert orcamento["statusPedido"] == "ORC"
    assert orcamento["podeIniciar"] is False


def test_listagem_filtra_pela_data_do_pedido(ambiente):
    """O período é sobre a data do pedido — a data que o usuário vê na tela —,
    não sobre quando o registro foi alterado."""
    client, _, _, _ = ambiente

    fora = client.get(
        "/expedicao/pedidos", params={"dataInicio": "2020-01-01", "dataFim": "2020-01-31"}
    ).json()
    assert fora["total"] == 0
    assert fora["items"] == []

    # os dois pedidos do cenário são de 17/08/2026
    dentro = client.get(
        "/expedicao/pedidos", params={"dataInicio": "2026-08-17", "dataFim": "2026-08-17"}
    ).json()
    assert dentro["total"] == 2

    # e a borda do dia entra: início e fim inclusivos
    borda = client.get(
        "/expedicao/pedidos", params={"dataInicio": "2026-08-17", "dataFim": "2026-08-18"}
    ).json()
    assert borda["total"] == 2


def test_listagem_pagina_no_banco(ambiente):
    client, _, _, _ = ambiente

    primeira = client.get("/expedicao/pedidos", params={"page": 1, "perPage": 1}).json()
    segunda = client.get("/expedicao/pedidos", params={"page": 2, "perPage": 1}).json()

    assert primeira["total"] == segunda["total"] == 2
    assert len(primeira["items"]) == len(segunda["items"]) == 1
    assert primeira["items"][0]["pedidoId"] != segunda["items"][0]["pedidoId"]


def test_busca_por_numero_e_cliente(ambiente):
    client, _, cenario, _ = ambiente

    por_numero = client.get("/expedicao/pedidos", params={"q": "0185972"}).json()
    assert [p["pedidoId"] for p in por_numero["items"]] == [cenario.pedido_id]

    por_cliente = client.get("/expedicao/pedidos", params={"q": "santa monica"}).json()
    assert por_cliente["total"] == 2

    sem_resultado = client.get("/expedicao/pedidos", params={"q": "nao-existe"}).json()
    assert sem_resultado["total"] == 0


def test_detalhe_traz_cliente_vendedor_e_proxima_etapa(ambiente):
    client, _, cenario, _ = ambiente

    detalhe = client.get(f"/expedicao/pedidos/{cenario.pedido_id}").json()

    assert detalhe["numero"] == "PED-00001"
    assert detalhe["clienteRazaoSocial"] == "Clinica Santa Monica LTDA"
    # endereço vem do cadastro vivo do cliente, não do snapshot do pedido
    assert detalhe["clienteEndereco"] == "R EM 1S/N Quadra Area, Lote 02"
    assert detalhe["clienteCidadeUf"] == "GO"
    assert detalhe["vendedorNome"] == "Separador Um"
    assert detalhe["proximaEtapa"] == "separacao"
    assert len(detalhe["itens"]) == 2
    # múltiplo de venda vem do cadastro vivo do produto, não do snapshot do item
    assert detalhe["itens"][0]["quantidadeMultiplaVenda"] == 1


def test_conferencia_exige_separacao_finalizada(ambiente):
    client, _, cenario, _ = ambiente

    resposta = client.post(f"/expedicao/conferencia/pedidos/{cenario.pedido_id}/iniciar")

    assert resposta.status_code == 409
    assert "separação" in resposta.json()["detail"].lower()


def test_pedido_fora_do_status_ped_nao_entra_na_expedicao(ambiente):
    client, _, cenario, _ = ambiente

    resposta = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_orcamento_id}/iniciar")

    assert resposta.status_code == 409
    assert "ORC" in resposta.json()["detail"]


def test_pedido_fora_de_ped_aparece_na_lista_mas_nao_pode_iniciar(ambiente):
    """Consultar é livre, trabalhar não: quem decide é o status do ERP."""
    client, sessao, cenario, _ = ambiente
    cancelado = PedidoStatus(chave="CAN")
    sessao.add(cancelado)
    sessao.commit()
    pedido = sessao.query(Pedido).filter(Pedido.id == cenario.pedido_id).one()
    pedido.status_id = cancelado.id
    sessao.commit()

    pagina = client.get("/expedicao/pedidos").json()
    linha = next(p for p in pagina["items"] if p["pedidoId"] == cenario.pedido_id)
    assert linha["statusPedido"] == "CAN"
    assert linha["podeIniciar"] is False

    recusado = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar")
    assert recusado.status_code == 409
    assert "CAN" in recusado.json()["detail"]

    detalhe = client.get(f"/expedicao/pedidos/{cenario.pedido_id}").json()
    assert detalhe["podeIniciar"] is False


def _status_expedicao(client: TestClient, pedido_id: str):
    return client.get(f"/expedicao/pedidos/{pedido_id}").json()["expedicaoStatus"]


def test_status_do_galpao_acompanha_as_etapas(ambiente):
    """A expedição grava o andamento em expedicao_pedido_status — nunca em
    pedidos.status_id, que é da integração."""
    client, sessao, cenario, _ = ambiente
    assert _status_expedicao(client, cenario.pedido_id) is None

    separacao = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    assert _status_expedicao(client, cenario.pedido_id) == "em_separacao"

    _processar_item_completo(client, "separacao", separacao["id"], cenario.item_a_id, CODIGO_BARRAS_A, 3)
    _processar_item_completo(client, "separacao", separacao["id"], cenario.item_b_id, CODIGO_BARRAS_B, 2)
    assert _status_expedicao(client, cenario.pedido_id) == "separado"

    conferencia = client.post(f"/expedicao/conferencia/pedidos/{cenario.pedido_id}/iniciar").json()
    assert _status_expedicao(client, cenario.pedido_id) == "em_conferencia"

    _processar_item_completo(client, "conferencia", conferencia["id"], cenario.item_a_id, CODIGO_BARRAS_A, 3)
    _processar_item_completo(client, "conferencia", conferencia["id"], cenario.item_b_id, CODIGO_BARRAS_B, 2)
    assert _status_expedicao(client, cenario.pedido_id) == "conferido"

    # o status do PEDIDO não foi tocado — é o que protege o andamento de ser
    # sobrescrito na próxima sincronização do ERP
    pedido = sessao.query(Pedido).filter(Pedido.id == cenario.pedido_id).one()
    assert sessao.query(PedidoStatus).filter(PedidoStatus.id == pedido.status_id).one().chave == "PED"

    # e a listagem lê o mesmo status
    pagina = client.get("/expedicao/pedidos").json()
    linha = next(p for p in pagina["items"] if p["pedidoId"] == cenario.pedido_id)
    assert linha["expedicaoStatus"] == "conferido"


def test_reset_devolve_o_status_do_galpao(ambiente):
    client, _, cenario, logado = ambiente
    separacao = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    _processar_item_completo(client, "separacao", separacao["id"], cenario.item_a_id, CODIGO_BARRAS_A, 3)
    _processar_item_completo(client, "separacao", separacao["id"], cenario.item_b_id, CODIGO_BARRAS_B, 2)
    conferencia = client.post(f"/expedicao/conferencia/pedidos/{cenario.pedido_id}/iniciar").json()

    credencial = {"usuarioGerente": "gerente", "senha": SENHA_GERENTE}

    # resetar a conferência volta ao marco anterior, que continua verdadeiro
    assert client.post(
        f"/expedicao/conferencia/{conferencia['id']}/resetar", json=credencial
    ).status_code == 204
    assert _status_expedicao(client, cenario.pedido_id) == "separado"

    # resetar a separação apaga a passagem pelo galpão
    assert client.post(
        f"/expedicao/separacao/{separacao['id']}/resetar", json=credencial
    ).status_code == 204
    assert _status_expedicao(client, cenario.pedido_id) is None


def test_fluxo_completo_separacao_depois_conferencia(ambiente):
    client, _, cenario, _ = ambiente

    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    assert processo["status"] == "em_andamento"
    assert {item["situacao"] for item in processo["itens"]} == {"pendente"}

    # Reentrar devolve o MESMO processo, não cria outro.
    assert client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()["id"] == processo["id"]

    resposta = _processar_item_completo(
        client, "separacao", processo["id"], cenario.item_a_id, CODIGO_BARRAS_A, 3
    )
    assert resposta.status_code == 200
    item_a = next(i for i in resposta.json()["itens"] if i["pedidoItemId"] == cenario.item_a_id)
    assert item_a["situacao"] == "finalizado"
    assert item_a["divergente"] is False
    assert item_a["dataInicio"] and item_a["dataFim"]  # tempo por item medido

    resposta = _processar_item_completo(
        client, "separacao", processo["id"], cenario.item_b_id, CODIGO_BARRAS_B, 2
    )
    assert resposta.json()["status"] == "finalizada"

    detalhe = client.get(f"/expedicao/pedidos/{cenario.pedido_id}").json()
    assert detalhe["separacao"]["status"] == "finalizada"
    assert detalhe["proximaEtapa"] == "conferencia"

    conferencia = client.post(f"/expedicao/conferencia/pedidos/{cenario.pedido_id}/iniciar").json()
    _processar_item_completo(client, "conferencia", conferencia["id"], cenario.item_a_id, CODIGO_BARRAS_A, 3)
    final = _processar_item_completo(
        client, "conferencia", conferencia["id"], cenario.item_b_id, CODIGO_BARRAS_B, 2
    )
    assert final.json()["status"] == "finalizada"

    detalhe = client.get(f"/expedicao/pedidos/{cenario.pedido_id}").json()
    assert detalhe["proximaEtapa"] is None


def test_so_um_item_por_vez(ambiente):
    client, _, cenario, _ = ambiente
    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()

    client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/iniciar")
    resposta = client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_b_id}/iniciar")

    assert resposta.status_code == 409
    assert "item em andamento" in resposta.json()["detail"].lower()


def test_reentrar_no_item_nao_reinicia_o_cronometro(ambiente):
    client, _, cenario, _ = ambiente
    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()

    primeira = client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/iniciar").json()
    segunda = client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/iniciar").json()

    inicio = lambda resp: next(i for i in resp["itens"] if i["pedidoItemId"] == cenario.item_a_id)["dataInicio"]  # noqa: E731
    assert inicio(primeira) == inicio(segunda)


def test_quem_comecou_termina(ambiente):
    client, _, cenario, logado = ambiente
    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()

    logado["id"] = cenario.outro_id
    resposta = client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/iniciar")

    assert resposta.status_code == 403
    assert "outro usuário" in resposta.json()["detail"]


def test_permissao_de_conferencia_e_separada_da_de_separacao(ambiente):
    client, _, cenario, logado = ambiente
    logado["id"] = cenario.sem_conferencia_id

    # separação passa
    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar")
    assert processo.status_code == 200

    _processar_item_completo(client, "separacao", processo.json()["id"], cenario.item_a_id, CODIGO_BARRAS_A, 3)
    _processar_item_completo(client, "separacao", processo.json()["id"], cenario.item_b_id, CODIGO_BARRAS_B, 2)

    # conferência não
    resposta = client.post(f"/expedicao/conferencia/pedidos/{cenario.pedido_id}/iniciar")
    assert resposta.status_code == 403
    assert "expedicao.conferencia.executar" in resposta.json()["detail"]


def test_bipagem_recusa_codigo_desconhecido_produto_errado_e_excesso(ambiente):
    client, _, cenario, _ = ambiente
    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/iniciar")

    inexistente = _bipar(client, "separacao", processo["id"], cenario.item_a_id, "0000000000000")
    assert inexistente.status_code == 422
    assert "não cadastrado" in inexistente.json()["detail"]

    outro_produto = _bipar(client, "separacao", processo["id"], cenario.item_a_id, CODIGO_BARRAS_B)
    assert outro_produto.status_code == 422
    assert "outro produto" in outro_produto.json()["detail"]

    # o item pede 3 — multiplicador 4 estoura
    excesso = _bipar(client, "separacao", processo["id"], cenario.item_a_id, CODIGO_BARRAS_A, 4)
    assert excesso.status_code == 422
    assert "acima da pedida" in excesso.json()["detail"]

    # e nada foi contabilizado nas recusas
    processo_atual = client.get(f"/expedicao/separacao/{processo['id']}").json()
    item = next(i for i in processo_atual["itens"] if i["pedidoItemId"] == cenario.item_a_id)
    assert item["quantidadeProcessada"] == 0


def test_bipagem_aceita_dun_14_quando_codigo_de_barras_nao_resolve(ambiente):
    """O operador bipou a caixa, não a unidade: o EAN não acha nada e o DUN-14
    resolve o mesmo produto."""
    client, _, cenario, _ = ambiente
    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/iniciar")

    assert _bipar(client, "separacao", processo["id"], cenario.item_a_id, DUN_14_A).status_code == 200

    atual = client.get(f"/expedicao/separacao/{processo['id']}").json()
    item = next(i for i in atual["itens"] if i["pedidoItemId"] == cenario.item_a_id)
    assert item["quantidadeProcessada"] == 1

    # o fallback não afrouxa a checagem de produto: um número que não está em
    # nenhum dos dois campos continua sendo recusado
    desconhecido = _bipar(client, "separacao", processo["id"], cenario.item_a_id, "19999999999999")
    assert desconhecido.status_code == 422
    assert "não cadastrado" in desconhecido.json()["detail"]


def test_bipagem_aceita_codigo_de_logistica_cadastrado(ambiente):
    """O código impresso na caixa do distribuidor não é o da nota nem o DUN-14 —
    está na lista de logística do produto, e é lá que a bipagem tem que achar."""
    client, sessao, cenario, _ = ambiente
    produto_a = sessao.query(Produto).filter(Produto.codigo == "A-001").one()
    sessao.add(ProdutoCodigoBarras(produto_id=produto_a.id, codigo=CODIGO_LOGISTICA_A))
    sessao.commit()

    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/iniciar")

    aceita = _bipar(client, "separacao", processo["id"], cenario.item_a_id, CODIGO_LOGISTICA_A)
    assert aceita.status_code == 200, aceita.text

    atual = client.get(f"/expedicao/separacao/{processo['id']}").json()
    item = next(i for i in atual["itens"] if i["pedidoItemId"] == cenario.item_a_id)
    assert item["quantidadeProcessada"] == 1
    # e a tela mostra o código de logística separado do código da nota
    assert item["produtoCodigosBarrasLogistica"] == [CODIGO_LOGISTICA_A]
    assert item["produtoCodigoBarraNotas"] == CODIGO_BARRAS_A


def test_bipagem_extrai_o_gtin_de_um_qrcode_gs1(ambiente):
    """O coletor leu um QR Code, não um código linear: o conteúdo traz lote e
    validade junto, e o produto está no AI 01. Sem extrair o GTIN, a leitura
    inteira seria procurada no cadastro e não acharia nada."""
    client, _, cenario, _ = ambiente
    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/iniciar")

    # AI 01 com o EAN-13 do produto zerado à esquerda para 14, depois validade e lote
    qrcode = f"01{DUN_14_A}1726010110LOTE123"
    aceita = _bipar(client, "separacao", processo["id"], cenario.item_a_id, qrcode)
    assert aceita.status_code == 200, aceita.text

    atual = client.get(f"/expedicao/separacao/{processo['id']}").json()
    item = next(i for i in atual["itens"] if i["pedidoItemId"] == cenario.item_a_id)
    assert item["quantidadeProcessada"] == 1


def test_qrcode_com_gtin_de_outro_produto_continua_sendo_recusado(ambiente):
    """Extrair o GTIN não afrouxa a checagem: o código extraído passa pelas
    mesmas regras do código linear."""
    client, _, cenario, _ = ambiente
    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/iniciar")

    recusada = _bipar(
        client, "separacao", processo["id"], cenario.item_a_id, f"010{CODIGO_BARRAS_B}10LOTE"
    )
    assert recusada.status_code == 422
    assert "outro produto" in recusada.json()["detail"]


def test_bipagem_multiplica_pela_embalagem_de_venda(ambiente):
    """Produto vendido só em caixa fechada: o pedido continua em unidade, mas
    cada leitura no coletor vale a caixa inteira."""
    client, sessao, cenario, _ = ambiente
    produto_b = sessao.query(Produto).filter(Produto.codigo == "B-002").one()
    produto_b.quantidade_multipla_venda = 2
    sessao.commit()

    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_b_id}/iniciar")

    # o item pede 2 unidades — uma caixa fecha o item num bipe só
    assert _bipar(client, "separacao", processo["id"], cenario.item_b_id, CODIGO_BARRAS_B).status_code == 200
    atual = client.get(f"/expedicao/separacao/{processo['id']}").json()
    item = next(i for i in atual["itens"] if i["pedidoItemId"] == cenario.item_b_id)
    assert item["quantidadeProcessada"] == 2

    # e a segunda caixa estoura, com a explicação do porquê no erro
    excesso = _bipar(client, "separacao", processo["id"], cenario.item_b_id, CODIGO_BARRAS_B)
    assert excesso.status_code == 422
    assert "vale 2 unidades" in excesso.json()["detail"]


def test_bipar_exige_item_iniciado(ambiente):
    client, _, cenario, _ = ambiente
    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()

    resposta = _bipar(client, "separacao", processo["id"], cenario.item_a_id, CODIGO_BARRAS_A)

    assert resposta.status_code == 409
    assert "Inicie este item" in resposta.json()["detail"]


def test_finalizar_com_falta_exige_gerente(ambiente):
    client, _, cenario, _ = ambiente
    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/iniciar")
    _bipar(client, "separacao", processo["id"], cenario.item_a_id, CODIGO_BARRAS_A, 2)  # falta 1

    sem_senha = client.post(
        f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/finalizar", json={}
    )
    # 422, não 401: credencial de gerente é campo do payload, não a sessão de
    # quem chama — ver _autorizar_gerente em expedicao_service.py.
    assert sem_senha.status_code == 422

    senha_errada = client.post(
        f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/finalizar",
        json={"usuarioGerente": "gerente", "senha": "errada"},
    )
    assert senha_errada.status_code == 422

    nao_gerente = client.post(
        f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/finalizar",
        json={"usuarioGerente": "outro", "senha": "x"},
    )
    assert nao_gerente.status_code == 422

    autorizado = client.post(
        f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/finalizar",
        json={"usuarioGerente": "gerente", "senha": SENHA_GERENTE},
    )
    assert autorizado.status_code == 200
    item = next(i for i in autorizado.json()["itens"] if i["pedidoItemId"] == cenario.item_a_id)
    assert item["situacao"] == "finalizado"
    assert item["divergente"] is True


def test_reset_exige_gerente_e_e_soft_delete(ambiente):
    client, sessao, cenario, _ = ambiente
    from app.domains.expedicao.expedicao_model import Separacao

    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    _processar_item_completo(client, "separacao", processo["id"], cenario.item_a_id, CODIGO_BARRAS_A, 3)

    recusado = client.post(
        f"/expedicao/separacao/{processo['id']}/resetar",
        json={"usuarioGerente": "outro", "senha": "x"},
    )
    assert recusado.status_code == 422

    aceito = client.post(
        f"/expedicao/separacao/{processo['id']}/resetar",
        json={"usuarioGerente": "gerente", "senha": SENHA_GERENTE},
    )
    assert aceito.status_code == 204

    # soft delete: a linha continua no banco, com o histórico de tempo por item
    apagada = sessao.query(Separacao).filter(Separacao.id == processo["id"]).one()
    assert apagada.sync_deleted_at is not None
    assert all(item.sync_deleted_at is not None for item in apagada.itens)
    assert any(item.data_fim is not None for item in apagada.itens)

    # e o pedido volta a poder ser separado do zero
    detalhe = client.get(f"/expedicao/pedidos/{cenario.pedido_id}").json()
    assert detalhe["separacao"]["status"] == "nao_iniciada"
    novo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    assert novo["id"] != processo["id"]


def test_reset_de_separacao_bloqueado_enquanto_houver_conferencia_viva(ambiente):
    client, _, cenario, _ = ambiente
    separacao = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    _processar_item_completo(client, "separacao", separacao["id"], cenario.item_a_id, CODIGO_BARRAS_A, 3)
    _processar_item_completo(client, "separacao", separacao["id"], cenario.item_b_id, CODIGO_BARRAS_B, 2)
    conferencia = client.post(f"/expedicao/conferencia/pedidos/{cenario.pedido_id}/iniciar").json()

    credencial = {"usuarioGerente": "gerente", "senha": SENHA_GERENTE}
    bloqueado = client.post(f"/expedicao/separacao/{separacao['id']}/resetar", json=credencial)
    assert bloqueado.status_code == 409
    assert "conferência" in bloqueado.json()["detail"].lower()

    # resetando a conferência primeiro, a separação libera
    assert client.post(f"/expedicao/conferencia/{conferencia['id']}/resetar", json=credencial).status_code == 204
    assert client.post(f"/expedicao/separacao/{separacao['id']}/resetar", json=credencial).status_code == 204


# ---------------------------------------------------------------------------
# Atribuição de pedidos
#
# A regra central: quem NÃO tem `expedicao.atribuir` só enxerga pedido em que
# ele é responsável por alguma etapa — e enxerga lista vazia enquanto nada
# tiver sido atribuído a ele. É decisão de negócio (trabalho empurrado pelo
# coordenador), e a barreira é a consulta do backend, não a tela.
# ---------------------------------------------------------------------------


def test_operador_sem_atribuicao_nao_ve_nenhum_pedido(ambiente):
    client, _sessao, cenario, logado = ambiente

    logado["id"] = cenario.outro_id
    resposta = client.get("/expedicao/pedidos")

    assert resposta.status_code == 200
    assert resposta.json()["items"] == []
    # O total precisa bater com o que se vê: dizer "2 pedidos no período" numa
    # lista vazia é pior que não mostrar nada.
    assert resposta.json()["total"] == 0


def test_coordenador_ve_a_fila_inteira(ambiente):
    client, _sessao, _cenario, _logado = ambiente

    resposta = client.get("/expedicao/pedidos")

    assert resposta.status_code == 200
    assert resposta.json()["total"] > 0


def test_operador_ve_o_pedido_depois_de_atribuido(ambiente):
    client, _sessao, cenario, logado = ambiente

    atribuicao = client.post(
        "/expedicao/atribuicoes",
        json={"pedidoIds": [cenario.pedido_id], "tipo": "separacao", "usuarioId": cenario.outro_id},
    )
    assert atribuicao.status_code == 204

    logado["id"] = cenario.outro_id
    resposta = client.get("/expedicao/pedidos")

    itens = resposta.json()["items"]
    assert [item["pedidoId"] for item in itens] == [cenario.pedido_id]
    assert itens[0]["atribuicaoSeparacao"]["usuarioNome"] == "Operador Dois"
    # Quem distribuiu fica registrado — é o que responde "quem mandou fulano
    # separar esse pedido?".
    assert itens[0]["atribuicaoSeparacao"]["atribuidoPorNome"] == "Separador Um"


def test_atribuicao_de_uma_etapa_nao_vale_para_a_outra(ambiente):
    client, _sessao, cenario, logado = ambiente

    client.post(
        "/expedicao/atribuicoes",
        json={"pedidoIds": [cenario.pedido_id], "tipo": "separacao", "usuarioId": cenario.outro_id},
    )

    logado["id"] = cenario.outro_id
    item = client.get("/expedicao/pedidos").json()["items"][0]
    assert item["atribuicaoSeparacao"] is not None
    assert item["atribuicaoConferencia"] is None


def test_operador_nao_inicia_processo_atribuido_a_outro(ambiente):
    client, _sessao, cenario, logado = ambiente

    client.post(
        "/expedicao/atribuicoes",
        json={"pedidoIds": [cenario.pedido_id], "tipo": "separacao", "usuarioId": cenario.outro_id},
    )

    # Sem esta trava a atribuição seria só enfeite: bastava saber a URL.
    logado["id"] = cenario.sem_conferencia_id
    resposta = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar")

    assert resposta.status_code == 403
    assert "atribuída a outro operador" in resposta.json()["detail"]


def test_usuario_id_nulo_remove_a_atribuicao(ambiente):
    client, _sessao, cenario, logado = ambiente

    client.post(
        "/expedicao/atribuicoes",
        json={"pedidoIds": [cenario.pedido_id], "tipo": "separacao", "usuarioId": cenario.outro_id},
    )
    remocao = client.post(
        "/expedicao/atribuicoes",
        json={"pedidoIds": [cenario.pedido_id], "tipo": "separacao", "usuarioId": None},
    )
    assert remocao.status_code == 204

    logado["id"] = cenario.outro_id
    assert client.get("/expedicao/pedidos").json()["items"] == []


def test_reatribuir_troca_o_responsavel_sem_deixar_duas_vivas(ambiente):
    client, sessao, cenario, _logado = ambiente
    from app.domains.expedicao.expedicao_model import ExpedicaoAtribuicao

    for usuario_id in (cenario.outro_id, cenario.sem_conferencia_id):
        client.post(
            "/expedicao/atribuicoes",
            json={"pedidoIds": [cenario.pedido_id], "tipo": "separacao", "usuarioId": usuario_id},
        )

    vivas = (
        sessao.query(ExpedicaoAtribuicao)
        .filter(
            ExpedicaoAtribuicao.pedido_id == cenario.pedido_id,
            ExpedicaoAtribuicao.tipo == "separacao",
            ExpedicaoAtribuicao.sync_deleted_at.is_(None),
        )
        .all()
    )
    assert len(vivas) == 1
    assert vivas[0].usuario_id == cenario.sem_conferencia_id
    # A anterior continua no banco, soft-deletada: quem atribuiu o quê e quando
    # é rastro de auditoria, não lixo a apagar.
    assert sessao.query(ExpedicaoAtribuicao).count() == 2


def test_nao_muda_responsavel_de_processo_em_andamento(ambiente):
    client, _sessao, cenario, _logado = ambiente

    client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar")

    resposta = client.post(
        "/expedicao/atribuicoes",
        json={"pedidoIds": [cenario.pedido_id], "tipo": "separacao", "usuarioId": cenario.outro_id},
    )

    # O caminho certo é resetar (que exige senha de gerente) e só então
    # redistribuir — desatribuir aqui deixaria o processo vivo sem dono.
    assert resposta.status_code == 409
    assert "Resete o processo" in resposta.json()["detail"]


def test_atribuir_exige_permissao(ambiente):
    client, _sessao, cenario, logado = ambiente

    logado["id"] = cenario.outro_id
    resposta = client.post(
        "/expedicao/atribuicoes",
        json={"pedidoIds": [cenario.pedido_id], "tipo": "separacao", "usuarioId": cenario.outro_id},
    )

    assert resposta.status_code == 403
    assert "expedicao.atribuir" in resposta.json()["detail"]


def test_seletor_de_operadores_so_traz_quem_executa_a_etapa(ambiente):
    client, _sessao, _cenario, _logado = ambiente

    nomes_conferencia = [item["nome"] for item in client.get("/expedicao/operadores/conferencia").json()]

    # "Só Separa" não tem `expedicao.conferencia.executar` — atribuir uma
    # conferência a ele seria criar um trabalho que ele não consegue abrir.
    assert "Só Separa" not in nomes_conferencia
    assert "Operador Dois" in nomes_conferencia
    assert "Só Separa" in [item["nome"] for item in client.get("/expedicao/operadores/separacao").json()]


# ---------------------------------------------------------------------------
# A tela de expedição não pode depender de permissão de OUTRO domínio.
#
# Regressão real: a listagem chamava GET /pedidos/status (que exige
# `pedidos.acessar`) para montar o filtro. O operador de galpão não tem essa
# chave, o 403 subia, e o interceptor do front tratava como "suas permissões
# mudaram" e devolvia o usuário para a tela inicial — parecendo falta de
# permissão na expedição, que ele tinha.
# ---------------------------------------------------------------------------


def test_operador_carrega_a_tela_sem_permissao_no_dominio_de_pedidos(ambiente):
    client, sessao, cenario, logado = ambiente
    from app.domains.usuarios.usuario_model import Usuario

    operador = sessao.query(Usuario).filter(Usuario.id == cenario.outro_id).one()
    chaves = {permissao.chave for permissao in operador.permissoes}
    assert "pedidos.acessar" not in chaves, "o cenário precisa de um operador SEM acesso a pedidos"

    logado["id"] = cenario.outro_id

    # As duas chamadas que a listagem dispara ao abrir.
    assert client.get("/expedicao/pedidos").status_code == 200
    catalogo = client.get("/expedicao/status-pedido")
    assert catalogo.status_code == 200
    assert pedido_publico.STATUS_LIBERADO_PARA_EXPEDICAO in catalogo.json()


def test_filtros_de_empresa_e_operador_saem_do_cadastro_e_nao_da_pagina(ambiente):
    """Regressão real: os dois filtros eram montados a partir dos pedidos da
    página carregada. A matriz sumia da lista quando nenhum pedido dela caía
    naquela página, e o operador que ainda não tinha pegado pedido nenhum não
    aparecia — justamente quem o coordenador queria procurar."""
    client, sessao, cenario, _logado = ambiente
    from app.domains.empresas.empresa_model import Empresa

    # Uma empresa sem nenhum pedido: é o caso que a lista tirada da página perdia.
    sessao.add(Empresa(razao_social="Filial Sem Pedido LTDA", nome_fantasia="Filial Zero", cnpj="99.999.999/0001-99"))
    sessao.commit()

    empresas = client.get("/expedicao/empresas")
    assert empresas.status_code == 200, empresas.text
    assert "Filial Zero" in [linha["nome"] for linha in empresas.json()]

    # E o operador que pode separar mas não está em pedido nenhum.
    operadores = client.get("/expedicao/operadores")
    assert operadores.status_code == 200, operadores.text
    nomes = [linha["nome"] for linha in operadores.json()]
    assert "Só Separa" in nomes
    # A lista é a união das duas etapas, sem repetir quem executa as duas.
    assert len(nomes) == len(set(nomes))


def test_filtros_da_listagem_nao_dependem_dos_dominios_donos(ambiente):
    """`empresas.acessar` e `usuarios.acessar` não podem ser exigidos aqui: o
    operador de galpão não tem nenhuma das duas, e o 403 derrubaria a tela
    inteira (mesmo motivo de `/expedicao/status-pedido` existir)."""
    client, sessao, cenario, logado = ambiente
    from app.domains.usuarios.usuario_model import Usuario

    operador = sessao.query(Usuario).filter(Usuario.id == cenario.outro_id).one()
    chaves = {permissao.chave for permissao in operador.permissoes}
    assert "empresas.acessar" not in chaves
    assert "usuarios.acessar" not in chaves

    logado["id"] = cenario.outro_id

    assert client.get("/expedicao/empresas").status_code == 200
    assert client.get("/expedicao/operadores").status_code == 200


def test_catalogo_de_status_ainda_exige_acesso_a_expedicao(ambiente):
    client, sessao, cenario, logado = ambiente
    from app.domains.usuarios.usuario_model import Usuario, UsuarioPermissao

    sem_nada = Usuario(
        usuario="sem.expedicao",
        nome="Sem Expedição",
        email="sem@ellotec.local",
        senha_hash="x",
        cargo_id=sessao.query(Usuario).filter(Usuario.id == cenario.outro_id).one().cargo_id,
        permissoes=[UsuarioPermissao(chave="produtos.acessar")],
    )
    sessao.add(sem_nada)
    sessao.commit()

    logado["id"] = sem_nada.id
    assert client.get("/expedicao/status-pedido").status_code == 403


# ---------------------------------------------------------------------------
# End-to-end da atribuição: o caminho que o galpão percorre de verdade.
#
# Coordenador distribui → operador enxerga o que é dele → separa → só então a
# conferência pode ser atribuída → conferente enxerga → quem não é o designado
# não abre. Cada passo é uma trava distinta, e todas moram no backend.
# ---------------------------------------------------------------------------


def _ids_visiveis(client) -> set[str]:
    return {item["pedidoId"] for item in client.get("/expedicao/pedidos").json()["items"]}


def _atribuir(client, pedido_id, tipo, usuario_id):
    return client.post(
        "/expedicao/atribuicoes",
        json={"pedidoIds": [pedido_id], "tipo": tipo, "usuarioId": usuario_id},
    )


def test_e2e_atribuicao_da_distribuicao_ate_a_conferencia(ambiente):
    client, _sessao, cenario, logado = ambiente

    # --- 1. Antes de distribuir: o operador não enxerga nada -----------------
    logado["id"] = cenario.outro_id
    assert _ids_visiveis(client) == set()

    logado["id"] = cenario.separador_id  # coordenador (tem expedicao.atribuir)
    assert cenario.pedido_id in _ids_visiveis(client)

    # --- 2. Conferência ainda não pode ser atribuída -------------------------
    # A separação nem começou. Designar a conferência agora colocaria o pedido
    # na fila do conferente só para dar 409 no clique dele.
    recusa = _atribuir(client, cenario.pedido_id, "conferencia", cenario.outro_id)
    assert recusa.status_code == 409
    assert "separação" in recusa.json()["detail"]

    # --- 3. Coordenador atribui a separação ----------------------------------
    assert _atribuir(client, cenario.pedido_id, "separacao", cenario.outro_id).status_code == 204

    # --- 4. Agora o designado enxerga; quem não foi designado, não ----------
    logado["id"] = cenario.outro_id
    assert _ids_visiveis(client) == {cenario.pedido_id}

    logado["id"] = cenario.sem_conferencia_id
    assert _ids_visiveis(client) == set()
    # E não abre pela URL: a atribuição barra de fato, não é só enfeite de tela.
    assert (
        client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").status_code == 403
    )

    # --- 5. O designado separa o pedido inteiro ------------------------------
    logado["id"] = cenario.outro_id
    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    _processar_item_completo(
        client, "separacao", processo["id"], cenario.item_a_id, CODIGO_BARRAS_A, 3
    )
    fim = _processar_item_completo(
        client, "separacao", processo["id"], cenario.item_b_id, CODIGO_BARRAS_B, 2
    )
    assert fim.json()["status"] == "finalizada"

    # --- 6. Com a separação fechada, a conferência já pode ser atribuída -----
    logado["id"] = cenario.separador_id
    assert _atribuir(client, cenario.pedido_id, "conferencia", cenario.sem_conferencia_id).status_code == 204

    # --- 7. O pedido aparece para o conferente ------------------------------
    logado["id"] = cenario.sem_conferencia_id
    assert _ids_visiveis(client) == {cenario.pedido_id}

    # --- 8. Quem separou não confere: a etapa é de outro ---------------------
    logado["id"] = cenario.outro_id
    negado = client.post(f"/expedicao/conferencia/pedidos/{cenario.pedido_id}/iniciar")
    assert negado.status_code == 403
    assert "atribuída a outro operador" in negado.json()["detail"]

    # ...mas continua enxergando o pedido, porque ainda é o dono da separação.
    assert _ids_visiveis(client) == {cenario.pedido_id}


def test_remover_atribuicao_de_conferencia_indevida_sempre_funciona(ambiente):
    """A trava do passo 2 vale só para ATRIBUIR. Se uma atribuição indevida
    existir (dado legado, correção de rota), desfazer não pode ficar bloqueado."""
    client, sessao, cenario, _logado = ambiente
    from app.domains.expedicao.expedicao_model import ExpedicaoAtribuicao
    from datetime import datetime

    sessao.add(
        ExpedicaoAtribuicao(
            pedido_id=cenario.pedido_id,
            tipo="conferencia",
            usuario_id=cenario.outro_id,
            atribuido_por_id=cenario.separador_id,
            data_atribuicao=datetime(2026, 8, 20, 12, 0, 0),
        )
    )
    sessao.commit()

    remocao = _atribuir(client, cenario.pedido_id, "conferencia", None)

    assert remocao.status_code == 204
    assert (
        sessao.query(ExpedicaoAtribuicao)
        .filter(
            ExpedicaoAtribuicao.pedido_id == cenario.pedido_id,
            ExpedicaoAtribuicao.sync_deleted_at.is_(None),
        )
        .count()
        == 0
    )


# ---------------------------------------------------------------------------
# Tempos: o relógio do galpão.
#
# O início de uma etapa é o PRIMEIRO BIPE, não a abertura do processo — entre
# abrir a lista e bipar o primeiro item o operador ainda está indo até o
# endereço, e esse tempo não é separação.
# ---------------------------------------------------------------------------


def test_primeiro_bipe_e_carimbado_uma_vez_so(ambiente):
    client, sessao, cenario, _logado = ambiente
    from app.domains.expedicao.expedicao_model import Separacao

    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    capa = sessao.query(Separacao).filter(Separacao.id == processo["id"]).one()
    # Abrir o processo não é começar a trabalhar.
    assert capa.data_primeiro_bipe is None

    client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/iniciar")
    _bipar(client, "separacao", processo["id"], cenario.item_a_id, CODIGO_BARRAS_A, 1)
    sessao.expire_all()
    primeiro = sessao.query(Separacao).filter(Separacao.id == processo["id"]).one().data_primeiro_bipe
    assert primeiro is not None

    _bipar(client, "separacao", processo["id"], cenario.item_a_id, CODIGO_BARRAS_A, 1)
    sessao.expire_all()
    # A segunda leitura não mexe mais: o marco é do PRIMEIRO bipe.
    assert sessao.query(Separacao).filter(Separacao.id == processo["id"]).one().data_primeiro_bipe == primeiro


def test_listagem_expoe_os_tempos_das_duas_etapas(ambiente):
    client, _sessao, cenario, _logado = ambiente

    processo = client.post(f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar").json()
    _processar_item_completo(
        client, "separacao", processo["id"], cenario.item_a_id, CODIGO_BARRAS_A, 3
    )

    item = next(
        p
        for p in client.get("/expedicao/pedidos").json()["items"]
        if p["pedidoId"] == cenario.pedido_id
    )

    assert item["separacao"]["dataPrimeiroBipe"] is not None
    # Ainda em andamento: sem fim, o badge do front conta até agora.
    assert item["separacao"]["dataFim"] is None
    # Conferência nem começou.
    assert item["conferencia"]["dataPrimeiroBipe"] is None
    # O campo do milestone existe no contrato mesmo sem o ERP ter mandado.
    assert "liberadoEm" in item


# ---------------------------------------------------------------------------
# Filtros da listagem, sobre a BASE inteira e não sobre a página carregada
#
# Regressão real: empresa, operador e situação eram aplicados no front, sobre os
# pedidos que tinham vindo na página. Com paginação isso responde "não achei"
# para pedido que existe na página seguinte, e mostra um total que não bate com
# as linhas na tela.
#
# Por isso todo teste daqui usa `perPage=1`: com uma linha por página, filtro
# que recorta a página carregada não tem como acertar. Se o total bater e o
# item vier certo, o filtro rodou no banco.
# ---------------------------------------------------------------------------


def _pedido_extra(sessao, cliente, empresa, status, produto, numero: str):
    """Um pedido de uma linha, para montar situações variadas na fila."""
    pedido = Pedido(
        numero=numero,
        data_pedido=date(2026, 8, 17),
        cliente_id=cliente.id,
        cliente_nome_fantasia="Santa Monica",
        cliente_cnpj="11.111.111/0001-11",
        empresa_id=empresa.id,
        status_id=status.id,
        itens=[
            PedidoItem(
                produto_id=produto.id,
                produto_codigo="A-001",
                produto_descricao="Nutrison EN 1000ml",
                quantidade=1,
                preco_unitario=10,
            )
        ],
    )
    sessao.add(pedido)
    sessao.commit()
    return pedido


def _abrir(client, tipo, pedido_id) -> str:
    resposta = client.post(f"/expedicao/{tipo}/pedidos/{pedido_id}/iniciar")
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["id"]


def _executar_etapa(client, tipo, pedido_id, item_id, *, completo=True, credencial=None) -> str:
    """Abre a etapa e fecha o item — completo, ou com falta autorizada."""
    processo_id = _abrir(client, tipo, pedido_id)
    assert client.post(f"/expedicao/{tipo}/{processo_id}/itens/{item_id}/iniciar").status_code == 200
    if completo:
        assert _bipar(client, tipo, processo_id, item_id, CODIGO_BARRAS_A).status_code == 200
    fechamento = client.post(
        f"/expedicao/{tipo}/{processo_id}/itens/{item_id}/finalizar", json=credencial or {}
    )
    assert fechamento.status_code == 200, fechamento.text
    return processo_id


@pytest.fixture()
def galpao(ambiente):
    """Uma fila com duas empresas, dois operadores e uma situação de cada.

    Montada pela API, não por INSERT: as situações que o filtro tem que
    reconhecer nascem do processo de expedição rodando de verdade — abrir,
    bipar, finalizar — e não de um estado escrito à mão, que pode divergir do
    que o sistema realmente produz.
    """
    client, sessao, cenario, logado = ambiente
    from app.domains.empresas.empresa_model import Empresa

    matriz = sessao.query(Empresa).one()
    filial = Empresa(
        razao_social="Ellotec Filial LTDA", nome_fantasia="Filial Sul", cnpj="22.222.222/0001-22"
    )
    sessao.add(filial)
    sessao.commit()

    cliente = sessao.query(Cliente).one()
    produto_a = sessao.query(Produto).filter(Produto.codigo == "A-001").one()
    status_ped = sessao.query(PedidoStatus).filter(PedidoStatus.chave == "PED").one()

    nao_iniciado = _pedido_extra(sessao, cliente, filial, status_ped, produto_a, "PED-10001")
    em_separacao = _pedido_extra(sessao, cliente, matriz, status_ped, produto_a, "PED-10002")
    aguardando = _pedido_extra(sessao, cliente, matriz, status_ped, produto_a, "PED-10003")
    em_conferencia = _pedido_extra(sessao, cliente, filial, status_ped, produto_a, "PED-10004")
    concluido = _pedido_extra(sessao, cliente, matriz, status_ped, produto_a, "PED-10005")
    divergente = _pedido_extra(sessao, cliente, filial, status_ped, produto_a, "PED-10006")

    # `separador` é o coordenador logado por padrão; `outro` entra numa etapa
    # para o filtro por operador ter dois nomes que distinguir.
    _abrir(client, "separacao", em_separacao.id)

    _executar_etapa(client, "separacao", aguardando.id, aguardando.itens[0].id)

    _executar_etapa(client, "separacao", em_conferencia.id, em_conferencia.itens[0].id)
    logado["id"] = cenario.outro_id
    _abrir(client, "conferencia", em_conferencia.id)
    logado["id"] = cenario.separador_id

    _executar_etapa(client, "separacao", concluido.id, concluido.itens[0].id)
    _executar_etapa(client, "conferencia", concluido.id, concluido.itens[0].id)

    # Falta: fecha sem bipar nada, com a senha do gerente autorizando.
    _executar_etapa(
        client,
        "separacao",
        divergente.id,
        divergente.itens[0].id,
        completo=False,
        credencial={"usuarioGerente": "gerente", "senha": SENHA_GERENTE},
    )

    cenario.matriz_id = matriz.id
    cenario.filial_id = filial.id
    cenario.p_nao_iniciado = nao_iniciado.id
    cenario.p_em_separacao = em_separacao.id
    cenario.p_aguardando = aguardando.id
    cenario.p_em_conferencia = em_conferencia.id
    cenario.p_concluido = concluido.id
    cenario.p_divergente = divergente.id
    return client, sessao, cenario, logado


def _filtrar(client, **params) -> dict:
    """Sempre com perPage=1: se o filtro recortasse a página carregada, não
    teria como devolver o pedido certo nem o total certo."""
    resposta = client.get("/expedicao/pedidos", params={"perPage": 1, **params})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _todos_os_ids(client, **params) -> set[str]:
    """Percorre TODAS as páginas do filtro. É o que prova que o recorte é do
    servidor: a soma das páginas fecha com o total que ele informou."""
    pagina = _filtrar(client, page=1, **params)
    total = pagina["total"]
    ids = {item["pedidoId"] for item in pagina["items"]}
    numero = 2
    while len(ids) < total:
        seguinte = _filtrar(client, page=numero, **params)
        assert seguinte["items"], "página vazia antes de completar o total informado"
        ids |= {item["pedidoId"] for item in seguinte["items"]}
        numero += 1
    assert len(ids) == total
    return ids


class TestFiltroPorEmpresa:
    def test_cada_empresa_traz_os_seus_pedidos(self, galpao):
        client, _, cenario, _ = galpao

        matriz = _todos_os_ids(client, empresaId=cenario.matriz_id)
        filial = _todos_os_ids(client, empresaId=cenario.filial_id)

        assert cenario.p_em_separacao in matriz
        assert cenario.p_aguardando in matriz
        assert cenario.p_concluido in matriz
        assert filial == {
            cenario.p_nao_iniciado,
            cenario.p_em_conferencia,
            cenario.p_divergente,
        }
        # Nenhum pedido em duas empresas, e as duas somam a fila inteira.
        assert not (matriz & filial)
        assert matriz | filial == _todos_os_ids(client)

    def test_empresa_sem_pedido_devolve_lista_vazia_e_total_zero(self, galpao):
        """Total zero, e não "a página 1 está vazia": é o total que a tela mostra
        no rodapé, e ele tem que descrever o filtro, não a página."""
        client, sessao, _, _ = galpao
        from app.domains.empresas.empresa_model import Empresa

        vazia = Empresa(
            razao_social="Sem Pedido LTDA", nome_fantasia="Filial Zero", cnpj="33.333.333/0001-33"
        )
        sessao.add(vazia)
        sessao.commit()

        pagina = _filtrar(client, empresaId=vazia.id)

        assert pagina["total"] == 0
        assert pagina["items"] == []


class TestFiltroPorOperador:
    def test_cada_operador_traz_as_etapas_que_ele_abriu(self, galpao):
        client, _, cenario, _ = galpao

        do_separador = _todos_os_ids(client, operadorId=cenario.separador_id)
        do_outro = _todos_os_ids(client, operadorId=cenario.outro_id)

        # `separador` abriu todas as separações do cenário.
        assert do_separador == {
            cenario.p_em_separacao,
            cenario.p_aguardando,
            cenario.p_em_conferencia,
            cenario.p_concluido,
            cenario.p_divergente,
        }
        # `outro` só abriu uma conferência — e esse pedido aparece para os dois,
        # cada um por uma etapa diferente.
        assert do_outro == {cenario.p_em_conferencia}

    def test_operador_sem_processo_aberto_devolve_vazio(self, galpao):
        """O gerente existe e tem permissão, mas nunca abriu etapa nenhuma.
        Antes ele nem aparecia na lista do filtro; agora aparece e responde
        honestamente que não há nada dele."""
        client, _, cenario, _ = galpao

        pagina = _filtrar(client, operadorId=cenario.gerente_id)

        assert pagina["total"] == 0
        assert pagina["items"] == []

    def test_pedido_nao_iniciado_nao_e_de_ninguem(self, galpao):
        client, _, cenario, _ = galpao

        assert cenario.p_nao_iniciado not in _todos_os_ids(client, operadorId=cenario.separador_id)


class TestFiltroPorSituacao:
    """Uma situação de cada, montada pelo processo rodando de verdade."""

    def test_cada_situacao_traz_exatamente_o_seu_pedido(self, galpao):
        client, _, cenario, _ = galpao

        assert _todos_os_ids(client, situacao="em_separacao") == {cenario.p_em_separacao}
        # O divergente também está aguardando conferência: a separação dele
        # fechou (com falta) e nenhuma conferência foi aberta. "Com divergência"
        # é um recorte transversal, não uma etapa do fluxo.
        assert _todos_os_ids(client, situacao="aguardando_conferencia") == {
            cenario.p_aguardando,
            cenario.p_divergente,
        }
        assert _todos_os_ids(client, situacao="em_conferencia") == {cenario.p_em_conferencia}
        assert _todos_os_ids(client, situacao="concluidos") == {cenario.p_concluido}
        assert _todos_os_ids(client, situacao="divergentes") == {cenario.p_divergente}

    def test_nao_iniciados_e_a_ausencia_de_separacao(self, galpao):
        """A única situação que se define por AUSÊNCIA — e a que denuncia filtro
        feito na página carregada, porque depende de saber o que NÃO está no
        conjunto."""
        client, _, cenario, _ = galpao

        nao_iniciados = _todos_os_ids(client, situacao="nao_iniciados")

        assert cenario.p_nao_iniciado in nao_iniciados
        # os dois pedidos do cenário base também nunca foram abertos
        assert cenario.pedido_id in nao_iniciados
        assert cenario.pedido_orcamento_id in nao_iniciados
        # e nenhum dos que abriram separação entra
        assert not (
            nao_iniciados & {cenario.p_em_separacao, cenario.p_aguardando, cenario.p_concluido}
        )

    def test_todos_e_o_mesmo_que_nao_filtrar(self, galpao):
        client, _, _, _ = galpao

        assert _todos_os_ids(client, situacao="todos") == _todos_os_ids(client)

    def test_as_situacoes_particionam_a_fila(self, galpao):
        """Cada pedido cai em uma situação — nenhum fica de fora, nenhum aparece
        em duas. `divergentes` é o único recorte transversal e sai da conta."""
        client, _, _, _ = galpao
        exclusivas = [
            "nao_iniciados",
            "em_separacao",
            "aguardando_conferencia",
            "em_conferencia",
            "concluidos",
        ]

        vistos: set[str] = set()
        for situacao in exclusivas:
            ids = _todos_os_ids(client, situacao=situacao)
            assert not (ids & vistos), f"{situacao} repete pedido de outra situacao"
            vistos |= ids

        assert vistos == _todos_os_ids(client)

    def test_situacao_desconhecida_e_recusada(self, galpao):
        client, _, _, _ = galpao

        recusada = client.get("/expedicao/pedidos", params={"situacao": "inventada"})

        assert recusada.status_code == 422
        assert "inválida" in recusada.json()["detail"]


class TestFiltrosCombinados:
    def test_empresa_e_situacao_se_somam(self, galpao):
        client, _, cenario, _ = galpao

        assert _todos_os_ids(client, empresaId=cenario.filial_id, situacao="em_conferencia") == {
            cenario.p_em_conferencia
        }
        # a mesma situação na outra empresa não existe
        assert _filtrar(client, empresaId=cenario.matriz_id, situacao="em_conferencia")["total"] == 0

    def test_operador_e_situacao_se_somam(self, galpao):
        client, _, cenario, _ = galpao

        assert _todos_os_ids(client, operadorId=cenario.separador_id, situacao="concluidos") == {
            cenario.p_concluido
        }
        assert _filtrar(client, operadorId=cenario.outro_id, situacao="concluidos")["total"] == 0

    def test_filtro_convive_com_a_visibilidade_do_operador(self, galpao):
        """Quem não distribui trabalho só vê o que foi atribuído a ele. O filtro
        recorta DENTRO disso — nunca revela pedido que a pessoa não veria."""
        client, _, cenario, logado = galpao

        client.post(
            "/expedicao/atribuicoes",
            json={
                "pedidoIds": [cenario.p_nao_iniciado],
                "tipo": "separacao",
                "usuarioId": cenario.sem_conferencia_id,
            },
        )
        logado["id"] = cenario.sem_conferencia_id

        assert _todos_os_ids(client, situacao="nao_iniciados") == {cenario.p_nao_iniciado}
        # a matriz tem pedidos, mas nenhum atribuído a essa pessoa
        assert _filtrar(client, empresaId=cenario.matriz_id)["total"] == 0


# ---------------------------------------------------------------------------
# Desempate pelo dígito verificador
#
# Caso real: a embalagem do fabricante traz o EAN com o DV errado e a nota traz
# o certo — a SEFAZ valida o DV do campo `cEAN` e rejeitaria a NF-e com o
# errado, então o faturamento emite corrigido enquanto a caixa continua com a
# impressão falha. Mesmos 12 primeiros dígitos, mesmo produto.
#
# Os números aqui são os do caso que motivou a regra: SONDA FOLEY 2 VIAS LÁTEX
# Nº 18 30ML.
# ---------------------------------------------------------------------------

EAN_NOTA_SONDA = "6936877313056"  # DV correto, o que a NF-e carrega
EAN_CAIXA_SONDA = "6936877313053"  # DV errado, o que está impresso na embalagem


@pytest.fixture()
def sonda(ambiente):
    """Troca o cadastro do produto A pelo EAN da sonda, e devolve a bipagem
    aberta no item dele."""
    client, sessao, cenario, _logado = ambiente
    produto_a = sessao.query(Produto).filter(Produto.codigo == "A-001").one()
    produto_a.codigo_barra_notas = EAN_NOTA_SONDA
    produto_a.dun_14 = None
    sessao.commit()

    processo = client.post(
        f"/expedicao/separacao/pedidos/{cenario.pedido_id}/iniciar"
    ).json()
    client.post(f"/expedicao/separacao/{processo['id']}/itens/{cenario.item_a_id}/iniciar")
    return client, sessao, cenario, processo["id"], produto_a


class TestDesempatePeloDigitoVerificador:
    def test_caixa_com_dv_errado_casa_com_o_cadastro_da_nota(self, sonda):
        client, _, cenario, processo_id, _ = sonda

        aceita = _bipar(client, "separacao", processo_id, cenario.item_a_id, EAN_CAIXA_SONDA)

        assert aceita.status_code == 200, aceita.text
        atual = client.get(f"/expedicao/separacao/{processo_id}").json()
        item = next(i for i in atual["itens"] if i["pedidoItemId"] == cenario.item_a_id)
        assert item["quantidadeProcessada"] == 1

    def test_o_dv_certo_continua_casando(self, sonda):
        """O desempate é o último passo — não pode atrapalhar quem bate exato."""
        client, _, cenario, processo_id, _ = sonda

        assert (
            _bipar(client, "separacao", processo_id, cenario.item_a_id, EAN_NOTA_SONDA).status_code
            == 200
        )

    def test_vale_para_codigo_de_logistica_e_para_dun_14(self, sonda):
        """A tolerância é das três origens, não só do código da nota."""
        client, sessao, cenario, processo_id, produto_a = sonda
        produto_a.codigo_barra_notas = None
        produto_a.dun_14 = "17891111111118"
        sessao.add(ProdutoCodigoBarras(produto_id=produto_a.id, codigo="7899999999994"))
        sessao.commit()

        # bate a logística pela base (último dígito trocado)
        assert (
            _bipar(client, "separacao", processo_id, cenario.item_a_id, "7899999999990").status_code
            == 200
        )
        # e o DUN-14 também
        assert (
            _bipar(client, "separacao", processo_id, cenario.item_a_id, "17891111111110").status_code
            == 200
        )

    def test_base_ambigua_e_recusada(self, sonda):
        """Dois produtos com a mesma base: ignorar o DV deixaria a leitura
        ambígua, e a bipagem recusa em vez de escolher. Errar o produto na
        conferência é pior que mandar o operador conferir o cadastro."""
        client, sessao, cenario, processo_id, produto_a = sonda
        marca_id = produto_a.marca_id
        sessao.add(
            Produto(
                codigo="C-003",
                descricao="Outro produto, mesma base de EAN",
                codigo_barra_notas="6936877313052",
                marca_id=marca_id,
            )
        )
        sessao.commit()

        recusada = _bipar(client, "separacao", processo_id, cenario.item_a_id, EAN_CAIXA_SONDA)

        assert recusada.status_code == 422
        assert "não cadastrado" in recusada.json()["detail"]

    def test_produto_inativo_nao_conta_para_a_ambiguidade(self, sonda):
        """Cadastro inativo não é opção de bipagem, então também não pode
        tornar a leitura ambígua — senão desativar um produto quebraria a
        bipagem de outro."""
        client, sessao, cenario, processo_id, produto_a = sonda
        sessao.add(
            Produto(
                codigo="C-004",
                descricao="Inativo com a mesma base",
                codigo_barra_notas="6936877313052",
                marca_id=produto_a.marca_id,
                ativo=False,
            )
        )
        sessao.commit()

        assert (
            _bipar(client, "separacao", processo_id, cenario.item_a_id, EAN_CAIXA_SONDA).status_code
            == 200
        )

    def test_base_curta_nao_vira_curinga(self, sonda):
        """Abaixo de 8 dígitos, "ignorar o último" deixa de ser tolerância e
        passa a casar com meio cadastro."""
        client, sessao, cenario, processo_id, produto_a = sonda
        produto_a.codigo_barra_notas = "1234567"
        sessao.commit()

        recusada = _bipar(client, "separacao", processo_id, cenario.item_a_id, "1234569")

        assert recusada.status_code == 422

    def test_codigo_alfanumerico_nao_entra_no_desempate(self, sonda):
        """Código interno não tem dígito verificador para estar errado."""
        client, sessao, cenario, processo_id, produto_a = sonda
        produto_a.codigo_barra_notas = "MED-0012-A"
        sessao.commit()

        recusada = _bipar(client, "separacao", processo_id, cenario.item_a_id, "MED-0012-B")

        assert recusada.status_code == 422

    def test_bases_de_comprimentos_diferentes_nao_se_misturam(self, sonda):
        """A base de um EAN-13 tem 12 dígitos e a de um DUN-14 tem 13 — comparar
        base com base já garante isso, e o teste trava a garantia."""
        client, sessao, cenario, processo_id, produto_a = sonda
        produto_a.codigo_barra_notas = None
        produto_a.dun_14 = "06936877313053"
        sessao.commit()

        recusada = _bipar(client, "separacao", processo_id, cenario.item_a_id, EAN_CAIXA_SONDA)

        assert recusada.status_code == 422

    def test_o_desempate_nao_afrouxa_a_checagem_de_produto(self, sonda):
        """Casar por base é sobre encontrar o cadastro, não sobre aceitar
        qualquer coisa: se o produto encontrado é de outro item, recusa igual."""
        client, sessao, cenario, processo_id, produto_a = sonda
        produto_b = sessao.query(Produto).filter(Produto.codigo == "B-002").one()
        produto_b.codigo_barra_notas = "6936877313056"
        produto_a.codigo_barra_notas = None
        sessao.commit()

        recusada = _bipar(client, "separacao", processo_id, cenario.item_a_id, EAN_CAIXA_SONDA)

        assert recusada.status_code == 422
        assert "outro produto" in recusada.json()["detail"]
