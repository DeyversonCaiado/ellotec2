"""
Testes da matriz de SLA de entrega (app/domains/entregas/entrega_prazo.py).

Esta é a razão de ser do módulo: no sistema antigo a matriz vivia dentro de um
`CASE` de ~100 linhas no SQL do Oracle, onde não havia como testá-la — e um
prazo errado só aparecia quando alguém reclamava que a entrega estava "em
atraso" sem estar.
"""

from datetime import date

from app.domains.entregas import entrega_prazo


class TestCapital:
    def test_reconhece_capital_com_acento_e_caixa_diferente(self):
        """O ERP manda a cidade em grafias diferentes. Sem normalizar, Goiânia
        seria tratada como interior e o prazo dobraria."""
        assert entrega_prazo.e_capital("GO", "Goiânia")
        assert entrega_prazo.e_capital("go", " GOIANIA ")
        assert entrega_prazo.e_capital("SP", "São Paulo")

    def test_interior_nao_e_capital(self):
        assert not entrega_prazo.e_capital("GO", "Anápolis")
        assert not entrega_prazo.e_capital("SP", "Campinas")

    def test_df_inteiro_conta_como_capital(self):
        """Regra herdada do sistema antigo: no DF não existe interior."""
        assert entrega_prazo.e_capital("DF", "Taguatinga")


class TestPrazoDias:
    def test_go_e_df_sao_um_dia_em_qualquer_cidade(self):
        assert entrega_prazo.calcular_prazo_dias("GO", "Goiânia", False) == 1
        assert entrega_prazo.calcular_prazo_dias("GO", "Rio Verde", False) == 1
        assert entrega_prazo.calcular_prazo_dias("DF", "Brasília", False) == 1

    def test_capital_e_interior_tem_prazos_diferentes(self):
        assert entrega_prazo.calcular_prazo_dias("SP", "São Paulo", False) == 3
        assert entrega_prazo.calcular_prazo_dias("SP", "Ribeirão Preto", False) == 5
        assert entrega_prazo.calcular_prazo_dias("AM", "Manaus", False) == 21
        assert entrega_prazo.calcular_prazo_dias("AM", "Parintins", False) == 25

    def test_termolabil_ignora_capital_e_usa_prazo_proprio(self):
        """Refrigerado não pode rodar o país esperando rota consolidar: o prazo
        é o mesmo na capital e no interior, e menor que o normal."""
        assert entrega_prazo.calcular_prazo_dias("AM", "Manaus", True) == 5
        assert entrega_prazo.calcular_prazo_dias("AM", "Parintins", True) == 5
        assert entrega_prazo.calcular_prazo_dias("SP", "Ribeirão Preto", True) == 2

    def test_uf_desconhecida_nao_tem_prazo(self):
        """`None` é informação legítima ('prazo não definido'), não erro."""
        assert entrega_prazo.calcular_prazo_dias("XX", "Cidade", False) is None
        assert entrega_prazo.calcular_prazo_dias(None, None, False) is None


class TestDiasUteis:
    def test_pula_o_fim_de_semana(self):
        # 2026-08-20 é uma quinta. D+3 cai na terça, não no domingo.
        assert entrega_prazo.somar_dias_uteis(date(2026, 8, 20), 3) == date(2026, 8, 25)

    def test_mapa_no_sabado_conta_a_partir_da_sexta(self):
        """Mapa fechado no fim de semana não teve dia útil naquele dia; contar
        da segunda daria um dia a mais do que a transportadora combinou."""
        # 2026-08-22 é sábado → base volta para sexta (21) → D+1 = segunda (24).
        assert entrega_prazo.somar_dias_uteis(date(2026, 8, 22), 1) == date(2026, 8, 24)
        # 2026-08-23 é domingo → mesma sexta, mesmo resultado.
        assert entrega_prazo.somar_dias_uteis(date(2026, 8, 23), 1) == date(2026, 8, 24)

    def test_data_prevista_exige_mapa_e_prazo(self):
        assert entrega_prazo.calcular_data_prevista(None, 3) is None
        assert entrega_prazo.calcular_data_prevista(date(2026, 8, 20), None) is None


class TestStatusPrazo:
    def test_entregue_vence_qualquer_atraso(self):
        """Entrega feita com atraso já é passado — listar como 'em atraso'
        pediria uma ação que não existe mais."""
        situacao = entrega_prazo.calcular_status_prazo(
            data_mapa=date(2026, 8, 1),
            data_prevista=date(2026, 8, 5),
            entregue=True,
            hoje=date(2026, 8, 23),
        )
        assert situacao == "entregue"

    def test_sem_mapa_nao_esta_atrasada(self):
        """A contagem só começa quando a mercadoria sai."""
        assert (
            entrega_prazo.calcular_status_prazo(None, None, False, date(2026, 8, 23))
            == "sem_mapa"
        )

    def test_atraso_e_no_prazo(self):
        assert (
            entrega_prazo.calcular_status_prazo(
                date(2026, 8, 1), date(2026, 8, 20), False, date(2026, 8, 23)
            )
            == "em_atraso"
        )
        assert (
            entrega_prazo.calcular_status_prazo(
                date(2026, 8, 1), date(2026, 8, 25), False, date(2026, 8, 23)
            )
            == "no_prazo"
        )

    def test_vencimento_no_proprio_dia_ainda_esta_no_prazo(self):
        """O prazo vence no fim do dia previsto, não no começo."""
        assert (
            entrega_prazo.calcular_status_prazo(
                date(2026, 8, 1), date(2026, 8, 23), False, date(2026, 8, 23)
            )
            == "no_prazo"
        )
