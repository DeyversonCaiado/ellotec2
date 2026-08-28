"""
Migração ÚNICA (one-off) de todas as marcas do Oracle (fat_marcas) para a
tabela `marcas` do MySQL do ELLOTEC (banco `dashboard`, config lida de
C:\\projetos\\ellotec2\\backend\\.env).

Diferente de gestcom/sincronizacao/marcas.py (que sincroniza via API HTTP,
incremental), este script:
  - Lê TODAS as marcas do Oracle de uma vez (sem filtro de data).
  - Escreve direto no MySQL via SQLAlchemy (sem passar pela API), bem
    mais rápido para uma carga inicial.
  - É idempotente: usa INSERT ... ON DUPLICATE KEY UPDATE casando pelo
    `sistema_origem_id` (chave única na tabela). Rodar de novo atualiza
    os registros já migrados em vez de duplicar.
  - Não apaga nada em nenhum dos dois bancos.

Uso:
    cd C:\\projetos\\ello
    python ellotec\\cadastros\\migrar_marcas_mysql.py
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


from sqlalchemy import bindparam, create_engine, text  # noqa: E402

from core.log import get_logger  # noqa: E402
from core.db import get_db_connection  # noqa: E402

logger = get_logger("migrar_marcas_mysql")


def buscar_marcas_oracle():
    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        SELECT
            fm.NOME_MARCA AS nome,
            fm.MARCA_ID AS sistema_origem_id
        FROM
            fat_marcas fm
        ORDER BY
            fm.MARCA_ID
    """

    try:
        cursor.execute(query)
        columns = [col[0].lower() for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        connection.close()


UPSERT_SQL = text("""
    INSERT INTO marcas
        (id, nome, ativo, sistema_origem_id, sync_created_at, sync_updated_at, sync_version)
    VALUES
        (:id, :nome, :ativo, :sistema_origem_id, NOW(), NOW(), 1)
    ON DUPLICATE KEY UPDATE
        nome = VALUES(nome),
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

    logger.info("Buscando todas as marcas no Oracle...")
    rows = buscar_marcas_oracle()
    logger.info(f"{len(rows)} marcas encontradas no Oracle.")

    migrados = 0
    sem_sistema_origem_id = []
    sem_nome = []

    lote = []
    TAMANHO_LOTE = 500

    def enviar_lote(mysql_conn, lote_atual):
        if not lote_atual:
            return
        mysql_conn.execute(UPSERT_SQL, lote_atual)

    with mysql_engine.begin() as mysql_conn:
        for idx, row in enumerate(rows, start=1):
            sistema_origem_id = row["sistema_origem_id"]
            if sistema_origem_id is None:
                sem_sistema_origem_id.append(row)
                continue

            sistema_origem_id = str(sistema_origem_id)

            nome = (row["nome"] or "").strip()
            if not nome:
                sem_nome.append(sistema_origem_id)
                continue

            lote.append({
                "id": str(uuid.uuid4()),
                "nome": nome[:100],
                "ativo": True,
                "sistema_origem_id": sistema_origem_id[:100],
            })

            if len(lote) >= TAMANHO_LOTE:
                enviar_lote(mysql_conn, lote)
                migrados += len(lote)
                logger.info(f"[{idx}/{len(rows)}] {migrados} marcas migradas até agora...")
                lote = []

        enviar_lote(mysql_conn, lote)
        migrados += len(lote)

    logger.info(f"Migração concluída. {migrados} marcas migradas/atualizadas com sucesso.")
    logger.info(f"{len(sem_sistema_origem_id)} sem MARCA_ID (sistema_origem_id) — pulados.")
    logger.info(f"{len(sem_nome)} sem nome — pulados.")

    if sem_nome:
        logger.warning(f"Exemplos sem nome: {sem_nome[:20]}")


if __name__ == "__main__":
    try:
        migrar()
    except Exception:
        print(traceback.format_exc())
        logger.error(traceback.format_exc())
