"""
Leitura GS1: o que o coletor manda vs. o que deve ser procurado no cadastro.

Sem HTTP e sem banco — é conversão de formato pura (`app/shared/gs1.py`), e é
onde mora o risco de tratar um código linear como QR Code (ou o contrário).
"""

import pytest

from app.shared import gs1

GS = gs1.SEPARADOR_GRUPO


class TestCodigoLinear:
    """Nada a extrair: o conteúdo é o código."""

    @pytest.mark.parametrize(
        "leitura",
        [
            "7891111111111",  # EAN-13
            "17891111111111",  # DUN-14
            "MED-0012",  # código interno, nem numérico é
        ],
    )
    def test_devolve_a_leitura_como_esta(self, leitura):
        assert gs1.extrair_gtin(leitura) is None
        assert gs1.codigos_para_buscar(leitura) == [leitura]

    def test_dun_14_comecando_com_01_nao_e_confundido_com_ai(self):
        """O DUN-14 '01...' tem 14 dígitos; um AI 01 precisaria de 16. É esse
        tamanho que separa os dois casos."""
        assert gs1.extrair_gtin("01891111111111") is None


class TestQrCodeGs1:
    def test_element_strings_com_separador(self):
        leitura = f"010789111111111{GS}17260101{GS}10LOTE123"
        assert gs1.extrair_gtin(f"01078911111111181{GS}10LOTE") == "07891111111118"
        assert gs1.extrair_gtin(leitura.replace(GS, "", 1)) is not None

    def test_gtin_lote_e_validade_concatenados(self):
        assert gs1.extrair_gtin("010789111111111817260101") == "07891111111118"

    def test_ai_01_depois_de_outro_campo(self):
        assert gs1.extrair_gtin(f"10LOTE123{GS}0107891111111118") == "07891111111118"

    def test_prefixo_de_simbologia_do_leitor_e_descartado(self):
        assert gs1.extrair_gtin(f"]d20107891111111118{GS}10LOTE") == "07891111111118"

    def test_gs1_digital_link(self):
        assert (
            gs1.extrair_gtin("https://id.gs1.org/01/07891111111118/10/LOTE123")
            == "07891111111118"
        )

    def test_digital_link_com_gtin_curto_e_completado_para_14(self):
        assert gs1.extrair_gtin("https://id.gs1.org/01/7891111111118") == "07891111111118"


class TestCodigosParaBuscar:
    def test_gtin_tambem_e_procurado_sem_os_zeros_a_esquerda(self):
        """O cadastro guarda EAN-13 com 13 dígitos; no QR Code o mesmo número
        vem com zero na frente. São o mesmo produto."""
        assert gs1.codigos_para_buscar(f"0107891111111118{GS}10LOTE") == [
            "07891111111118",
            "7891111111118",
        ]

    def test_gtin_sozinho_e_ambiguo_e_as_duas_formas_sao_tentadas(self):
        """'01' + 14 dígitos e mais nada pode ser um QR só com o GTIN ou um
        código linear de 16. A leitura crua vai na frente."""
        assert gs1.codigos_para_buscar("0107891111111118") == [
            "0107891111111118",
            "07891111111118",
            "7891111111118",
        ]

    def test_leitura_vazia_nao_procura_nada(self):
        assert gs1.codigos_para_buscar("   ") == []
