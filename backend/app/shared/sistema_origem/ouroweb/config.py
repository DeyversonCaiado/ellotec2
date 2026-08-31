"""
Configuração do banco do sistema de origem OUROWEB (SQL Server), lida do .env.

Segue exatamente o mesmo desenho do `gestcom/config.py`, e pela mesma razão:
`shared/*` não pode importar de `core/*` (ver ARCHITECTURE.md → "Regras de
import entre domínios"), então o pacote lê o próprio recorte do .env — mesmo
arquivo, mesmas variáveis, sem criar a dependência de volta.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class SqlServerSettings(BaseSettings):
    # Prefixo OUROWEB_SQLSERVER_ para não colidir com o GESTCOM, que usa
    # ELLOTEC_ORACLE_. Assim `host` lê OUROWEB_SQLSERVER_HOST.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="OUROWEB_SQLSERVER_",
    )

    host: str = ""
    porta: int = 1433
    user: str = ""
    password: str = ""
    # Vazio conecta no banco default do login (hoje `Ourobase`). Preencher só
    # é necessário se o login passar a cair em outro banco.
    database: str = ""

    # Teto de tempo de uma consulta de TELA. As tabelas do Bionexo têm dezenas
    # de milhões de linhas; sem teto, uma consulta mal filtrada seguraria o
    # worker do uvicorn indefinidamente.
    timeout_consulta_segundos: int = 60

    # Teto da EXPORTAÇÃO, que é outra ordem de grandeza: a tela lê 50 linhas e
    # a exportação lê o filtro inteiro. Medido com 65 mil linhas, a mesma
    # consulta levou de 18s a 51s conforme a carga do servidor de origem — com
    # o teto de 60s da tela, o CSV falhava de forma intermitente, que é o pior
    # tipo de falha.
    timeout_exportacao_segundos: int = 600

    @property
    def configurado(self) -> bool:
        """Sem host, usuário ou senha não há o que tentar — quem chama
        responde 503 em vez de deixar o driver falhar com mensagem obscura."""
        return bool(self.host and self.user and self.password)


@lru_cache
def obter_sqlserver_settings() -> SqlServerSettings:
    return SqlServerSettings()
