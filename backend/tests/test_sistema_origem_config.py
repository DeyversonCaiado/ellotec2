"""
Descoberta do Oracle Instant Client por sistema operacional.

Este arquivo existe por causa de um incidente: o `.env` de produção (Linux)
tinha o caminho Windows do Instant Client, copiado do `.env.example`, e a
sincronização morria com `DPI-1047: Cannot locate a 64-bit Oracle Client
library` — o driver procurava `libclntsh.so` dentro de `C:/oracle/`.

A regra que ficou: o caminho é descoberto pelo sistema operacional, e o `.env`
é só a saída para instalação fora do lugar de sempre.
"""

import pytest

from app.shared.sistema_origem.gestcom import config
from app.shared.sistema_origem.gestcom.config import (
    OracleSettings,
    diretorio_padrao_do_client,
)


def _settings(**campos) -> OracleSettings:
    """Settings montado no teste, sem ler o .env da máquina — senão o resultado
    mudaria conforme quem roda a suíte."""
    base = dict(
        oracle_user="consulta",
        oracle_password="x",
        oracle_dsn="servidor:1521/ORCL",
        oracle_client_dir="",
        _env_file=None,
    )
    base.update(campos)
    return OracleSettings(**base)


class TestDiretorioPadraoPorSistema:
    @pytest.mark.parametrize(
        "sistema, esperado",
        [
            ("Linux", "/opt/oracle/instantclient_12_2"),
            ("Windows", r"C:\oracle\instantclient_19_28"),
            ("Darwin", "/opt/oracle/instantclient"),
        ],
    )
    def test_cada_sistema_tem_o_seu_caminho(self, monkeypatch, sistema, esperado):
        """Os caminhos NÃO são iguais entre si: no Linux o Instant Client
        instalado é o 12_2, no Windows o 19_28."""
        monkeypatch.setattr(config.platform, "system", lambda: sistema)
        assert diretorio_padrao_do_client() == esperado

    def test_sistema_desconhecido_devolve_vazio(self, monkeypatch):
        """Vazio em vez de um chute: quem chama já sabe reclamar de diretório
        vazio com uma mensagem que aponta para o .env, e inventar um caminho só
        trocaria um erro claro por um DPI-1047."""
        monkeypatch.setattr(config.platform, "system", lambda: "FreeBSD")
        assert diretorio_padrao_do_client() == ""

    def test_a_deteccao_nao_depende_de_maiuscula(self, monkeypatch):
        """`platform.system()` devolve 'Linux' com maiúscula — comparar sem
        normalizar faria a detecção falhar em todo sistema."""
        monkeypatch.setattr(config.platform, "system", lambda: "LINUX")
        assert diretorio_padrao_do_client() == "/opt/oracle/instantclient_12_2"


class TestClientDirEfetivo:
    def test_sem_env_usa_o_padrao_do_sistema(self, monkeypatch):
        """O caso normal, e o que corrige o incidente: o mesmo .env funciona no
        Windows do desenvolvedor e no Linux do servidor."""
        monkeypatch.setattr(config.platform, "system", lambda: "Linux")
        assert _settings().client_dir_efetivo == "/opt/oracle/instantclient_12_2"

    def test_o_env_vence_quando_preenchido(self, monkeypatch):
        """A saída para uma instalação fora do lugar de sempre. Explícito vence
        implícito — se o valor estiver errado, o erro tem que aparecer, não ser
        silenciosamente corrigido."""
        monkeypatch.setattr(config.platform, "system", lambda: "Linux")
        efetivo = _settings(oracle_client_dir="/srv/oracle/ic").client_dir_efetivo
        assert efetivo == "/srv/oracle/ic"

    def test_configurado_nao_exige_mais_o_caminho_no_env(self, monkeypatch):
        """`configurado` olha o caminho EFETIVO. Antes exigia o campo do .env, e
        com o padrão por sistema o campo vazio passou a ser o caso normal — sem
        esta mudança o domínio se declararia 'não configurado' justamente na
        configuração recomendada."""
        monkeypatch.setattr(config.platform, "system", lambda: "Linux")
        assert _settings().configurado is True

    def test_sistema_sem_padrao_e_sem_env_nao_esta_configurado(self, monkeypatch):
        monkeypatch.setattr(config.platform, "system", lambda: "FreeBSD")
        assert _settings().configurado is False
