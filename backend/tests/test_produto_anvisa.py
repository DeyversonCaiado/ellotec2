"""
Verificar ANVISA: o código bipado conferido contra a tabela da CMED.

Cenário que isto resolve: o operador bipa a caixa, o código não está no
cadastro, mas o produto é medicamento registrado. A CMED publica até três EANs
por apresentação, e um deles costuma ser o que está impresso na caixa.

`cotacao_tabela_cmed` é tabela de OUTRO sistema — não tem model SQLAlchemy e não
está no metadata do Alembic. Aqui ela é criada à mão no SQLite, com as colunas
que `app/shared/tabela_cmed.py` consulta, e não por `Base.metadata.create_all`.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
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

# Registro e EANs de uma apresentação real da CMED (ANDROCUR), o exemplo com os
# três EANs preenchidos.
REGISTRO = "1705600660037"
EAN_1 = "7891106907460"
EAN_2 = "7891106907484"
EAN_3 = "7891106913904"

_CRIAR_CMED = """
    create table cotacao_tabela_cmed (
        id integer primary key,
        registro varchar(30),
        ean_1 varchar(20),
        ean_2 varchar(20),
        ean_3 varchar(20),
        produto varchar(255),
        apresentacao varchar(500),
        laboratorio varchar(255)
    )
"""


@pytest.fixture()
def ambiente() -> Generator[tuple[TestClient, Session, Produto], None, None]:
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
    sessao = sessionmaker(bind=engine)()
    sessao.execute(text(_CRIAR_CMED))
    sessao.execute(
        text(
            "insert into cotacao_tabela_cmed (id, registro, ean_1, ean_2, ean_3, produto,"
            " apresentacao, laboratorio) values (1, :r, :e1, :e2, :e3, 'ANDROCUR',"
            " '50 MG COM CT BL AL PLAS INC X 20', 'BAYER')"
        ),
        {"r": REGISTRO, "e1": EAN_1, "e2": EAN_2, "e3": EAN_3},
    )

    cargo = Cargo(nome="Funcionario")
    marca = Marca(nome="Bayer")
    sessao.add_all([cargo, marca])
    sessao.commit()

    produto = Produto(
        codigo="MED-9001",
        descricao="ANDROCUR 50MG C/20",
        registro_anvisa=REGISTRO,
        marca_id=marca.id,
    )
    usuario = Usuario(
        usuario="operador",
        nome="Operador Coletor",
        email="op@ellotec.local",
        senha_hash="x",
        cargo_id=cargo.id,
        permissoes=[
            UsuarioPermissao(chave="produtos.codigo_barras.vincular_anvisa"),
            UsuarioPermissao(chave="produtos.acessar"),
        ],
    )
    sessao.add_all([produto, usuario])
    sessao.commit()

    def _sessao_de_teste() -> Generator[Session, None, None]:
        yield sessao

    def _usuario_de_teste() -> ContextoRequisicao:
        return ContextoRequisicao(usuario=usuario, dispositivo_id="dispositivo-de-teste")

    app.dependency_overrides[obter_sessao] = _sessao_de_teste
    app.dependency_overrides[obter_usuario_atual] = _usuario_de_teste

    try:
        yield TestClient(app), sessao, produto
    finally:
        app.dependency_overrides.clear()
        sessao.close()
        engine.dispose()


def _verificar(client: TestClient, produto_id: str, codigo: str):
    return client.post(
        f"/produtos/{produto_id}/codigos-barras/anvisa", json={"codigoBarras": codigo}
    )


def _codigos_vivos(sessao: Session, produto_id: str) -> set[str]:
    return {
        linha.codigo
        for linha in sessao.query(ProdutoCodigoBarras)
        .filter(
            ProdutoCodigoBarras.produto_id == produto_id,
            ProdutoCodigoBarras.sync_deleted_at.is_(None),
        )
        .all()
    }


class TestMatch:
    def test_codigo_da_caixa_confere_e_os_tres_eans_sao_vinculados(self, ambiente):
        """O caso que motivou a feature: o operador bipou o EAN 2, que não estava
        no cadastro, mas a CMED confirma que ele é deste registro."""
        client, sessao, produto = ambiente

        resposta = _verificar(client, produto.id, EAN_2)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["situacao"] == "vinculado"
        assert set(corpo["codigosVinculados"]) == {EAN_1, EAN_2, EAN_3}
        assert _codigos_vivos(sessao, produto.id) == {EAN_1, EAN_2, EAN_3}

    def test_depois_de_vincular_a_bipagem_encontra_o_produto(self, ambiente):
        """O objetivo final: a leitura seguinte tem que passar."""
        client, sessao, produto = ambiente
        from app.domains.produtos import produto_publico

        assert produto_publico.obter_por_codigo_barras(sessao, EAN_2) is None
        _verificar(client, produto.id, EAN_2)
        achado = produto_publico.obter_por_codigo_barras(sessao, EAN_2)
        assert achado is not None and achado.id == produto.id

    def test_repetir_a_operacao_nao_duplica_codigo(self, ambiente):
        client, sessao, produto = ambiente

        _verificar(client, produto.id, EAN_2)
        segunda = _verificar(client, produto.id, EAN_2)

        assert segunda.status_code == 200
        assert segunda.json()["codigosVinculados"] == []
        assert len(_codigos_vivos(sessao, produto.id)) == 3

    def test_ean_em_branco_na_cmed_nao_vira_codigo(self, ambiente):
        """A CMED preenche `ean_2`/`ean_3` com string vazia quando a apresentação
        só tem um código — string vazia casaria com qualquer coisa depois."""
        client, sessao, produto = ambiente
        sessao.execute(text("update cotacao_tabela_cmed set ean_2 = '', ean_3 = null"))
        sessao.commit()

        resposta = _verificar(client, produto.id, EAN_1)

        assert resposta.json()["codigosVinculados"] == [EAN_1]
        assert _codigos_vivos(sessao, produto.id) == {EAN_1}


class TestConflito:
    def test_codigo_de_outro_produto_bloqueia_tudo(self, ambiente):
        """"Não faça nada" é literal: nem os códigos sem conflito são gravados.
        Vincular metade deixaria o cadastro num estado que ninguém pediu."""
        client, sessao, produto = ambiente
        outro = Produto(
            codigo="MED-9002",
            descricao="Outro produto que já usa o EAN 3",
            codigo_barra_notas=EAN_3,
            marca_id=produto.marca_id,
        )
        sessao.add(outro)
        sessao.commit()

        resposta = _verificar(client, produto.id, EAN_2)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["situacao"] == "conflito"
        assert corpo["codigosVinculados"] == []
        # nada gravado, nem os que não conflitavam
        assert _codigos_vivos(sessao, produto.id) == set()

    def test_o_conflito_diz_de_qual_produto_e(self, ambiente):
        """"Já existe" sem dizer onde não ajuda ninguém a resolver."""
        client, sessao, produto = ambiente
        sessao.add(
            Produto(
                codigo="MED-9002",
                descricao="Dono do EAN 1",
                codigo_barra_notas=EAN_1,
                marca_id=produto.marca_id,
            )
        )
        sessao.commit()

        corpo = _verificar(client, produto.id, EAN_2).json()

        assert len(corpo["conflitos"]) == 1
        conflito = corpo["conflitos"][0]
        assert conflito["codigo"] == EAN_1
        assert conflito["produtoCodigo"] == "MED-9002"
        assert conflito["produtoDescricao"] == "Dono do EAN 1"
        assert "MED-9002" in corpo["mensagem"]

    def test_conflito_vale_para_as_tres_origens(self, ambiente):
        """O código pode estar no campo da nota, no DUN-14 ou na lista de
        logística de outro produto — em qualquer uma delas é conflito."""
        client, sessao, produto = ambiente
        dono = Produto(codigo="MED-9003", descricao="Dono", marca_id=produto.marca_id)
        sessao.add(dono)
        sessao.commit()

        for campo, codigo in (("dun_14", EAN_1), ("logistica", EAN_2)):
            sessao.query(ProdutoCodigoBarras).delete()
            dono.dun_14 = None
            if campo == "dun_14":
                dono.dun_14 = codigo
            else:
                sessao.add(ProdutoCodigoBarras(produto_id=dono.id, codigo=codigo))
            sessao.commit()

            corpo = _verificar(client, produto.id, EAN_3).json()
            assert corpo["situacao"] == "conflito", campo
            assert _codigos_vivos(sessao, produto.id) == set(), campo

    def test_codigo_ja_do_proprio_produto_nao_e_conflito(self, ambiente):
        """Conflito é com OUTRO produto. O próprio cadastro já ter um dos códigos
        é o caso normal de quem roda a verificação duas vezes."""
        client, sessao, produto = ambiente
        produto.codigo_barra_notas = EAN_1
        sessao.commit()

        corpo = _verificar(client, produto.id, EAN_2).json()

        assert corpo["situacao"] == "vinculado"
        assert set(corpo["codigosVinculados"]) == {EAN_1, EAN_2, EAN_3}


class TestRecusas:
    def test_produto_sem_registro_anvisa(self, ambiente):
        """A maior parte do catálogo é correlato, não medicamento registrado —
        não é erro, é uma resposta."""
        client, sessao, produto = ambiente
        produto.registro_anvisa = None
        sessao.commit()

        corpo = _verificar(client, produto.id, EAN_2).json()

        assert corpo["situacao"] == "sem_registro"
        assert _codigos_vivos(sessao, produto.id) == set()

    def test_registro_que_nao_esta_na_cmed(self, ambiente):
        client, sessao, produto = ambiente
        produto.registro_anvisa = "9999999999999"
        sessao.commit()

        corpo = _verificar(client, produto.id, EAN_2).json()

        assert corpo["situacao"] == "registro_nao_encontrado"
        assert _codigos_vivos(sessao, produto.id) == set()

    def test_codigo_lido_que_nao_e_do_registro(self, ambiente):
        """A trava principal. Sem ela a função viraria "importe os códigos da
        CMED", e vincularia o produto ao registro errado sem ninguém perceber."""
        client, sessao, produto = ambiente

        corpo = _verificar(client, produto.id, "7899999999999").json()

        assert corpo["situacao"] == "codigo_nao_confere"
        assert _codigos_vivos(sessao, produto.id) == set()
        # a mensagem mostra o que a CMED publica, para o operador conferir a caixa
        assert EAN_1 in corpo["mensagem"]

    def test_produto_inexistente_da_404(self, ambiente):
        client, _, _ = ambiente

        assert _verificar(client, "nao-existe", EAN_1).status_code == 404


class TestRegistroEmFormatosDiferentes:
    """O registro é escrito de várias formas; a CMED guarda só os dígitos."""

    @pytest.mark.parametrize(
        "cadastrado",
        ["1705600660037", "1.7056.0066.003-7", "1 7056 0066 0037"],
    )
    def test_pontuacao_no_cadastro_nao_impede_o_match(self, ambiente, cadastrado):
        client, sessao, produto = ambiente
        produto.registro_anvisa = cadastrado
        sessao.commit()

        assert _verificar(client, produto.id, EAN_2).json()["situacao"] == "vinculado"


class TestPermissao:
    def test_exige_a_chave_propria_e_nao_a_de_editar_produto(self, ambiente):
        """O operador do coletor não tem `produtos.gravar.editar` — se a
        operação exigisse essa chave, a feature não serviria para quem ela foi
        feita."""
        client, sessao, produto = ambiente
        sessao.query(UsuarioPermissao).filter(
            UsuarioPermissao.chave == "produtos.codigo_barras.vincular_anvisa"
        ).delete()
        sessao.commit()

        assert _verificar(client, produto.id, EAN_2).status_code == 403
