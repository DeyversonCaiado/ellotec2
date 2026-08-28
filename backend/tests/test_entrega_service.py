"""
Testes do domínio entregas (app/domains/entregas).

O foco é no que o sistema antigo fazia frágil e que a migração precisa manter
correto:

- a integração REPROCESSA — o mesmo mapa e a mesma nota não podem duplicar;
- o status da nota é derivado da última interação, e tem que acompanhar edição
  e exclusão, não só inclusão;
- editar uma interação NÃO pode reordenar a linha do tempo;
- vendedor sem `entregas.ver_todas` não enxerga nota de outro.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.domains.empresas.empresa_model import Empresa
from app.domains.entregas import entrega_service
from app.domains.entregas.entrega_contrato import (
    EntregaCriarSchema,
    EntregaNotaCriarSchema,
    FiltrosListagemSchema,
    InteracaoAtualizarSchema,
    InteracaoCriarSchema,
)
from app.domains.usuarios.cargo_model import Cargo
from app.domains.usuarios.usuario_model import Usuario


@pytest.fixture()
def empresa(sessao_db) -> Empresa:
    registro = Empresa(
        razao_social="ELLO DISTRIBUICAO LTDA",
        nome_fantasia="Ello",
        cnpj="14.115.388/0001-80",
    )
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


@pytest.fixture()
def cargo(sessao_db) -> Cargo:
    registro = Cargo(nome="Logística")
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


def _criar_usuario(sessao_db, cargo, login: str, nome: str, codigo: str | None) -> Usuario:
    registro = Usuario(
        usuario=login,
        nome=nome,
        email=f"{login}@ello.com.br",
        senha_hash="x",
        cargo_id=cargo.id,
        sistema_origem_id=codigo,
    )
    sessao_db.add(registro)
    sessao_db.commit()
    return registro


@pytest.fixture()
def operador(sessao_db, cargo) -> Usuario:
    return _criar_usuario(sessao_db, cargo, "00233", "VALERIA ROSA DA SILVA", "00233")


@pytest.fixture()
def vendedor(sessao_db, cargo) -> Usuario:
    return _criar_usuario(sessao_db, cargo, "00132", "MARCOS FONSECA", "00132")


def _dados_nota(empresa, **overrides) -> EntregaNotaCriarSchema:
    base = dict(
        empresa_id=empresa.id,
        numero_nota="0116606",
        serie="1",
        pedido="0186009",
        tipo_nota="venda",
        data_nota=datetime(2026, 8, 20, 10, 0),
        valor_total=Decimal("15347.04"),
        cliente_nome="HOSPITAL SANTA CASA",
        cliente_cidade="Goiânia",
        cliente_uf="GO",
        itens=[
            dict(
                numero_item=1,
                produto_codigo="12-2818",
                produto_descricao="LANCETA DE SEGURANCA 28GX1.8MM",
                quantidade=Decimal("2000"),
                preco_unitario=Decimal("7.1292800000"),
                valor_total=Decimal("14258.56"),
                lote="2512366503",
            )
        ],
    )
    base.update(overrides)
    return EntregaNotaCriarSchema(**base)


class TestIntegracao:
    def test_reprocessar_a_mesma_nota_atualiza_em_vez_de_duplicar(self, sessao_db, empresa):
        """O job de integração roda de novo — é o caso normal, não a exceção."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, cliente_nome="HOSPITAL SANTA CASA DE GOIAS")
        )

        notas, total = entrega_service.listar_paginado(
            sessao_db, 1, 20, "data_nota", "desc"
        )
        assert total == 1
        assert notas[0].cliente_nome == "HOSPITAL SANTA CASA DE GOIAS"

    def test_serie_diferente_e_outra_nota(self, sessao_db, empresa):
        """A série entra na chave natural justamente para isso: sem ela, duas
        notas de séries diferentes com o mesmo número colidiriam."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa, serie="1"))
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa, serie="4"))

        _, total = entrega_service.listar_paginado(sessao_db, 1, 20, "data_nota", "desc")
        assert total == 2

    def test_nota_sem_mapa_fica_sem_prazo(self, sessao_db, empresa):
        """A contagem do prazo só começa quando a mercadoria sai."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        notas, _ = entrega_service.listar_paginado(sessao_db, 1, 20, "data_nota", "desc")

        assert notas[0].data_prevista_entrega is None
        assert notas[0].status_prazo == "sem_mapa"
        # O prazo em DIAS já é conhecido (depende só do destino) — o que falta
        # é a data-base para contar a partir dela.
        assert notas[0].prazo_dias == 1

    def test_mapa_que_chega_depois_vincula_as_notas_e_calcula_o_prazo(
        self, sessao_db, empresa
    ):
        """As duas integrações são independentes: o mapa pode chegar depois da
        nota, e nesse caso é ele que costura o vínculo."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa, entrega_numero_mapa="49852"))

        notas, _ = entrega_service.listar_paginado(sessao_db, 1, 20, "data_nota", "desc")
        assert notas[0].numero_mapa is None  # o mapa ainda não existia

        entrega_service.registrar_entrega(
            sessao_db,
            EntregaCriarSchema(
                empresa_id=empresa.id,
                numero_mapa="49852",
                data_mapa=datetime(2026, 8, 20, 18, 0),
                transportadora_nome="RODONAVES",
            ),
        )
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa, entrega_numero_mapa="49852"))

        notas, _ = entrega_service.listar_paginado(sessao_db, 1, 20, "data_nota", "desc")
        assert notas[0].numero_mapa == "49852"
        # GO/Goiânia = D+1 útil a partir de quinta 20/08 → sexta 21/08.
        assert notas[0].data_prevista_entrega == date(2026, 8, 21)

    def test_vendedor_desconhecido_nao_recusa_a_nota(self, sessao_db, empresa):
        """Código de funcionário que não existe aqui é problema de cadastro —
        perder o documento por causa dele seria pior."""
        nota = entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, vendedor_sistema_origem_id="99999")
        )
        assert nota.vendedor_id is None

    def test_precisao_decimal_do_item_sobrevive_ao_banco(self, sessao_db, empresa):
        nota = entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        sessao_db.expire_all()

        resposta = entrega_service.montar_resposta(
            sessao_db, entrega_service.obter_por_id(sessao_db, nota.id)
        )
        assert resposta.itens[0].preco_unitario == pytest.approx(7.12928)


class TestTimeline:
    def test_status_da_nota_segue_a_ultima_interacao(self, sessao_db, empresa, operador):
        nota = entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        assert nota.status_atual == "aguardando_embarque"

        entrega_service.registrar_interacao(
            sessao_db,
            nota.id,
            InteracaoCriarSchema(status="em_transito", observacao="Saiu do CD"),
            operador.id,
        )
        entrega_service.registrar_interacao(
            sessao_db,
            nota.id,
            InteracaoCriarSchema(status="entrega_realizada", observacao="Recebido por Luan"),
            operador.id,
        )

        atualizada = entrega_service.obter_por_id(sessao_db, nota.id)
        assert atualizada.status_atual == "entrega_realizada"
        assert atualizada.data_entrega_realizada is not None

    def test_apagar_a_ultima_interacao_volta_o_status_anterior(
        self, sessao_db, empresa, operador
    ):
        """O status é derivado da timeline — se o último evento sai, o status
        volta a ser o do evento anterior."""
        nota = entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        entrega_service.registrar_interacao(
            sessao_db, nota.id, InteracaoCriarSchema(status="em_transito"), operador.id
        )
        nota = entrega_service.registrar_interacao(
            sessao_db,
            nota.id,
            InteracaoCriarSchema(status="entrega_realizada"),
            operador.id,
        )
        ultima_id = [i for i in nota.interacoes if i.sync_deleted_at is None][0].id

        entrega_service.apagar_interacao(sessao_db, nota.id, ultima_id)

        atualizada = entrega_service.obter_por_id(sessao_db, nota.id)
        assert atualizada.status_atual == "em_transito"
        assert atualizada.data_entrega_realizada is None

    def test_editar_nao_reordena_a_linha_do_tempo(self, sessao_db, empresa, operador):
        """Corrigir um texto de ontem não pode empurrar aquele evento para o
        topo de hoje — nem a `data_interacao` nem a `sequencia` mudam na
        edição."""
        nota = entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        primeira = entrega_service.registrar_interacao(
            sessao_db, nota.id, InteracaoCriarSchema(status="aguardando_embarque"), operador.id
        )
        id_antiga = primeira.interacoes[0].id

        entrega_service.registrar_interacao(
            sessao_db, nota.id, InteracaoCriarSchema(status="em_transito"), operador.id
        )
        entrega_service.atualizar_interacao(
            sessao_db,
            nota.id,
            id_antiga,
            InteracaoAtualizarSchema(status="aguardando_embarque", observacao="corrigido"),
            operador.id,
        )

        resposta = entrega_service.montar_resposta(
            sessao_db, entrega_service.obter_por_id(sessao_db, nota.id)
        )
        # A editada continua embaixo, e o status da nota continua sendo o do
        # evento mais recente.
        assert resposta.interacoes[0].status == "em_transito"
        assert resposta.interacoes[-1].observacao == "corrigido"
        assert resposta.status_atual == "em_transito"

    def test_data_da_timeline_nao_e_campo_de_sincronizacao(
        self, sessao_db, empresa, operador
    ):
        """`data_interacao` é campo de negócio com coluna própria. Editar a
        interação mexe nos campos de auditoria da linha (sync_updated_at) e
        NÃO pode mexer na data do evento — é o que garante que a timeline não
        reordena sozinha depois de um reprocessamento ou de uma correção."""
        nota = entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        nota = entrega_service.registrar_interacao(
            sessao_db, nota.id, InteracaoCriarSchema(status="em_transito"), operador.id
        )
        interacao = nota.interacoes[0]
        data_do_evento = interacao.data_interacao
        assert data_do_evento is not None

        entrega_service.atualizar_interacao(
            sessao_db,
            nota.id,
            interacao.id,
            InteracaoAtualizarSchema(status="em_transito", observacao="texto corrigido"),
            operador.id,
        )
        sessao_db.expire_all()

        resposta = entrega_service.montar_resposta(
            sessao_db, entrega_service.obter_por_id(sessao_db, nota.id)
        )
        assert resposta.interacoes[0].data_interacao == data_do_evento

    def test_edicao_fica_registrada(self, sessao_db, empresa, operador, vendedor):
        nota = entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        nota = entrega_service.registrar_interacao(
            sessao_db, nota.id, InteracaoCriarSchema(status="em_transito"), operador.id
        )
        interacao_id = nota.interacoes[0].id

        entrega_service.atualizar_interacao(
            sessao_db,
            nota.id,
            interacao_id,
            InteracaoAtualizarSchema(status="com_ocorrencia", observacao="Avaria"),
            vendedor.id,
        )

        resposta = entrega_service.montar_resposta(
            sessao_db, entrega_service.obter_por_id(sessao_db, nota.id)
        )
        assert resposta.interacoes[0].usuario_nome == "VALERIA ROSA DA SILVA"
        assert resposta.interacoes[0].editado_por_nome == "MARCOS FONSECA"
        assert resposta.interacoes[0].editado_em is not None

    def test_interacao_de_outra_nota_nao_e_editavel_pela_url(
        self, sessao_db, empresa, operador
    ):
        nota_a = entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        nota_b = entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, numero_nota="0116607")
        )
        nota_a = entrega_service.registrar_interacao(
            sessao_db, nota_a.id, InteracaoCriarSchema(status="em_transito"), operador.id
        )
        interacao_de_a = nota_a.interacoes[0].id

        with pytest.raises(HTTPException) as erro:
            entrega_service.atualizar_interacao(
                sessao_db,
                nota_b.id,
                interacao_de_a,
                InteracaoAtualizarSchema(status="com_ocorrencia"),
                operador.id,
            )
        assert erro.value.status_code == 404


class TestVisibilidade:
    def test_vendedor_sem_ver_todas_so_enxerga_as_proprias(
        self, sessao_db, empresa, vendedor
    ):
        entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, vendedor_sistema_origem_id="00132")
        )
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa, numero_nota="0116607"))

        _, total_geral = entrega_service.listar_paginado(sessao_db, 1, 20, "data_nota", "desc")
        _, total_dele = entrega_service.listar_paginado(
            sessao_db, 1, 20, "data_nota", "desc", apenas_vendedor_id=vendedor.id
        )
        assert (total_geral, total_dele) == (2, 1)

    def test_restricao_vale_tambem_no_acesso_direto_por_id(
        self, sessao_db, empresa, vendedor
    ):
        """Sem isso, quem não vê a nota na lista veria colando a URL."""
        alheia = entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))

        with pytest.raises(HTTPException) as erro:
            entrega_service.obter_por_id(sessao_db, alheia.id, apenas_vendedor_id=vendedor.id)
        assert erro.value.status_code == 404


class TestFiltros:
    def test_filtra_por_status_prazo_sobre_a_base_inteira(self, sessao_db, empresa, operador):
        """`status_prazo` não é coluna — é traduzido para condições sobre
        data_prevista/entrega_id, para o filtro valer na base toda e não só na
        página carregada."""
        entrega_service.registrar_entrega(
            sessao_db,
            EntregaCriarSchema(
                empresa_id=empresa.id,
                numero_mapa="1",
                data_mapa=datetime(2020, 1, 6, 8, 0),  # bem no passado
            ),
        )
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa, entrega_numero_mapa="1"))
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa, numero_nota="0116607"))

        _, atrasadas = entrega_service.listar_paginado(
            sessao_db, 1, 20, "data_nota", "desc", status_prazo="em_atraso"
        )
        _, sem_mapa = entrega_service.listar_paginado(
            sessao_db, 1, 20, "data_nota", "desc", status_prazo="sem_mapa"
        )
        assert (atrasadas, sem_mapa) == (1, 1)

    def test_sort_invalido_gera_422(self, sessao_db):
        with pytest.raises(HTTPException) as erro:
            entrega_service.listar_paginado(sessao_db, 1, 20, "campo_inexistente", "asc")
        assert erro.value.status_code == 422


# ===========================================================================
# O painel de filtros: cada campo aceita vários valores, e as opções que a tela
# oferece saem do próprio período.
#
# O que estes testes protegem, acima de tudo, é o CASAMENTO entre as duas
# coisas: o valor que `opcoes_de_filtros` oferece tem que ser aceito por
# `listar_paginado`. Quando as duas listas divergem, a tela oferece um valor
# que devolve zero linhas — e o defeito é invisível em code review.
# ===========================================================================


def _opcoes(sessao_db, **kwargs) -> dict[str, list[str]]:
    """As sugestões de TODOS os campos, montadas como a tela monta: uma chamada
    por campo ao mesmo endpoint. Existe para os testes lerem como antes, agora
    que o backend responde por campo em vez de despejar tudo de uma vez."""
    return {
        campo: entrega_service.sugestoes_de_campo(sessao_db, campo=campo, **kwargs).valores
        for campo in type(FiltrosListagemSchema()).model_fields
    }


def _filtros(**campos) -> FiltrosListagemSchema:
    return FiltrosListagemSchema(**campos)


class TestPainelDeFiltros:
    def test_varios_valores_no_mesmo_campo_sao_ou(self, sessao_db, empresa):
        """Escolher GO e DF traz as duas — filtro múltiplo soma, não intersecta."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(empresa, numero_nota="0116607", cliente_uf="DF", cliente_cidade="Brasilia"),
        )
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(empresa, numero_nota="0116608", cliente_uf="SP", cliente_cidade="Santos"),
        )

        _, total = entrega_service.listar_paginado(
            sessao_db, 1, 20, "data_nota", "desc", filtros=_filtros(uf=["GO", "DF"])
        )
        assert total == 2

    def test_campos_diferentes_sao_e(self, sessao_db, empresa):
        """UF GO E cidade Anapolis nao pode trazer a nota de Goiania."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, numero_nota="0116607", cliente_cidade="Anapolis")
        )

        _, total = entrega_service.listar_paginado(
            sessao_db,
            1,
            20,
            "data_nota",
            "desc",
            filtros=_filtros(uf=["GO"], cidade=["Anapolis"]),
        )
        assert total == 1

    def test_filtro_de_item_nao_multiplica_a_nota(self, sessao_db, empresa):
        """A regra que justifica EXISTS em vez de JOIN.

        Com join, uma nota de 3 itens da mesma marca apareceria 3 vezes: o total
        do rodape mentiria e a paginacao repetiria linhas.
        """
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                itens=[
                    dict(
                        numero_item=n,
                        produto_codigo=f"12-281{n}",
                        produto_descricao=f"LANCETA {n}",
                        marca_nome="DESCARPACK",
                        quantidade=Decimal("10"),
                        lote=f"LOTE{n}",
                    )
                    for n in (1, 2, 3)
                ],
            ),
        )

        notas, total = entrega_service.listar_paginado(
            sessao_db, 1, 20, "data_nota", "desc", filtros=_filtros(marca=["DESCARPACK"])
        )
        assert total == 1
        assert len(notas) == 1

    def test_filtro_de_produto_traz_a_nota_inteira(self, sessao_db, empresa):
        """"Quais entregas levam o produto X" devolve a NOTA, nao o item."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                numero_nota="0116607",
                itens=[
                    dict(
                        numero_item=1,
                        produto_codigo="99-0001",
                        produto_descricao="SERINGA 5ML",
                        quantidade=Decimal("50"),
                    )
                ],
            ),
        )

        _, total = entrega_service.listar_paginado(
            sessao_db, 1, 20, "data_nota", "desc", filtros=_filtros(produto=["SERINGA 5ML"])
        )
        assert total == 1

    def test_filtro_de_mapa_nao_derruba_nota_sem_mapa(self, sessao_db, empresa):
        """`.has()` e nao join: sem isso, filtrar por qualquer coisa do mapa
        sumiria com as notas que ainda nao entraram em nenhum — e "sem mapa" e
        uma das abas da propria tela."""
        entrega_service.registrar_entrega(
            sessao_db,
            EntregaCriarSchema(
                empresa_id=empresa.id, numero_mapa="49852", data_mapa=datetime(2026, 8, 20, 18, 0)
            ),
        )
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa, entrega_numero_mapa="49852"))
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa, numero_nota="0116607"))

        _, com_mapa = entrega_service.listar_paginado(
            sessao_db, 1, 20, "data_nota", "desc", filtros=_filtros(numero_mapa=["49852"])
        )
        _, sem_filtro = entrega_service.listar_paginado(sessao_db, 1, 20, "data_nota", "desc")
        assert (com_mapa, sem_filtro) == (1, 2)

    def test_data_da_nota_compara_pelo_dia(self, sessao_db, empresa):
        """A coluna e DATETIME e a pessoa escolhe um DIA numa lista. Sem
        comparar por dia, "20/08/2026" nunca casaria com "20/08/2026 10:00"."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))

        _, total = entrega_service.listar_paginado(
            sessao_db, 1, 20, "data_nota", "desc", filtros=_filtros(data_nota=[date(2026, 8, 20)])
        )
        assert total == 1

    def test_filtra_por_apelido_da_empresa(self, sessao_db, empresa):
        """A tela lista o apelido, nao o UUID — e e o apelido que volta."""
        empresa.apelido = "Matriz"
        sessao_db.commit()
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))

        _, achou = entrega_service.listar_paginado(
            sessao_db, 1, 20, "data_nota", "desc", filtros=_filtros(empresa=["Matriz"])
        )
        _, nao_achou = entrega_service.listar_paginado(
            sessao_db, 1, 20, "data_nota", "desc", filtros=_filtros(empresa=["BSB"])
        )
        assert (achou, nao_achou) == (1, 0)

    def test_resumo_traz_o_apelido_da_empresa(self, sessao_db, empresa):
        empresa.apelido = "Matriz"
        sessao_db.commit()
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))

        notas, _ = entrega_service.listar_paginado(sessao_db, 1, 20, "data_nota", "desc")
        assert notas[0].empresa_apelido == "Matriz"

    def test_sem_apelido_cai_no_nome_fantasia(self, sessao_db, empresa):
        """Celula em branco nao diz de qual filial e a entrega — que e a unica
        razao de a coluna existir."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))

        notas, _ = entrega_service.listar_paginado(sessao_db, 1, 20, "data_nota", "desc")
        assert notas[0].empresa_apelido == "Ello"


class TestOpcoesDeFiltros:
    def test_oferece_os_valores_que_existem_no_periodo(self, sessao_db, empresa, vendedor):
        empresa.apelido = "Matriz"
        sessao_db.commit()
        entrega_service.registrar_entrega(
            sessao_db,
            EntregaCriarSchema(
                empresa_id=empresa.id, numero_mapa="49852", data_mapa=datetime(2026, 8, 20, 18, 0)
            ),
        )
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                entrega_numero_mapa="49852",
                vendedor_sistema_origem_id="00132",
                situacao="NF",
            ),
        )
        entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, numero_nota="0116607", cliente_uf="DF")
        )

        opcoes = _opcoes(sessao_db)

        assert opcoes["uf"] == ["DF", "GO"]  # ordenado, sem repetir
        assert opcoes["empresa"] == ["Matriz"]
        assert opcoes["vendedor"] == ["MARCOS FONSECA"]
        assert opcoes["numero_mapa"] == ["49852"]
        assert opcoes["situacao"] == ["NF"]
        assert opcoes["produto"] == ["LANCETA DE SEGURANCA 28GX1.8MM"]
        assert opcoes["lote"] == ["2512366503"]
        assert opcoes["data_nota"] == ["2026-08-20"]

    def test_todo_valor_oferecido_e_aceito_pelo_filtro(self, sessao_db, empresa, vendedor):
        """O casamento entre as duas pontas.

        Se a lista oferecesse um valor que o filtro nao reconhece, a tela
        devolveria zero linhas para uma escolha que ela mesma sugeriu — e
        ninguem veria isso lendo o codigo de um lado so.
        """
        empresa.apelido = "Matriz"
        sessao_db.commit()
        entrega_service.registrar_entrega(
            sessao_db,
            EntregaCriarSchema(
                empresa_id=empresa.id, numero_mapa="49852", data_mapa=datetime(2026, 8, 20, 18, 0)
            ),
        )
        # A nota preenche TODO campo do painel: o teste percorre os campos do
        # contrato, e um campo vazio no cenario passaria por engano.
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                entrega_numero_mapa="49852",
                vendedor_sistema_origem_id="00132",
                situacao="NF",
                transportadora_nome="RODONAVES",
                chave_acesso_nota=_chave("116606"),
                chave_acesso_referenciada=_chave("116000"),
                itens=[
                    dict(
                        numero_item=1,
                        produto_codigo="12-2818",
                        produto_descricao="LANCETA DE SEGURANCA 28GX1.8MM",
                        marca_nome="DESCARPACK",
                        quantidade=Decimal("2000"),
                        lote="2512366503",
                    )
                ],
            ),
        )

        opcoes = _opcoes(sessao_db)

        for campo in type(FiltrosListagemSchema()).model_fields:
            valores = opcoes[campo]
            assert valores, f"campo {campo} nao ofereceu nenhum valor"
            _, total = entrega_service.listar_paginado(
                sessao_db, 1, 20, "data_nota", "desc", filtros=_filtros(**{campo: valores[:1]})
            )
            assert total >= 1, f"o filtro {campo}={valores[0]!r} devolveu zero linhas"

    def test_nao_vaza_valores_de_notas_que_o_vendedor_nao_pode_ver(
        self, sessao_db, empresa, vendedor
    ):
        """A lista de opcoes tem que respeitar a mesma visibilidade da listagem
        — senao o autocomplete mostra o cliente do colega."""
        entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, vendedor_sistema_origem_id="00132")
        )
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(empresa, numero_nota="0116607", cliente_nome="CLIENTE DE OUTRO VENDEDOR"),
        )

        opcoes = _opcoes(sessao_db, apenas_vendedor_id=vendedor.id)

        assert opcoes["cliente"] == ["HOSPITAL SANTA CASA"]

    def test_periodo_recorta_as_opcoes(self, sessao_db, empresa):
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                numero_nota="0116607",
                cliente_uf="SP",
                data_nota=datetime(2026, 7, 1, 9, 0),
            ),
        )

        opcoes = _opcoes(sessao_db, data_inicio=date(2026, 8, 1), data_fim=date(2026, 8, 31))

        assert opcoes["uf"] == ["GO"]


class TestChaveDeAcesso:
    """Snapshot vindo do ERP, como o resto de `entrega_notas`.

    Ter a chave aqui NÃO faz desta tabela fonte da verdade fiscal — quem
    responde por imposto, XML e situação na SEFAZ continua sendo
    `notas_fiscais`. Ela serve para identificar o documento sem ambiguidade e
    para amarrar uma devolução à nota de origem.
    """

    CHAVE = "52260814115388000180550010001166061000000015"
    ORIGEM = "52260714115388000180550010001100011000000027"

    def test_grava_as_duas_chaves(self, sessao_db, empresa):
        nota = entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                chave_acesso_nota=self.CHAVE,
                chave_acesso_referenciada=self.ORIGEM,
            ),
        )

        resposta = entrega_service.montar_resposta(sessao_db, nota)
        assert resposta.chave_acesso_nota == self.CHAVE
        assert resposta.chave_acesso_referenciada == self.ORIGEM

    def test_nota_sem_chave_continua_valida(self, sessao_db, empresa):
        """A integração pode mandar a nota antes de a chave ser conhecida —
        recusar o documento por isso perderia a entrega inteira."""
        nota = entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))

        resposta = entrega_service.montar_resposta(sessao_db, nota)
        assert resposta.chave_acesso_nota is None
        assert resposta.chave_acesso_referenciada is None

    def test_chave_com_tamanho_errado_e_recusada_na_entrada(self, empresa):
        """44 posições é o tamanho fixo do layout da NF-e. Gravar uma chave de
        43 só apareceria como problema no dia em que alguém tentasse cruzar
        esta linha com a nota fiscal — e aí ninguém lembraria do porquê."""
        with pytest.raises(ValueError):
            _dados_nota(empresa, chave_acesso_nota="123")

    def test_reprocessar_atualiza_a_chave(self, sessao_db, empresa):
        """A integração reprocessa: a chave que chega depois tem que sobrepor a
        que estava lá, senão a nota fica com o valor da primeira carga."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        nota = entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, chave_acesso_nota=self.CHAVE)
        )

        resposta = entrega_service.montar_resposta(sessao_db, nota)
        assert resposta.chave_acesso_nota == self.CHAVE


# ===========================================================================
# Devolução: a nota que volta aponta para a de origem pela chave de acesso.
#
# Duas pontas do mesmo vínculo:
#   - o FILTRO "Nota devolvida", que recorta pelo NÚMERO extraído da chave;
#   - a SEÇÃO do detalhe, que acha as devoluções de uma nota pela chave inteira.
# ===========================================================================


def _chave(numero: str, cnpj_sufixo: str = "14115388000180", serie: str = "001") -> str:
    """Monta uma chave de acesso de 44 posicoes com o numero no lugar certo.

    Layout da NF-e: cUF(2) AAMM(4) CNPJ(14) modelo(2) serie(3) nNF(9)
    tpEmis(1) cNF(8) DV(1). O numero ocupa as 9 posicoes a partir da 26a — e
    montar a chave aqui, em vez de escrever 44 digitos na mao, e o que faz o
    teste falhar se alguem mudar a posicao no service.
    """
    chave = "52" + "2608" + cnpj_sufixo + "55" + serie + numero.zfill(9) + "1" + "00000001" + "5"
    assert len(chave) == 44, f"chave montada com {len(chave)} posicoes"
    return chave


class TestPosicaoDoNumeroNaChave:
    def test_o_numero_sai_das_posicoes_26_a_34(self, sessao_db, empresa):
        """A regra inteira do filtro em uma linha: SUBSTR(chave, 26, 9).

        Se a posicao mudar, o filtro passa a recortar serie ou tpEmis e devolve
        zero linhas em silencio — sem este teste, ninguem descobre ate alguem
        procurar uma devolucao que existe.
        """
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                numero_nota="0116700",
                chave_acesso_nota=_chave("116700"),
                chave_acesso_referenciada=_chave("116606"),
            ),
        )

        opcoes = _opcoes(sessao_db)
        assert opcoes["nota_devolvida"] == ["000116606"]

    def test_filtra_pelo_numero_da_nota_devolvida(self, sessao_db, empresa):
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                numero_nota="0116700",
                chave_acesso_referenciada=_chave("116606"),
            ),
        )
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                numero_nota="0116701",
                chave_acesso_referenciada=_chave("999999"),
            ),
        )

        _, total = entrega_service.listar_paginado(
            sessao_db,
            1,
            20,
            "data_nota",
            "desc",
            filtros=_filtros(nota_devolvida=["000116606"]),
        )
        assert total == 1

    def test_nota_sem_chave_referenciada_nao_entra_nas_opcoes(self, sessao_db, empresa):
        """Nota que nao devolve nada nao pode virar uma opcao vazia no combo."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))

        opcoes = _opcoes(sessao_db)
        assert opcoes["nota_devolvida"] == []


class TestSecaoDeNotasDeDevolucao:
    def test_acha_as_devolucoes_pela_chave_de_acesso(self, sessao_db, empresa):
        """O vinculo e chave->chave, nao numero->numero: o numero se repete
        entre empresas e series, e casar por ele juntaria a devolucao da filial
        com a nota da matriz."""
        origem = entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, chave_acesso_nota=_chave("116606"))
        )
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                numero_nota="0116700",
                tipo_nota="devolucao_cliente",
                chave_acesso_nota=_chave("116700"),
                chave_acesso_referenciada=_chave("116606"),
            ),
        )

        resposta = entrega_service.montar_resposta(sessao_db, origem)

        assert [d.numero_nota for d in resposta.notas_devolucao] == ["0116700"]
        assert resposta.notas_devolucao[0].tipo_nota == "devolucao_cliente"

    def test_nota_sem_devolucao_traz_lista_vazia(self, sessao_db, empresa):
        origem = entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, chave_acesso_nota=_chave("116606"))
        )

        resposta = entrega_service.montar_resposta(sessao_db, origem)
        assert resposta.notas_devolucao == []

    def test_nota_sem_chave_nao_casa_com_ninguem(self, sessao_db, empresa):
        """Sem chave nesta nota nao ha por onde apontar para ela. Casar NULL com
        NULL traria toda nota sem chave referenciada como se fosse devolucao."""
        origem = entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))
        entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, numero_nota="0116700")
        )

        resposta = entrega_service.montar_resposta(sessao_db, origem)
        assert resposta.notas_devolucao == []

    def test_varias_devolucoes_saem_da_mais_recente_para_a_mais_antiga(
        self, sessao_db, empresa
    ):
        """Havendo devolucao parcial mais de uma vez, a ultima e a que explica
        o saldo de hoje."""
        origem = entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, chave_acesso_nota=_chave("116606"))
        )
        for numero, dia in (("0116700", 21), ("0116800", 25)):
            entrega_service.registrar_nota(
                sessao_db,
                _dados_nota(
                    empresa,
                    numero_nota=numero,
                    data_nota=datetime(2026, 8, dia, 10, 0),
                    chave_acesso_nota=_chave(numero.lstrip("0")),
                    chave_acesso_referenciada=_chave("116606"),
                ),
            )

        resposta = entrega_service.montar_resposta(sessao_db, origem)
        assert [d.numero_nota for d in resposta.notas_devolucao] == ["0116800", "0116700"]

    def test_nao_mostra_devolucao_de_nota_que_o_vendedor_nao_pode_ver(
        self, sessao_db, empresa, vendedor
    ):
        """A secao e listagem como outra qualquer — sem a restricao, ela vira o
        caminho para ver por dentro do detalhe o que a lista esconde."""
        origem = entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                chave_acesso_nota=_chave("116606"),
                vendedor_sistema_origem_id="00132",
            ),
        )
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                numero_nota="0116700",
                chave_acesso_referenciada=_chave("116606"),
            ),
        )

        resposta = entrega_service.montar_resposta(
            sessao_db, origem, apenas_vendedor_id=vendedor.id
        )
        assert resposta.notas_devolucao == []


class TestPeriodoPadraoDaApi:
    """Sem período na query, a API recorta o MÊS ATUAL.

    O padrão fica no router, não no service: "sem data = sem filtro" continua
    sendo a regra do service (os outros testes deste arquivo dependem disso), e
    o mês corrente é decisao da API — o que permite um relatorio futuro pedir a
    base toda sem lutar contra um recorte que ele nao escolheu.
    """

    def test_o_service_sem_data_continua_sem_filtrar(self, sessao_db, empresa):
        """A contraprova do desenho: quem chama o service direto pede tudo."""
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(empresa, data_nota=datetime(2020, 1, 15, 9, 0)),
        )

        _, total = entrega_service.listar_paginado(sessao_db, 1, 20, "data_nota", "desc")
        assert total == 1

    def test_listagem_e_opcoes_usam_o_mesmo_padrao(self, sessao_db, empresa):
        """Se as opcoes saissem de um intervalo e a lista de outro, o
        autocomplete ofereceria um valor que a listagem nao traz — e a pessoa
        concluiria que o filtro esta quebrado."""
        hoje = date.today()
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                data_nota=datetime(hoje.year, hoje.month, 1, 9, 0),
                cliente_uf="GO",
            ),
        )
        # Fora do mes atual: nao pode aparecer nem na lista nem nas opcoes.
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                numero_nota="0116607",
                data_nota=datetime(2020, 1, 15, 9, 0),
                cliente_uf="SP",
            ),
        )

        inicio, fim = hoje.replace(day=1), hoje
        _, total = entrega_service.listar_paginado(
            sessao_db, 1, 20, "data_nota", "desc", data_inicio=inicio, data_fim=fim
        )
        opcoes = _opcoes(sessao_db, data_inicio=inicio, data_fim=fim)

        assert total == 1
        assert opcoes["uf"] == ["GO"]


class TestSugestoesPorCampo:
    """Um endpoint so para os 19 campos, recortado pelo que a pessoa digita.

    Antes a tela carregava TODOS os valores de TODOS os campos a cada troca de
    periodo — num mes real, ~600 pedidos e centenas de numeros de nota numa
    resposta so, crescendo com o intervalo.
    """

    def test_o_termo_recorta_as_sugestoes(self, sessao_db, empresa):
        for numero, cliente in (
            ("0116606", "HOSPITAL SANTA CASA"),
            ("0116607", "CLINICA SAO LUCAS"),
            ("0116608", "SANTA GENOVEVA"),
        ):
            entrega_service.registrar_nota(
                sessao_db, _dados_nota(empresa, numero_nota=numero, cliente_nome=cliente)
            )

        sugestoes = entrega_service.sugestoes_de_campo(sessao_db, campo="cliente", termo="SANTA")

        assert sugestoes.valores == ["HOSPITAL SANTA CASA", "SANTA GENOVEVA"]
        assert sugestoes.truncado is False

    def test_o_termo_casa_no_meio_do_valor(self, sessao_db, empresa):
        """Quem procura o pedido "5185" nao sabe que ele comeca com zeros, e
        quem procura um cliente digita o meio do nome. Prefixo so serviria a
        campo numerico alinhado."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa, pedido="0186009"))

        sugestoes = entrega_service.sugestoes_de_campo(sessao_db, campo="pedido", termo="8600")
        assert sugestoes.valores == ["0186009"]

    def test_corta_no_teto_e_avisa(self, sessao_db, empresa):
        """`truncado` existe para a tela dizer "refine a busca" em vez de deixar
        a pessoa achar que aquilo e tudo que existe."""
        for i in range(6):
            entrega_service.registrar_nota(
                sessao_db, _dados_nota(empresa, numero_nota=f"011660{i}")
            )

        sugestoes = entrega_service.sugestoes_de_campo(
            sessao_db, campo="numero_nota", limite=3
        )

        assert len(sugestoes.valores) == 3
        assert sugestoes.truncado is True

    def test_campo_desconhecido_gera_422(self, sessao_db):
        """`campo` vem da query string. Conjunto fechado, como as colunas de
        ordenacao — aceitar qualquer nome abriria a porta para pedir uma coluna
        que a tela nao deveria expor."""
        with pytest.raises(HTTPException) as erro:
            entrega_service.sugestoes_de_campo(sessao_db, campo="senha_hash")
        assert erro.value.status_code == 422

    def test_quantidade_sai_sem_casas_decimais_a_toa(self, sessao_db, empresa):
        """Ninguem escolhe "2000.0000" numa lista."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))

        sugestoes = entrega_service.sugestoes_de_campo(sessao_db, campo="quantidade")
        assert sugestoes.valores == ["2000"]

    def test_data_sai_no_formato_que_o_filtro_aceita(self, sessao_db, empresa):
        """O valor sugerido volta como query param — se o formato nao casar com
        o que o contrato de entrada espera, a escolha da tela vira 422."""
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))

        sugestoes = entrega_service.sugestoes_de_campo(sessao_db, campo="data_nota")
        assert sugestoes.valores == ["2026-08-20"]

        _, total = entrega_service.listar_paginado(
            sessao_db,
            1,
            20,
            "data_nota",
            "desc",
            filtros=FiltrosListagemSchema(data_nota=sugestoes.valores),
        )
        assert total == 1


    def test_aceita_o_campo_em_camel_case(self, sessao_db, empresa, vendedor):
        """A TELA manda `numeroNota`, nao `numero_nota`.

        Ela usa uma chave so para as duas coisas — o parametro de filtro
        (`?numeroNota=0116606`) e o `?campo=` das sugestoes — e o contrato
        camelCasa os nomes. Este teste percorre os ALIASES, que e o que a API
        recebe de verdade; percorrer os nomes Python passava com o endpoint
        quebrado para todo campo de nome composto.
        """
        entrega_service.registrar_nota(
            sessao_db,
            _dados_nota(
                empresa,
                situacao="NF",
                transportadora_nome="RODONAVES",
                vendedor_sistema_origem_id="00132",
                chave_acesso_referenciada=_chave("116000"),
                itens=[
                    dict(
                        numero_item=1,
                        produto_codigo="12-2818",
                        produto_descricao="LANCETA",
                        marca_nome="DESCARPACK",
                        quantidade=Decimal("2000"),
                        lote="2512366503",
                    )
                ],
            ),
        )
        entrega_service.registrar_entrega(
            sessao_db,
            EntregaCriarSchema(
                empresa_id=empresa.id, numero_mapa="49852", data_mapa=datetime(2026, 8, 20, 18, 0)
            ),
        )
        entrega_service.registrar_nota(
            sessao_db, _dados_nota(empresa, numero_nota="0116607", entrega_numero_mapa="49852")
        )

        for nome, definicao in FiltrosListagemSchema.model_fields.items():
            alias = definicao.alias or nome
            sugestoes = entrega_service.sugestoes_de_campo(sessao_db, campo=alias)
            assert sugestoes.valores, f"campo {alias} nao ofereceu nenhum valor"


    def test_campo_de_data_nao_compara_com_string_vazia(self, sessao_db, empresa):
        """Regressao com nome: `DATE(x) != ''` faz o MySQL recusar com 1525
        ("Incorrect DATE value") e a requisicao morre.

        O SQLite dos testes aceita a mesma comparacao em silencio, entao este
        teste NAO teria pego o defeito — ele foi encontrado no navegador, contra
        o MySQL de verdade. Fica aqui para registrar a regra: descartar vazio so
        vale para coluna de texto.
        """
        entrega_service.registrar_nota(sessao_db, _dados_nota(empresa))

        for campo in ("dataNota", "dataMapa"):
            assert entrega_service.sugestoes_de_campo(sessao_db, campo=campo) is not None
