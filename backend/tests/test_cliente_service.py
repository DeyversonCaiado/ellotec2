"""
Testes do domínio clientes (app/domains/clientes), com foco na resolução de
cidade na criação/atualização: o payload pode informar `cidade_id` direto
(fluxo atual) ou `cidade_ibge` (código de município do IBGE), caso em que o
service resolve o id perguntando ao domínio cidades pela fronteira pública
`cidade_publico.py` — nunca consultando a tabela de cidades direto.
"""

import pytest
from fastapi import HTTPException

from app.domains.cidades.cidade_model import Cidade
from app.domains.clientes import cliente_service
from app.domains.clientes.cliente_contrato import ClienteAtualizarSchema, ClienteCriarSchema


@pytest.fixture()
def cidade(sessao_db) -> Cidade:
    registro = Cidade(codigo_municipio=5208707, nome="Goiânia", uf="GO")
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


def _dados(cidade_id: str | None = None, cidade_ibge: int | None = None, **overrides) -> dict:
    base = dict(
        razao_social="Distribuidora Saúde Total Ltda",
        nome_fantasia="Saúde Total",
        cpf_cnpj="12.345.678/0001-90",
        cidade_id=cidade_id,
        cidade_ibge=cidade_ibge,
    )
    base.update(overrides)
    return base


class TestCriar:
    def test_cria_com_cidade_id(self, sessao_db, cidade):
        dados = ClienteCriarSchema(**_dados(cidade_id=cidade.id))
        cliente = cliente_service.criar(sessao_db, dados)
        assert cliente.cidade_id == cidade.id

    def test_cria_resolvendo_cidade_ibge(self, sessao_db, cidade):
        dados = ClienteCriarSchema(**_dados(cidade_ibge=cidade.codigo_municipio))
        cliente = cliente_service.criar(sessao_db, dados)
        assert cliente.cidade_id == cidade.id

    def test_sem_cidade_id_e_sem_cidade_ibge_gera_erro_de_validacao(self):
        with pytest.raises(ValueError):
            ClienteCriarSchema(**_dados())

    def test_permite_cpf_cnpj_duplicado(self, sessao_db, cidade):
        cliente_service.criar(sessao_db, ClienteCriarSchema(**_dados(cidade_id=cidade.id)))
        segundo = cliente_service.criar(
            sessao_db, ClienteCriarSchema(**_dados(cidade_id=cidade.id, razao_social="Outra Empresa Ltda", nome_fantasia="Outra"))
        )
        assert segundo.cpf_cnpj == "12.345.678/0001-90"

    def test_cidade_ibge_inexistente_gera_404(self, sessao_db):
        dados = ClienteCriarSchema(**_dados(cidade_ibge=9999999))
        with pytest.raises(HTTPException) as exc:
            cliente_service.criar(sessao_db, dados)
        assert exc.value.status_code == 404


class TestAtualizar:
    def test_atualiza_resolvendo_cidade_ibge(self, sessao_db, cidade):
        criado = cliente_service.criar(sessao_db, ClienteCriarSchema(**_dados(cidade_id=cidade.id)))

        outra_cidade = Cidade(codigo_municipio=3550308, nome="São Paulo", uf="SP")
        sessao_db.add(outra_cidade)
        sessao_db.commit()

        dados = ClienteAtualizarSchema(**_dados(cidade_ibge=outra_cidade.codigo_municipio))
        atualizado = cliente_service.atualizar(sessao_db, criado.id, dados)
        assert atualizado.cidade_id == outra_cidade.id

    def test_atualiza_por_id_da_url_quando_sistema_origem_id_nao_informado(self, sessao_db, cidade):
        criado = cliente_service.criar(sessao_db, ClienteCriarSchema(**_dados(cidade_id=cidade.id)))

        dados = ClienteAtualizarSchema(**_dados(cidade_id=cidade.id, razao_social="Novo Nome Ltda"))
        atualizado = cliente_service.atualizar(sessao_db, criado.id, dados)
        assert atualizado.razao_social == "Novo Nome Ltda"

    def test_atualiza_por_sistema_origem_id_quando_informado(self, sessao_db, cidade):
        criado = cliente_service.criar(
            sessao_db, ClienteCriarSchema(**_dados(cidade_id=cidade.id, sistema_origem_id="ERP-123"))
        )

        dados = ClienteAtualizarSchema(**_dados(cidade_id=cidade.id, razao_social="Novo Nome Ltda"))
        atualizado = cliente_service.atualizar(
            sessao_db, cliente_id="id-qualquer-invalido", dados=dados, sistema_origem_id="ERP-123"
        )
        assert atualizado.id == criado.id
        assert atualizado.razao_social == "Novo Nome Ltda"

    def test_nao_apaga_sistema_origem_id_quando_corpo_nao_o_repete(self, sessao_db, cidade):
        """Regressão: o cliente é identificado via ?sistema_origem_id=X na URL,
        mas o corpo da requisição não repete o campo (o integrador já disse
        quem é pela query string). O valor precisa ser preservado, não
        sobrescrito para null."""
        criado = cliente_service.criar(
            sessao_db, ClienteCriarSchema(**_dados(cidade_id=cidade.id, sistema_origem_id="ERP-123"))
        )

        dados = ClienteAtualizarSchema(**_dados(cidade_id=cidade.id, razao_social="Novo Nome Ltda"))
        assert dados.sistema_origem_id is None

        atualizado = cliente_service.atualizar(
            sessao_db, cliente_id="irrelevante", dados=dados, sistema_origem_id="ERP-123"
        )
        assert atualizado.sistema_origem_id == "ERP-123"

    def test_sistema_origem_id_duplicado_gera_409(self, sessao_db, cidade):
        cliente_service.criar(sessao_db, ClienteCriarSchema(**_dados(cidade_id=cidade.id, sistema_origem_id="ERP-1")))

        dados = ClienteCriarSchema(**_dados(cidade_id=cidade.id, cpf_cnpj="23.456.789/0001-11", sistema_origem_id="ERP-1"))
        with pytest.raises(HTTPException) as exc:
            cliente_service.criar(sessao_db, dados)
        assert exc.value.status_code == 409

    def test_sistema_origem_id_inexistente_gera_404(self, sessao_db, cidade):
        cliente_service.criar(sessao_db, ClienteCriarSchema(**_dados(cidade_id=cidade.id)))

        dados = ClienteAtualizarSchema(**_dados(cidade_id=cidade.id))
        with pytest.raises(HTTPException) as exc:
            cliente_service.atualizar(sessao_db, cliente_id="irrelevante", dados=dados, sistema_origem_id="nao-existe")
        assert exc.value.status_code == 404


class TestListarPaginado:
    def test_lista_paginado_sem_filtro(self, sessao_db, cidade):
        cliente_service.criar(
            sessao_db, ClienteCriarSchema(**_dados(cidade_id=cidade.id, cpf_cnpj="12.345.678/0001-90"))
        )
        cliente_service.criar(
            sessao_db,
            ClienteCriarSchema(
                **_dados(cidade_id=cidade.id, cpf_cnpj="23.456.789/0001-11", razao_social="Hospital Vida Plena", nome_fantasia="Vida Plena")
            ),
        )

        itens, total = cliente_service.listar_paginado(sessao_db, page=1, per_page=20, sort="nome_fantasia", sort_type="asc")
        assert total == 2
        assert len(itens) == 2

    def test_filtra_por_q_em_razao_social_fantasia_ou_cpf_cnpj(self, sessao_db, cidade):
        cliente_service.criar(
            sessao_db, ClienteCriarSchema(**_dados(cidade_id=cidade.id, cpf_cnpj="12.345.678/0001-90"))
        )
        cliente_service.criar(
            sessao_db,
            ClienteCriarSchema(
                **_dados(cidade_id=cidade.id, cpf_cnpj="23.456.789/0001-11", razao_social="Hospital Vida Plena", nome_fantasia="Vida Plena")
            ),
        )

        itens, total = cliente_service.listar_paginado(sessao_db, page=1, per_page=20, sort="nome_fantasia", sort_type="asc", q="vida")
        assert total == 1
        assert itens[0].nome_fantasia == "Vida Plena"

    def test_sort_invalido_gera_422(self, sessao_db):
        with pytest.raises(HTTPException) as exc:
            cliente_service.listar_paginado(sessao_db, page=1, per_page=20, sort="campo_inexistente", sort_type="asc")
        assert exc.value.status_code == 422
