"""
Testes do CRUD de usuários (app/domains/usuarios). Cobrem especificamente
o cenário do bug relatado: permissões marcadas na edição não eram
persistidas. A causa raiz era um bug de binding no formulário Angular
([(selection)]="signal" reatribuindo o signal em vez de chamar .set()),
não no backend — mas como a sincronização de permissões (_sincronizar_
permissoes) é a parte crítica e sem cobertura, os testes abaixo garantem
que o service adiciona e remove as chaves corretamente, prevenindo
regressões nesse ponto específico.
"""

import pytest
from fastapi import HTTPException

from app.domains.usuarios import usuario_service
from app.domains.usuarios.usuario_contrato import UsuarioAtualizarSchema, UsuarioCriarSchema


def _dados_criar(**overrides) -> UsuarioCriarSchema:
    base = dict(
        usuario="mariana.silva",
        nome="Mariana Silva",
        email="mariana.silva@ellotec.com",
        cargo="Analista Comercial",
        ativo=True,
        senha="123456",
        permissoes=["clientes.acessar", "clientes.gravar.incluir"],
    )
    base.update(overrides)
    return UsuarioCriarSchema(**base)


def _dados_atualizar(**overrides) -> UsuarioAtualizarSchema:
    base = dict(
        usuario="mariana.silva",
        nome="Mariana Silva",
        email="mariana.silva@ellotec.com",
        cargo="Analista Comercial",
        ativo=True,
        permissoes=["clientes.acessar", "clientes.gravar.incluir"],
    )
    base.update(overrides)
    return UsuarioAtualizarSchema(**base)


class TestCriar:
    def test_cria_usuario_com_permissoes(self, sessao_db):
        usuario = usuario_service.criar(sessao_db, _dados_criar())

        assert usuario.id
        assert usuario.usuario == "mariana.silva"
        assert usuario.senha_hash != "123456"  # senha precisa estar hasheada, nunca em texto puro
        assert {p.chave for p in usuario.permissoes} == {"clientes.acessar", "clientes.gravar.incluir"}

    def test_cria_usuario_sem_permissoes(self, sessao_db):
        usuario = usuario_service.criar(sessao_db, _dados_criar(usuario="sem.permissao", email="sem.permissao@ellotec.com", permissoes=[]))
        assert usuario.permissoes == []

    def test_rejeita_email_duplicado(self, sessao_db):
        usuario_service.criar(sessao_db, _dados_criar())
        with pytest.raises(HTTPException) as excinfo:
            usuario_service.criar(sessao_db, _dados_criar(usuario="outro.usuario"))
        assert excinfo.value.status_code == 409

    def test_rejeita_usuario_duplicado(self, sessao_db):
        usuario_service.criar(sessao_db, _dados_criar())
        with pytest.raises(HTTPException) as excinfo:
            usuario_service.criar(sessao_db, _dados_criar(email="outro@ellotec.com"))
        assert excinfo.value.status_code == 409


class TestListar:
    def test_listar_paginado_retorna_apenas_ativos_nao_apagados(self, sessao_db):
        criado = usuario_service.criar(sessao_db, _dados_criar())
        usuario_service.apagar(sessao_db, criado.id, usuario_solicitante_id="outro-id")

        itens, total = usuario_service.listar_paginado(sessao_db, page=1, per_page=20, sort="nome", sort_type="asc")

        assert total == 0
        assert itens == []

    def test_listar_paginado_filtra_por_busca(self, sessao_db):
        usuario_service.criar(sessao_db, _dados_criar())
        usuario_service.criar(
            sessao_db, _dados_criar(usuario="carlos.eduardo", nome="Carlos Eduardo", email="carlos.eduardo@ellotec.com")
        )

        itens, total = usuario_service.listar_paginado(
            sessao_db, page=1, per_page=20, sort="nome", sort_type="asc", busca="mariana"
        )

        assert total == 1
        assert itens[0].usuario == "mariana.silva"

    def test_listar_paginado_com_sort_invalido_gera_422(self, sessao_db):
        with pytest.raises(HTTPException) as excinfo:
            usuario_service.listar_paginado(sessao_db, page=1, per_page=20, sort="campo_inexistente", sort_type="asc")
        assert excinfo.value.status_code == 422


class TestObter:
    def test_obter_por_id_existente(self, sessao_db):
        criado = usuario_service.criar(sessao_db, _dados_criar())
        encontrado = usuario_service.obter_por_id(sessao_db, criado.id)
        assert encontrado.id == criado.id

    def test_obter_por_id_inexistente_gera_404(self, sessao_db):
        with pytest.raises(HTTPException) as excinfo:
            usuario_service.obter_por_id(sessao_db, "id-que-nao-existe")
        assert excinfo.value.status_code == 404


class TestAtualizar:
    def test_atualizar_dados_basicos(self, sessao_db):
        criado = usuario_service.criar(sessao_db, _dados_criar())

        atualizado = usuario_service.atualizar(
            sessao_db, criado.id, _dados_atualizar(nome="Mariana Silva Souza", cargo="Gerente Comercial")
        )

        assert atualizado.nome == "Mariana Silva Souza"
        assert atualizado.cargo == "Gerente Comercial"
        assert atualizado.sync_version == 2

    def test_atualizar_adiciona_novas_permissoes(self, sessao_db):
        criado = usuario_service.criar(sessao_db, _dados_criar(permissoes=["clientes.acessar"]))

        atualizado = usuario_service.atualizar(
            sessao_db,
            criado.id,
            _dados_atualizar(permissoes=["clientes.acessar", "clientes.gravar.incluir", "pedidos.acessar"]),
        )

        assert {p.chave for p in atualizado.permissoes} == {
            "clientes.acessar",
            "clientes.gravar.incluir",
            "pedidos.acessar",
        }

    def test_atualizar_remove_permissoes_que_sairam(self, sessao_db):
        criado = usuario_service.criar(
            sessao_db, _dados_criar(permissoes=["clientes.acessar", "clientes.gravar.incluir", "pedidos.acessar"])
        )

        atualizado = usuario_service.atualizar(sessao_db, criado.id, _dados_atualizar(permissoes=["clientes.acessar"]))

        assert {p.chave for p in atualizado.permissoes} == {"clientes.acessar"}

    def test_atualizar_permissoes_persiste_apos_reconsulta(self, sessao_db):
        """Reproduz o cenário do bug relatado: grava permissões e confere
        que, numa nova consulta ao banco (não no objeto em memória), elas
        realmente estão lá — não só na sessão que fez o update."""
        criado = usuario_service.criar(sessao_db, _dados_criar(permissoes=[]))

        usuario_service.atualizar(sessao_db, criado.id, _dados_atualizar(permissoes=["usuarios.acessar", "usuarios.apagar"]))

        relido = usuario_service.obter_por_id(sessao_db, criado.id)
        assert {p.chave for p in relido.permissoes} == {"usuarios.acessar", "usuarios.apagar"}

    def test_atualizar_esvaziando_permissoes(self, sessao_db):
        criado = usuario_service.criar(sessao_db, _dados_criar(permissoes=["clientes.acessar"]))

        atualizado = usuario_service.atualizar(sessao_db, criado.id, _dados_atualizar(permissoes=[]))

        assert atualizado.permissoes == []

    def test_atualizar_por_sistema_origem_id(self, sessao_db):
        criado = usuario_service.criar(sessao_db, _dados_criar(sistema_origem_id="FUNC-001"))

        atualizado = usuario_service.atualizar(
            sessao_db,
            "irrelevante",
            _dados_atualizar(nome="Nome Atualizado", sistema_origem_id="FUNC-001"),
            sistema_origem_id="FUNC-001",
        )

        assert atualizado.id == criado.id
        assert atualizado.nome == "Nome Atualizado"

    def test_nao_apaga_sistema_origem_id_quando_corpo_nao_o_repete(self, sessao_db):
        criado = usuario_service.criar(sessao_db, _dados_criar(sistema_origem_id="FUNC-001"))

        dados = _dados_atualizar(nome="Nome Atualizado")
        assert dados.sistema_origem_id is None

        atualizado = usuario_service.atualizar(
            sessao_db, "irrelevante", dados, sistema_origem_id="FUNC-001"
        )
        assert atualizado.sistema_origem_id == "FUNC-001"

    def test_sistema_origem_id_duplicado_gera_409(self, sessao_db):
        usuario_service.criar(sessao_db, _dados_criar(sistema_origem_id="FUNC-001"))

        dados = _dados_criar(usuario="outro.usuario", email="outro@ellotec.com", sistema_origem_id="FUNC-001")
        with pytest.raises(HTTPException) as exc:
            usuario_service.criar(sessao_db, dados)
        assert exc.value.status_code == 409

    def test_atualizar_usuario_inexistente_gera_404(self, sessao_db):
        with pytest.raises(HTTPException) as excinfo:
            usuario_service.atualizar(sessao_db, "id-que-nao-existe", _dados_atualizar())
        assert excinfo.value.status_code == 404

    def test_atualizar_rejeita_email_ja_usado_por_outro_usuario(self, sessao_db):
        usuario_service.criar(sessao_db, _dados_criar())
        outro = usuario_service.criar(
            sessao_db, _dados_criar(usuario="carlos.eduardo", email="carlos.eduardo@ellotec.com")
        )

        with pytest.raises(HTTPException) as excinfo:
            usuario_service.atualizar(sessao_db, outro.id, _dados_atualizar(email="mariana.silva@ellotec.com"))
        assert excinfo.value.status_code == 409


class TestApagar:
    def test_apagar_marca_soft_delete(self, sessao_db):
        criado = usuario_service.criar(sessao_db, _dados_criar())

        usuario_service.apagar(sessao_db, criado.id, usuario_solicitante_id="outro-id")

        with pytest.raises(HTTPException) as excinfo:
            usuario_service.obter_por_id(sessao_db, criado.id)
        assert excinfo.value.status_code == 404

    def test_apagar_o_proprio_usuario_e_bloqueado(self, sessao_db):
        criado = usuario_service.criar(sessao_db, _dados_criar())

        with pytest.raises(HTTPException) as excinfo:
            usuario_service.apagar(sessao_db, criado.id, usuario_solicitante_id=criado.id)
        assert excinfo.value.status_code == 400

    def test_apagar_usuario_inexistente_gera_404(self, sessao_db):
        with pytest.raises(HTTPException) as excinfo:
            usuario_service.apagar(sessao_db, "id-que-nao-existe", usuario_solicitante_id="outro-id")
        assert excinfo.value.status_code == 404
