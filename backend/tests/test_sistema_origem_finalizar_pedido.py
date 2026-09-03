"""
A conversa com o Oracle do ERP ao finalizar um pedido, sem Oracle nenhum.

O banco do GESTCOM é **base de produção**: rodar estes testes contra ele
mudaria o status de pedidos de verdade. Por isso `conectar` é substituído por
uma conexão de mentira que só ANOTA o que recebeu — e é justamente sobre o que
foi anotado que os testes afirmam: quais comandos saíram, em que ordem, com que
parâmetros, e se houve `commit`.

O que estes testes protegem, em uma frase cada:

- o pedido fora do `PED` não é fechado, e nada é gravado nem no log do ERP;
- o `commit` acontece uma vez, no fim, e só depois de os dois comandos passarem;
- a espécie chega maiúscula no ERP mesmo que o operador digite minúscula;
- Oracle fora do ar vira 503 (canal indisponível), não 500 (defeito nosso).
"""

from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.domains.sistema_origem import sistema_origem_service
from app.shared.sistema_origem.gestcom.conexao import OracleIndisponivel

DADOS = {
    "empresa_sistema_origem_id": "1",
    "pedido_sistema_origem_id": "0185972",
    "usuario_sistema_origem_id": "00168",
    "volume": Decimal("4"),
    "especie": "CX",
    "peso_liquido": Decimal("12.500"),
    "peso_bruto": Decimal("13.200"),
}


class CursorFalso:
    def __init__(self, conexao: "ConexaoFalsa") -> None:
        self._conexao = conexao
        self.rowcount = 1
        self.fechado = False

    def execute(self, sql, parametros=None):  # noqa: ANN001
        self._conexao.comandos.append((" ".join(sql.split()), parametros or {}))

    def fetchone(self):
        return self._conexao.status_atual

    def close(self):
        self.fechado = True


class ConexaoFalsa:
    """Só o suficiente da API do `oracledb` para o service rodar inteiro."""

    def __init__(self, status_atual: tuple[str] | None) -> None:
        self.status_atual = status_atual
        self.comandos: list[tuple[str, dict]] = []
        self.commits = 0
        self.fechada = False
        self.cursor_criado: CursorFalso | None = None

    def cursor(self) -> CursorFalso:
        self.cursor_criado = CursorFalso(self)
        return self.cursor_criado

    def commit(self) -> None:
        self.commits += 1


@pytest.fixture()
def conexao(monkeypatch):
    """Devolve uma fábrica: o teste diz qual status o ERP tem para o pedido."""

    criadas: list[ConexaoFalsa] = []

    def preparar(status_atual: tuple[str] | None) -> ConexaoFalsa:
        conexao_falsa = ConexaoFalsa(status_atual)
        criadas.append(conexao_falsa)

        class _Contexto:
            def __enter__(self):
                return conexao_falsa

            def __exit__(self, *_):
                conexao_falsa.fechada = True
                return False

        monkeypatch.setattr(sistema_origem_service, "conectar", lambda *_a, **_k: _Contexto())
        return conexao_falsa

    return preparar


def _comandos(conexao_falsa: ConexaoFalsa) -> list[str]:
    return [sql for sql, _ in conexao_falsa.comandos]


def test_pedido_em_ped_e_fechado_com_um_commit_so(conexao):
    falsa = conexao(("PED",))

    sistema_origem_service.finalizar_pedido(**DADOS)

    comandos = _comandos(falsa)
    assert len(comandos) == 3
    # A ordem é a garantia: checar o status ANTES de gravar qualquer coisa.
    assert comandos[0].startswith("SELECT STATUS FROM FAT_CAPAPEDIDO")
    assert "FOR UPDATE" in comandos[0]
    assert comandos[1].startswith("INSERT INTO FAT_POLICE")
    assert comandos[2].startswith("UPDATE FAT_CAPAPEDIDO SET")
    assert falsa.commits == 1
    assert falsa.cursor_criado.fechado


def test_parametros_do_update_sao_os_que_o_erp_espera(conexao):
    falsa = conexao(("PED",))

    sistema_origem_service.finalizar_pedido(**DADOS)

    _, parametros = falsa.comandos[2]
    assert parametros == {
        "status": "FEC",
        "conferidor": "00168",
        "liberacao_sem_conferencia": "00168",
        # Texto, e sem separador decimal: `VOLUME_PEDIDO` é VARCHAR2(10) no
        # ERP, e um bind numérico viraria "4,0" pelo NLS da sessão.
        "volume": "4",
        "especie": "CX",
        "peso_liquido": 12.5,
        "peso_bruto": 13.2,
        "marca_pedido": "DIVERSOS",
        "empresa_id": "1",
        "pedido": "0185972",
    }
    # As cinco datas saem do relógio do BANCO (SYSDATE no SQL), nunca do
    # relógio da máquina que roda a API — dois relógios diferentes gravariam
    # horas diferentes no mesmo pedido.
    assert "DATA_HORA_CONFERENCIA = SYSDATE" in falsa.comandos[2][0]
    assert "DATA_HORA_ALTERACAO = SYSDATE" in falsa.comandos[2][0]
    assert falsa.comandos[1][0].count("SYSDATE") == 3

    _, log = falsa.comandos[1]
    assert log == {
        "funcionario": "00168",
        "formulario": "Situação de Pedidos",
        "terminal": "NOTRESFIN-ELL",
    }


def test_especie_minuscula_chega_maiuscula_no_erp(conexao):
    falsa = conexao(("PED",))

    sistema_origem_service.finalizar_pedido(**{**DADOS, "especie": "cx"})

    assert falsa.comandos[2][1]["especie"] == "CX"


def test_especie_aceita_os_dez_caracteres_da_coluna(conexao):
    """`ESPECIE_PEDIDO` é VARCHAR2(10) (conferido em `all_tab_columns`), então
    'CAIXA' e 'PALETE' passam — a versão anterior cortava em 2 por estimativa."""
    falsa = conexao(("PED",))

    sistema_origem_service.finalizar_pedido(**{**DADOS, "especie": "palete"})

    assert falsa.comandos[2][1]["especie"] == "PALETE"


def test_especie_acima_de_dez_caracteres_e_recusada(conexao):
    falsa = conexao(("PED",))

    with pytest.raises(HTTPException) as erro:
        sistema_origem_service.finalizar_pedido(**{**DADOS, "especie": "EMBALAGEM_GRANDE"})

    assert erro.value.status_code == 422
    assert falsa.comandos == []


def test_volume_vai_como_texto_de_digitos(conexao):
    """A coluna é VARCHAR2(10), não numérica. Deixar o Oracle converter um bind
    numérico gravaria "12,0" com NLS em português — e o resto do sistema tem
    "12". Os dois "parecem" doze, e é por isso que o bug seria difícil de ver."""
    falsa = conexao(("PED",))

    sistema_origem_service.finalizar_pedido(**{**DADOS, "volume": Decimal("12")})

    assert falsa.comandos[2][1]["volume"] == "12"


def test_pedido_fora_do_ped_nao_grava_nada(conexao):
    """O caso que a checagem existe para pegar: alguém faturou o pedido no ERP
    enquanto o galpão conferia. Fechar por cima apagaria o trabalho de lá."""
    falsa = conexao(("FAT",))

    with pytest.raises(HTTPException) as erro:
        sistema_origem_service.finalizar_pedido(**DADOS)

    assert erro.value.status_code == 409
    assert "'FAT'" in erro.value.detail
    # Só o SELECT rodou — nem o log do ERP foi escrito.
    assert len(falsa.comandos) == 1
    assert falsa.commits == 0


def test_pedido_inexistente_no_erp_e_404(conexao):
    falsa = conexao(None)

    with pytest.raises(HTTPException) as erro:
        sistema_origem_service.finalizar_pedido(**DADOS)

    assert erro.value.status_code == 404
    assert falsa.commits == 0


def test_update_que_nao_afeta_linha_nenhuma_nao_commita(conexao):
    falsa = conexao(("PED",))

    def executar_e_zerar(sql, parametros=None):  # noqa: ANN001
        falsa.comandos.append((" ".join(sql.split()), parametros or {}))
        if sql.strip().startswith("UPDATE"):
            falsa.cursor_criado.rowcount = 0

    original = falsa.cursor

    def cursor_com_rowcount_zero():
        cursor = original()
        cursor.execute = executar_e_zerar
        return cursor

    falsa.cursor = cursor_com_rowcount_zero

    with pytest.raises(HTTPException) as erro:
        sistema_origem_service.finalizar_pedido(**DADOS)

    assert erro.value.status_code == 409
    assert falsa.commits == 0


def test_usuario_sem_vinculo_nem_abre_conexao(conexao):
    """A recusa NOMEIA a conta. Sem isso a frase "seu usuário não tem vínculo"
    obriga a adivinhar de qual conta se está falando — e quem clicou não é
    necessariamente a conta que a pessoa acha que está usando: contas
    administrativas nossas (`admin`) não têm código no ERP e caem aqui."""
    falsa = conexao(("PED",))

    with pytest.raises(HTTPException) as erro:
        sistema_origem_service.finalizar_pedido(
            **{**DADOS, "usuario_sistema_origem_id": ""}, usuario_login="admin"
        )

    assert erro.value.status_code == 409
    assert "vínculo com o sistema de origem" in erro.value.detail
    assert "'admin'" in erro.value.detail
    assert falsa.comandos == []


def test_oracle_fora_do_ar_e_503_e_nao_500(monkeypatch):
    """503 é a informação correta: não é defeito nosso nem erro do operador, é
    o canal indisponível — e a conferência feita no galpão continua valendo."""

    def explodir(*_a, **_k):
        raise OracleIndisponivel("banco fora do ar")

    monkeypatch.setattr(sistema_origem_service, "conectar", explodir)

    with pytest.raises(HTTPException) as erro:
        sistema_origem_service.finalizar_pedido(**DADOS)

    assert erro.value.status_code == 503


def test_erro_do_driver_no_meio_da_transacao_e_502(conexao):
    """ORA-12899, trigger do ERP, constraint: nada foi commitado, e o operador
    precisa ver isso como 'o ERP recusou', não como tela quebrada."""
    falsa = conexao(("PED",))
    original = falsa.cursor

    def cursor_que_explode():
        cursor = original()

        def execute(sql, parametros=None):  # noqa: ANN001
            if sql.strip().startswith("INSERT"):
                raise RuntimeError("ORA-12899: value too large for column")
            falsa.comandos.append((" ".join(sql.split()), parametros or {}))

        cursor.execute = execute
        return cursor

    falsa.cursor = cursor_que_explode

    with pytest.raises(HTTPException) as erro:
        sistema_origem_service.finalizar_pedido(**DADOS)

    assert erro.value.status_code == 502
    assert "ORA-12899" in erro.value.detail
    assert falsa.commits == 0
