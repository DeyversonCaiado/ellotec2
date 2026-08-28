"""
Migração ÚNICA (one-off) de todas as empresas do Oracle (gestcom.empresas)
para a tabela `empresas` do MySQL do ELLOTEC (banco `dashboard`, config
lida de C:\\projetos\\ellotec2\\backend\\.env).

Não é uma sincronização incremental (não existe job pra isso, foi pedido
só o envio direto dos dados). Envia somente os campos que existem na
tabela `empresas` do MySQL:
  - EMPRESA_ID (Oracle)     -> cnpj
  - NUMERO_EMPRESA (Oracle) -> codigo (e também sistema_origem_id, pra
    idempotência: rodar de novo atualiza em vez de duplicar)
  - RAZAO_SOCIAL            -> razao_social
  - NOME_FANTASIA           -> nome_fantasia
  - INATIVA ('S'/'N')       -> ativo

Uso:
    cd C:\\projetos\\ello
    python ellotec\\cadastros\\migrar_empresas_mysql.py
"""
import os
import sys
import uuid
import traceback

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

ELLOTEC2_BACKEND_DIR = r"C:\projetos\ellotec2\backend"
if ELLOTEC2_BACKEND_DIR not in sys.path:
    sys.path.insert(0, ELLOTEC2_BACKEND_DIR)

from app.core.settings import Settings  # noqa: E402

# Settings() só lê o .env relativo ao cwd NO MOMENTO da instanciação (não
# na importação), então não dá pra confiar em obter_settings() (que tem
# @lru_cache e pode rodar com o cwd de quem importou este módulo).
# Apontamos o caminho do .env explicitamente para não depender de cwd.
_ENV_FILE = os.path.join(ELLOTEC2_BACKEND_DIR, ".env")


def obter_settings():
    return Settings(_env_file=_ENV_FILE)


from sqlalchemy import create_engine, text  # noqa: E402

from core.log import get_logger  # noqa: E402
from core.db import get_db_connection  # noqa: E402

logger = get_logger("migrar_empresas_mysql")


def buscar_empresas_oracle():
    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        SELECT
            e.EMPRESA_ID AS cnpj,
            e.NUMERO_EMPRESA AS codigo,
            e.RAZAO_SOCIAL AS razao_social,
            e.NOME_FANTASIA AS nome_fantasia,
            CASE
                WHEN e.INATIVA = 'S' THEN
                    0
                ELSE
                    1
            END AS ativo
        FROM
            gestcom.empresas e
        ORDER BY
            e.NUMERO_EMPRESA
    """

    try:
        cursor.execute(query)
        columns = [col[0].lower() for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        connection.close()


UPSERT_SQL = text("""
    INSERT INTO empresas
        (id, codigo, razao_social, nome_fantasia, cnpj, sistema_origem_id, ativo,
         sync_created_at, sync_updated_at, sync_version)
    VALUES
        (:id, :codigo, :razao_social, :nome_fantasia, :cnpj, :sistema_origem_id, :ativo,
         NOW(), NOW(), 1)
    ON DUPLICATE KEY UPDATE
        codigo = VALUES(codigo),
        razao_social = VALUES(razao_social),
        nome_fantasia = VALUES(nome_fantasia),
        cnpj = VALUES(cnpj),
        ativo = VALUES(ativo),
        sync_updated_at = NOW(),
        sync_version = sync_version + 1
""")


def migrar():
    settings = obter_settings()
    logger.info(
        f"Destino MySQL: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    )
    mysql_engine = create_engine(settings.database_url)

    logger.info("Buscando todas as empresas no Oracle...")
    rows = buscar_empresas_oracle()
    logger.info(f"{len(rows)} empresas encontradas no Oracle.")

    migrados = 0
    invalidas = []

    lote = []
    for row in rows:
        codigo = (row["codigo"] or "").strip()
        cnpj = (row["cnpj"] or "").strip()
        razao_social = (row["razao_social"] or "").strip()
        nome_fantasia = (row["nome_fantasia"] or razao_social).strip()

        if not codigo or not cnpj or not razao_social:
            invalidas.append(row)
            continue

        lote.append({
            "id": str(uuid.uuid4()),
            "codigo": codigo[:10],
            "razao_social": razao_social[:200],
            "nome_fantasia": nome_fantasia[:150],
            "cnpj": cnpj[:18],
            "sistema_origem_id": codigo[:100],
            "ativo": bool(row["ativo"]),
        })

    with mysql_engine.begin() as mysql_conn:
        if lote:
            mysql_conn.execute(UPSERT_SQL, lote)
        migrados = len(lote)

    logger.info(f"Migração concluída. {migrados} empresas migradas/atualizadas com sucesso.")
    logger.info(f"{len(invalidas)} com dados inválidos (sem código/cnpj/razão social) — puladas.")

    if invalidas:
        logger.warning(f"Exemplos pulados: {invalidas[:20]}")


if __name__ == "__main__":
    try:
        migrar()
    except Exception:
        print(traceback.format_exc())
        logger.error(traceback.format_exc())
