from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuração central da aplicação. Tudo que muda entre ambientes
    (dev/staging/produção) vem daqui, lido de variáveis de ambiente ou
    de um arquivo .env na raiz do projeto. Nenhum outro lugar do código
    deve ler os.environ diretamente — sempre por aqui.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- aplicação -----------------------------------------------------
    app_name: str = "ELLOTEC ERP API"
    ambiente: str = "desenvolvimento"  # desenvolvimento | producao
    debug: bool = True

    # --- banco de dados --------------------------------------------------
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "fuse_erp"
    mysql_password: str = "fuse_erp_dev_2026"
    mysql_database: str = "fuse_erp"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{quote_plus(self.mysql_user)}:{quote_plus(self.mysql_password)}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    # --- autenticação / JWT ----------------------------------------------
    jwt_segredo: str = "troque-este-segredo-em-producao-com-uma-chave-aleatoria-forte"
    jwt_algoritmo: str = "HS256"
    jwt_access_token_minutos: int = 30
    jwt_refresh_token_dias: int = 30

    # --- fingerprint / dispositivo -----------------------------------------
    # tolerância: quantas vezes os headers podem variar discretamente
    # (ex: atualização de navegador) antes de exigir reautenticação,
    # mesmo com device_id batendo.
    fingerprint_tolerancia_anomalias: int = 3

    # --- CORS --------------------------------------------------------------
    cors_origens: list[str] = ["http://localhost:4200"]


@lru_cache
def obter_settings() -> Settings:
    return Settings()
