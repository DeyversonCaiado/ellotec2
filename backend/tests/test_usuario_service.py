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
from app.domains.usuarios.cargo_model import Cargo
from app.domains.usuarios.usuario_contrato import UsuarioAtualizarSchema, UsuarioCriarSchema


@pytest.fixture()
def cargo(sessao_db) -> Cargo:
    """O cargo virou FK (migração `22c3528ed7ac`), e `cargoId` é obrigatório
    nos schemas. Os helpers abaixo ainda passavam o antigo `cargo=` em texto, e
    por isso este arquivo inteiro estava falhando com "cargoId Field required" —
    ou seja, o CRUD de usuários ficou sem cobertura nenhuma."""
    registro = Cargo(nome="Analista Comercial")
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


def _dados_criar(cargo, **overrides) -> UsuarioCriarSchema:
    base = dict(
        usuario="mariana.silva",
        nome="Mariana Silva",
        email="mariana.silva@ellotec.com",
        cargo_id=cargo.id,
        ativo=True,
        senha="123456",
        permissoes=["clientes.acessar", "clientes.gravar.incluir"],
    )
    base.update(overrides)
    return UsuarioCriarSchema(**base)


def _dados_atualizar(cargo, **overrides) -> UsuarioAtualizarSchema:
    base = dict(
        usuario="mariana.silva",
        nome="Mariana Silva",
        email="mariana.silva@ellotec.com",
        cargo_id=cargo.id,
        ativo=True,
        permissoes=["clientes.acessar", "clientes.gravar.incluir"],
    )
    base.update(overrides)
    return UsuarioAtualizarSchema(**base)


class TestCriar:
    def test_cria_usuario_com_permissoes(self, sessao_db, cargo):
        usuario = usuario_service.criar(sessao_db, _dados_criar(cargo))

        assert usuario.id
        assert usuario.usuario == "mariana.silva"
        assert usuario.senha_hash != "123456"  # senha precisa estar hasheada, nunca em texto puro
        assert {p.chave for p in usuario.permissoes} == {"clientes.acessar", "clientes.gravar.incluir"}

    def test_cria_usuario_sem_permissoes(self, sessao_db, cargo):
        usuario = usuario_service.criar(sessao_db, _dados_criar(cargo, usuario="sem.permissao", email="sem.permissao@ellotec.com", permissoes=[]))
        assert usuario.permissoes == []

    def test_rejeita_email_duplicado(self, sessao_db, cargo):
        usuario_service.criar(sessao_db, _dados_criar(cargo))
        with pytest.raises(HTTPException) as excinfo:
            usuario_service.criar(sessao_db, _dados_criar(cargo, usuario="outro.usuario"))
        assert excinfo.value.status_code == 409

    def test_rejeita_usuario_duplicado(self, sessao_db, cargo):
        usuario_service.criar(sessao_db, _dados_criar(cargo))
        with pytest.raises(HTTPException) as excinfo:
            usuario_service.criar(sessao_db, _dados_criar(cargo, email="outro@ellotec.com"))
        assert excinfo.value.status_code == 409


class TestListar:
    def test_listar_paginado_retorna_apenas_ativos_nao_apagados(self, sessao_db, cargo):
        criado = usuario_service.criar(sessao_db, _dados_criar(cargo))
        usuario_service.apagar(sessao_db, criado.id, usuario_solicitante_id="outro-id")

        itens, total = usuario_service.listar_paginado(sessao_db, page=1, per_page=20, sort="nome", sort_type="asc")

        assert total == 0
        assert itens == []

    def test_listar_paginado_filtra_por_busca(self, sessao_db, cargo):
        usuario_service.criar(sessao_db, _dados_criar(cargo))
        usuario_service.criar(
            sessao_db, _dados_criar(cargo, usuario="carlos.eduardo", nome="Carlos Eduardo", email="carlos.eduardo@ellotec.com")
        )

        itens, total = usuario_service.listar_paginado(
            sessao_db, page=1, per_page=20, sort="nome", sort_type="asc", busca="mariana"
        )

        assert total == 1
        assert itens[0].usuario == "mariana.silva"

    def test_listar_paginado_com_sort_invalido_gera_422(self, sessao_db, cargo):
        with pytest.raises(HTTPException) as excinfo:
            usuario_service.listar_paginado(sessao_db, page=1, per_page=20, sort="campo_inexistente", sort_type="asc")
        assert excinfo.value.status_code == 422


class TestObter:
    def test_obter_por_id_existente(self, sessao_db, cargo):
        criado = usuario_service.criar(sessao_db, _dados_criar(cargo))
        encontrado = usuario_service.obter_por_id(sessao_db, criado.id)
        assert encontrado.id == criado.id

    def test_obter_por_id_inexistente_gera_404(self, sessao_db, cargo):
        with pytest.raises(HTTPException) as excinfo:
            usuario_service.obter_por_id(sessao_db, "id-que-nao-existe")
        assert excinfo.value.status_code == 404


class TestAtualizar:
    def test_atualizar_dados_basicos(self, sessao_db, cargo):
        criado = usuario_service.criar(sessao_db, _dados_criar(cargo))

        atualizado = usuario_service.atualizar(
            sessao_db, criado.id, _dados_atualizar(cargo, nome="Mariana Silva Souza")
        )

        assert atualizado.nome == "Mariana Silva Souza"
        assert atualizado.cargo_id == cargo.id
        assert atualizado.sync_version == 2

    def test_atualizar_adiciona_novas_permissoes(self, sessao_db, cargo):
        criado = usuario_service.criar(sessao_db, _dados_criar(cargo, permissoes=["clientes.acessar"]))

        atualizado = usuario_service.atualizar(
            sessao_db,
            criado.id,
            _dados_atualizar(cargo, permissoes=["clientes.acessar", "clientes.gravar.incluir", "pedidos.acessar"]),
        )

        assert {p.chave for p in atualizado.permissoes} == {
            "clientes.acessar",
            "clientes.gravar.incluir",
            "pedidos.acessar",
        }

    def test_atualizar_remove_permissoes_que_sairam(self, sessao_db, cargo):
        criado = usuario_service.criar(
            sessao_db, _dados_criar(cargo, permissoes=["clientes.acessar", "clientes.gravar.incluir", "pedidos.acessar"])
        )

        atualizado = usuario_service.atualizar(sessao_db, criado.id, _dados_atualizar(cargo, permissoes=["clientes.acessar"]))

        assert {p.chave for p in atualizado.permissoes} == {"clientes.acessar"}

    def test_atualizar_permissoes_persiste_apos_reconsulta(self, sessao_db, cargo):
        """Reproduz o cenário do bug relatado: grava permissões e confere
        que, numa nova consulta ao banco (não no objeto em memória), elas
        realmente estão lá — não só na sessão que fez o update."""
        criado = usuario_service.criar(sessao_db, _dados_criar(cargo, permissoes=[]))

        usuario_service.atualizar(sessao_db, criado.id, _dados_atualizar(cargo, permissoes=["usuarios.acessar", "usuarios.apagar"]))

        relido = usuario_service.obter_por_id(sessao_db, criado.id)
        assert {p.chave for p in relido.permissoes} == {"usuarios.acessar", "usuarios.apagar"}

    def test_atualizar_esvaziando_permissoes(self, sessao_db, cargo):
        criado = usuario_service.criar(sessao_db, _dados_criar(cargo, permissoes=["clientes.acessar"]))

        atualizado = usuario_service.atualizar(sessao_db, criado.id, _dados_atualizar(cargo, permissoes=[]))

        assert atualizado.permissoes == []

    def test_atualizar_por_sistema_origem_id(self, sessao_db, cargo):
        criado = usuario_service.criar(sessao_db, _dados_criar(cargo, sistema_origem_id="FUNC-001"))

        atualizado = usuario_service.atualizar(
            sessao_db,
            "irrelevante",
            _dados_atualizar(cargo, nome="Nome Atualizado", sistema_origem_id="FUNC-001"),
            sistema_origem_id="FUNC-001",
        )

        assert atualizado.id == criado.id
        assert atualizado.nome == "Nome Atualizado"

    def test_nao_apaga_sistema_origem_id_quando_corpo_nao_o_repete(self, sessao_db, cargo):
        criado = usuario_service.criar(sessao_db, _dados_criar(cargo, sistema_origem_id="FUNC-001"))

        dados = _dados_atualizar(cargo, nome="Nome Atualizado")
        assert dados.sistema_origem_id is None

        atualizado = usuario_service.atualizar(
            sessao_db, "irrelevante", dados, sistema_origem_id="FUNC-001"
        )
        assert atualizado.sistema_origem_id == "FUNC-001"

    def test_sistema_origem_id_duplicado_gera_409(self, sessao_db, cargo):
        usuario_service.criar(sessao_db, _dados_criar(cargo, sistema_origem_id="FUNC-001"))

        dados = _dados_criar(cargo, usuario="outro.usuario", email="outro@ellotec.com", sistema_origem_id="FUNC-001")
        with pytest.raises(HTTPException) as exc:
            usuario_service.criar(sessao_db, dados)
        assert exc.value.status_code == 409

    def test_atualizar_usuario_inexistente_gera_404(self, sessao_db, cargo):
        with pytest.raises(HTTPException) as excinfo:
            usuario_service.atualizar(sessao_db, "id-que-nao-existe", _dados_atualizar(cargo))
        assert excinfo.value.status_code == 404

    def test_atualizar_rejeita_email_ja_usado_por_outro_usuario(self, sessao_db, cargo):
        usuario_service.criar(sessao_db, _dados_criar(cargo))
        outro = usuario_service.criar(
            sessao_db, _dados_criar(cargo, usuario="carlos.eduardo", email="carlos.eduardo@ellotec.com")
        )

        with pytest.raises(HTTPException) as excinfo:
            usuario_service.atualizar(sessao_db, outro.id, _dados_atualizar(cargo, email="mariana.silva@ellotec.com"))
        assert excinfo.value.status_code == 409


class TestApagar:
    def test_apagar_marca_soft_delete(self, sessao_db, cargo):
        criado = usuario_service.criar(sessao_db, _dados_criar(cargo))

        usuario_service.apagar(sessao_db, criado.id, usuario_solicitante_id="outro-id")

        with pytest.raises(HTTPException) as excinfo:
            usuario_service.obter_por_id(sessao_db, criado.id)
        assert excinfo.value.status_code == 404

    def test_apagar_o_proprio_usuario_e_bloqueado(self, sessao_db, cargo):
        criado = usuario_service.criar(sessao_db, _dados_criar(cargo))

        with pytest.raises(HTTPException) as excinfo:
            usuario_service.apagar(sessao_db, criado.id, usuario_solicitante_id=criado.id)
        assert excinfo.value.status_code == 400

    def test_apagar_usuario_inexistente_gera_404(self, sessao_db, cargo):
        with pytest.raises(HTTPException) as excinfo:
            usuario_service.apagar(sessao_db, "id-que-nao-existe", usuario_solicitante_id="outro-id")
        assert excinfo.value.status_code == 404


class TestVinculoComOErp:
    """`sistema_origem_id` e o vinculo com o ERP. Perde-lo tem consequencia
    fora deste dominio: todo pedido que aponta para o funcionario passa a
    responder 404 "Vendedor nao encontrado", o sincronizador levanta
    RuntimeError, o processo morre e o systemd reinicia — em loop, sem avancar
    o checkpoint. Foi o que parou a integracao de pedidos por tres dias.
    """

    def test_editar_pela_tela_nao_apaga_o_vinculo(self, sessao_db, cargo):
        """O caso que quebrou a producao.

        A tela de usuarios nao exibe nem envia `sistemaOrigemId`, e edita pelo
        ID (sem o query param que a integracao usa). Antes da correcao, os dois
        caminhos davam None e o campo era zerado em silencio.
        """
        criado = usuario_service.criar(
            sessao_db, _dados_criar(cargo, sistema_origem_id="00168")
        )

        atualizado = usuario_service.atualizar(
            sessao_db, criado.id, _dados_atualizar(cargo, nome="Marcos Rodrigo Fonseca")
        )

        assert atualizado.sistema_origem_id == "00168"

    def test_a_integracao_continua_podendo_trocar_o_vinculo(self, sessao_db, cargo):
        """Preservar nao pode virar congelar: quando o corpo TRAZ o campo, ele
        manda."""
        criado = usuario_service.criar(
            sessao_db, _dados_criar(cargo, sistema_origem_id="00168")
        )

        atualizado = usuario_service.atualizar(
            sessao_db, criado.id, _dados_atualizar(cargo, sistema_origem_id="00999")
        )

        assert atualizado.sistema_origem_id == "00999"

    def test_atualizar_pelo_sistema_origem_id_preserva_a_chave_da_busca(
        self, sessao_db, cargo
    ):
        """O integrador nao deveria precisar reenviar a propria chave que usou
        para identificar o registro."""
        usuario_service.criar(sessao_db, _dados_criar(cargo, sistema_origem_id="00168"))

        atualizado = usuario_service.atualizar(
            sessao_db,
            "id-ignorado",
            _dados_atualizar(cargo, nome="Marcos Fonseca"),
            sistema_origem_id="00168",
        )

        assert atualizado.sistema_origem_id == "00168"

    def test_usuario_sem_vinculo_continua_sem_vinculo(self, sessao_db, cargo):
        """Usuario criado a mao (admin, por exemplo) nao ganha vinculo do nada."""
        criado = usuario_service.criar(sessao_db, _dados_criar(cargo))

        atualizado = usuario_service.atualizar(
            sessao_db, criado.id, _dados_atualizar(cargo, nome="Outro Nome")
        )

        assert atualizado.sistema_origem_id is None
