"""
Cria a tabela `cotacao_tabela_cmed` no MySQL do ELLOTEC (banco `dashboard`,
config lida de C:\\projetos\\ellotec2\\backend\\.env), com as colunas do
arquivo xls_conformidade_gov_20260811_192510234.xlsx (Lista de Preços CMED).

Uso:
    cd C:\\projetos\\ello
    python ellotec\\cadastros\\criar_tabela_cotacao_cmed.py
"""
import os
import sys
import traceback

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

ELLOTEC2_BACKEND_DIR = r"C:\projetos\ellotec2\backend"
if ELLOTEC2_BACKEND_DIR not in sys.path:
    sys.path.insert(0, ELLOTEC2_BACKEND_DIR)

from app.core.settings import Settings  # noqa: E402

_ENV_FILE = os.path.join(ELLOTEC2_BACKEND_DIR, ".env")


def obter_settings():
    return Settings(_env_file=_ENV_FILE)


from sqlalchemy import create_engine, text  # noqa: E402

from core.log import get_logger  # noqa: E402

logger = get_logger("criar_tabela_cotacao_cmed")


CREATE_TABLE_SQL = text("""
    CREATE TABLE IF NOT EXISTS cotacao_tabela_cmed (
        id INT AUTO_INCREMENT PRIMARY KEY,
        substancia VARCHAR(500),
        cnpj VARCHAR(20),
        laboratorio VARCHAR(255),
        codigo_ggrem VARCHAR(20),
        registro VARCHAR(30),
        ean_1 VARCHAR(20),
        ean_2 VARCHAR(20),
        ean_3 VARCHAR(20),
        produto VARCHAR(255),
        apresentacao VARCHAR(500),
        classe_terapeutica VARCHAR(255),
        tipo_de_produto VARCHAR(100),
        regime_de_preco VARCHAR(100),
        pf_sem_impostos DECIMAL(15,4),
        pf_0 DECIMAL(15,4),
        pf_12 DECIMAL(15,4),
        pf_12_alc DECIMAL(15,4),
        pf_17 DECIMAL(15,4),
        pf_17_alc DECIMAL(15,4),
        pf_17_5 DECIMAL(15,4),
        pf_17_5_alc DECIMAL(15,4),
        pf_18 DECIMAL(15,4),
        pf_18_alc DECIMAL(15,4),
        pf_19 DECIMAL(15,4),
        pf_19_alc DECIMAL(15,4),
        pf_19_5 DECIMAL(15,4),
        pf_19_5_alc DECIMAL(15,4),
        pf_20 DECIMAL(15,4),
        pf_20_alc DECIMAL(15,4),
        pf_20_5 DECIMAL(15,4),
        pf_20_5_alc DECIMAL(15,4),
        pf_21 DECIMAL(15,4),
        pf_21_alc DECIMAL(15,4),
        pf_22 DECIMAL(15,4),
        pf_22_alc DECIMAL(15,4),
        pf_22_5 DECIMAL(15,4),
        pf_22_5_alc DECIMAL(15,4),
        pf_23 DECIMAL(15,4),
        pf_23_alc DECIMAL(15,4),
        pmvg_sem_impostos DECIMAL(15,4),
        pmvg_0 DECIMAL(15,4),
        pmvg_12 DECIMAL(15,4),
        pmvg_12_alc DECIMAL(15,4),
        pmvg_17 DECIMAL(15,4),
        pmvg_17_alc DECIMAL(15,4),
        pmvg_17_5 DECIMAL(15,4),
        pmvg_17_5_alc DECIMAL(15,4),
        pmvg_18 DECIMAL(15,4),
        pmvg_18_alc DECIMAL(15,4),
        pmvg_19 DECIMAL(15,4),
        pmvg_19_alc DECIMAL(15,4),
        pmvg_19_5 DECIMAL(15,4),
        pmvg_19_5_alc DECIMAL(15,4),
        pmvg_20 DECIMAL(15,4),
        pmvg_20_alc DECIMAL(15,4),
        pmvg_20_5 DECIMAL(15,4),
        pmvg_20_5_alc DECIMAL(15,4),
        pmvg_21 DECIMAL(15,4),
        pmvg_21_alc DECIMAL(15,4),
        pmvg_22 DECIMAL(15,4),
        pmvg_22_alc DECIMAL(15,4),
        pmvg_22_5 DECIMAL(15,4),
        pmvg_22_5_alc DECIMAL(15,4),
        pmvg_23 DECIMAL(15,4),
        pmvg_23_alc DECIMAL(15,4),
        restricao_hospitalar VARCHAR(20),
        cap VARCHAR(20),
        confaz_87 VARCHAR(20),
        icms_0 VARCHAR(20),
        analise_recursal VARCHAR(100),
        lista_concessao_credito_tributario VARCHAR(100),
        comercializacao_2025 VARCHAR(50),
        tarja VARCHAR(50),
        destinacao_comercial_9 VARCHAR(100),
        data_arquivo VARCHAR(8) NOT NULL DEFAULT '20260811'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""")


def criar_tabela():
    settings = obter_settings()
    logger.info(
        f"Destino MySQL: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    )
    mysql_engine = create_engine(settings.database_url)

    with mysql_engine.begin() as conn:
        conn.execute(CREATE_TABLE_SQL)

    logger.info("Tabela cotacao_tabela_cmed criada (ou já existente) com sucesso.")


if __name__ == "__main__":
    try:
        criar_tabela()
    except Exception:
        print(traceback.format_exc())
        logger.error(traceback.format_exc())
