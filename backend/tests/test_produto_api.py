"""
Produtos batendo na API por HTTP (TestClient) sobre um SQLite em memória.

Existe separado de `test_produto_service.py` porque aquele exercita o service
direto: ele não passa pelo router, e por isso não pega um campo que o service
grava mas o `_para_resposta` do router esquece de devolver — que é justamente
o erro que este arquivo cobre para `quantidade_multipla_venda`.

Mesma dispensa de autenticação usada em test_expedicao_e2e.py: `obter_usuario_atual`
é substituído por um override; `exigir_permissao` continua rodando de verdade
sobre as chaves gravadas em `usuario_permissoes`.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth.dependencies import ContextoRequisicao, obter_usuario_atual
from app.core.database import todos_os_models  # noqa: F401
from app.core.database.conexao import Base, obter_sessao
from app.domains.marcas.marca_model import Marca
from app.domains.produtos.produto_model import Produto, ProdutoCodigoBarras
from app.domains.usuarios.cargo_model import Cargo
from app.domains.usuarios.usuario_model import Usuario, UsuarioPermissao
from app.main import app

PERMISSOES = ["produtos.acessar", "produtos.gravar.incluir", "produtos.gravar.editar"]


@pytest.fixture()
def ambiente() -> Generator[tuple[TestClient, Session, str], None, None]:
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
    sessao = sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    marca = Marca(nome="Descarpack")
    cargo = Cargo(nome="Cadastro")
    sessao.add_all([marca, cargo])
    sessao.commit()

    usuario = Usuario(
        usuario="cadastrador",
        nome="Cadastrador",
        email="cad@ellotec.local",
        senha_hash="nao-usado",
        cargo_id=cargo.id,
        permissoes=[UsuarioPermissao(chave=chave) for chave in PERMISSOES],
    )
    sessao.add(usuario)
    sessao.commit()

    def _sessao_de_teste() -> Generator[Session, None, None]:
        yield sessao

    def _usuario_de_teste() -> ContextoRequisicao:
        return ContextoRequisicao(usuario=usuario, dispositivo_id="dispositivo-de-teste")

    app.dependency_overrides[obter_sessao] = _sessao_de_teste
    app.dependency_overrides[obter_usuario_atual] = _usuario_de_teste

    try:
        yield TestClient(app), sessao, marca.id
    finally:
        app.dependency_overrides.clear()
        sessao.close()
        engine.dispose()


def _payload(marca_id: str, **overrides) -> dict:
    base = {
        "codigo": "MED-0012",
        "descricao": "Luva de Procedimento Látex P (cx c/100)",
        "unidade": "CX",
        "codigoBarraNotas": "7891234500012",
        "dun14": "17891234500012",
        "marcaId": marca_id,
    }
    base.update(overrides)
    return base


def test_post_grava_quantidade_multipla_venda_e_get_devolve(ambiente):
    client, sessao, marca_id = ambiente

    criado = client.post("/produtos", json=_payload(marca_id, quantidadeMultiplaVenda=100))
    assert criado.status_code == 201, criado.text
    assert criado.json()["quantidadeMultiplaVenda"] == 100

    # gravou mesmo no banco, não só ecoou o payload
    produto_id = criado.json()["id"]
    assert sessao.query(Produto).filter(Produto.id == produto_id).one().quantidade_multipla_venda == 100

    lido = client.get(f"/produtos/{produto_id}")
    assert lido.status_code == 200
    assert lido.json()["quantidadeMultiplaVenda"] == 100

    listado = client.get("/produtos")
    assert listado.status_code == 200
    assert listado.json()["items"][0]["quantidadeMultiplaVenda"] == 100


def test_put_altera_quantidade_multipla_venda(ambiente):
    client, sessao, marca_id = ambiente
    produto_id = client.post("/produtos", json=_payload(marca_id)).json()["id"]

    alterado = client.put(
        f"/produtos/{produto_id}", json=_payload(marca_id, quantidadeMultiplaVenda=12)
    )
    assert alterado.status_code == 200, alterado.text
    assert alterado.json()["quantidadeMultiplaVenda"] == 12
    sessao.expire_all()
    assert sessao.query(Produto).filter(Produto.id == produto_id).one().quantidade_multipla_venda == 12


def test_ausente_no_payload_vale_1(ambiente):
    """Produto vendido na unidade é a maioria — quem não informa não precisa saber
    que o campo existe."""
    client, _, marca_id = ambiente

    criado = client.post("/produtos", json=_payload(marca_id))

    assert criado.status_code == 201, criado.text
    assert criado.json()["quantidadeMultiplaVenda"] == 1


def test_post_grava_dun_14_e_get_devolve(ambiente):
    client, sessao, marca_id = ambiente

    criado = client.post("/produtos", json=_payload(marca_id))
    assert criado.status_code == 201, criado.text
    assert criado.json()["dun14"] == "17891234500012"

    produto_id = criado.json()["id"]
    assert sessao.query(Produto).filter(Produto.id == produto_id).one().dun_14 == "17891234500012"
    assert client.get(f"/produtos/{produto_id}").json()["dun14"] == "17891234500012"


def test_dun_14_e_opcional(ambiente):
    client, _, marca_id = ambiente

    criado = client.post("/produtos", json=_payload(marca_id, dun14=None))

    assert criado.status_code == 201, criado.text
    assert criado.json()["dun14"] is None


def test_zero_e_recusado(ambiente):
    client, _, marca_id = ambiente

    recusado = client.post("/produtos", json=_payload(marca_id, quantidadeMultiplaVenda=0))

    assert recusado.status_code == 422


def test_post_grava_codigos_de_logistica_e_get_devolve(ambiente):
    """O produto chega em caixa de fabricante e em caixa de distribuidor, com
    código diferente em cada uma. Os dois são o mesmo produto e os dois bipam."""
    client, sessao, marca_id = ambiente

    criado = client.post(
        "/produtos",
        json=_payload(marca_id, codigosBarrasLogistica=["17891234500012", "27891234500019"]),
    )
    assert criado.status_code == 201, criado.text
    assert criado.json()["codigosBarrasLogistica"] == ["17891234500012", "27891234500019"]

    produto_id = criado.json()["id"]
    gravados = (
        sessao.query(ProdutoCodigoBarras)
        .filter(ProdutoCodigoBarras.produto_id == produto_id)
        .all()
    )
    assert sorted(linha.codigo for linha in gravados) == ["17891234500012", "27891234500019"]
    assert sorted(client.get(f"/produtos/{produto_id}").json()["codigosBarrasLogistica"]) == [
        "17891234500012",
        "27891234500019",
    ]


def test_put_sincroniza_a_lista_de_logistica(ambiente):
    """A lista que chega é o cadastro final: o que sumiu dela é apagado, o que
    continua nela mantém a linha (e a data de criação) que já tinha."""
    client, sessao, marca_id = ambiente
    produto_id = client.post(
        "/produtos", json=_payload(marca_id, codigosBarrasLogistica=["111", "222"])
    ).json()["id"]

    id_do_que_fica = (
        sessao.query(ProdutoCodigoBarras)
        .filter(ProdutoCodigoBarras.produto_id == produto_id, ProdutoCodigoBarras.codigo == "111")
        .one()
        .id
    )

    alterado = client.put(
        f"/produtos/{produto_id}", json=_payload(marca_id, codigosBarrasLogistica=["111", "333"])
    )
    assert alterado.status_code == 200, alterado.text
    assert sorted(alterado.json()["codigosBarrasLogistica"]) == ["111", "333"]

    sessao.expire_all()
    vivos = (
        sessao.query(ProdutoCodigoBarras)
        .filter(
            ProdutoCodigoBarras.produto_id == produto_id,
            ProdutoCodigoBarras.sync_deleted_at.is_(None),
        )
        .all()
    )
    assert sorted(linha.codigo for linha in vivos) == ["111", "333"]
    assert id_do_que_fica in {linha.id for linha in vivos}

    # o que saiu da lista é soft delete, não some do banco
    apagado = (
        sessao.query(ProdutoCodigoBarras)
        .filter(ProdutoCodigoBarras.produto_id == produto_id, ProdutoCodigoBarras.codigo == "222")
        .one()
    )
    assert apagado.sync_deleted_at is not None


def test_codigo_de_logistica_repetido_no_payload_vira_um_so(ambiente):
    """Bipar duas vezes o mesmo código na tela de cadastro é acidente comum —
    não é motivo para recusar a gravação."""
    client, _, marca_id = ambiente

    criado = client.post(
        "/produtos", json=_payload(marca_id, codigosBarrasLogistica=["111", " 111 ", ""])
    )

    assert criado.status_code == 201, criado.text
    assert criado.json()["codigosBarrasLogistica"] == ["111"]


def test_lista_de_logistica_ausente_vale_vazia(ambiente):
    client, _, marca_id = ambiente

    criado = client.post("/produtos", json=_payload(marca_id))

    assert criado.status_code == 201, criado.text
    assert criado.json()["codigosBarrasLogistica"] == []


def test_post_grava_registro_anvisa_e_get_devolve(ambiente):
    client, sessao, marca_id = ambiente

    criado = client.post("/produtos", json=_payload(marca_id, registroAnvisa="80149220015"))
    assert criado.status_code == 201, criado.text
    assert criado.json()["registroAnvisa"] == "80149220015"

    produto_id = criado.json()["id"]
    assert (
        sessao.query(Produto).filter(Produto.id == produto_id).one().registro_anvisa
        == "80149220015"
    )
    assert client.get(f"/produtos/{produto_id}").json()["registroAnvisa"] == "80149220015"


def test_registro_anvisa_e_opcional(ambiente):
    """Nem todo item do catálogo é produto de saúde registrado."""
    client, _, marca_id = ambiente

    criado = client.post("/produtos", json=_payload(marca_id))

    assert criado.status_code == 201, criado.text
    assert criado.json()["registroAnvisa"] is None


def test_registro_anvisa_preserva_zero_a_esquerda(ambiente):
    """É por isso que o campo é texto e não número: o zero da frente faz parte
    do registro, e um inteiro o comeria."""
    client, _, marca_id = ambiente

    criado = client.post("/produtos", json=_payload(marca_id, registroAnvisa="00801492200"))

    assert criado.status_code == 201, criado.text
    assert criado.json()["registroAnvisa"] == "00801492200"


def test_registro_anvisa_aceita_texto_nao_numerico(ambiente):
    """Produto isento ou em renovação chega do ERP com texto livre no campo."""
    client, _, marca_id = ambiente

    criado = client.post("/produtos", json=_payload(marca_id, registroAnvisa="ISENTO"))

    assert criado.status_code == 201, criado.text
    assert criado.json()["registroAnvisa"] == "ISENTO"


def test_put_altera_registro_anvisa(ambiente):
    client, sessao, marca_id = ambiente
    produto_id = client.post(
        "/produtos", json=_payload(marca_id, registroAnvisa="80149220015")
    ).json()["id"]

    alterado = client.put(
        f"/produtos/{produto_id}", json=_payload(marca_id, registroAnvisa="10033430289")
    )

    assert alterado.status_code == 200, alterado.text
    assert alterado.json()["registroAnvisa"] == "10033430289"
    sessao.expire_all()
    assert (
        sessao.query(Produto).filter(Produto.id == produto_id).one().registro_anvisa
        == "10033430289"
    )
