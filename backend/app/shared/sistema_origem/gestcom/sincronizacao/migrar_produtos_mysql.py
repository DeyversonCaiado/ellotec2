"""
Migração ÚNICA (one-off) de todos os produtos do Oracle (fat_produtos) para
a tabela `produtos` do MySQL do ELLOTEC (banco `dashboard`, config lida de
C:\\projetos\\ellotec2\\backend\\.env).

Diferente de gestcom/sincronizacao/produtos.py (que sincroniza via API HTTP,
incremental), este script:
  - Lê TODOS os produtos do Oracle de uma vez (sem filtro de data), já
    trazendo o MARCA_ID (Oracle) de cada um via join com fat_marcas.
  - Resolve marca_id (MySQL) a partir do MARCA_ID (Oracle) usando a
    tabela `marcas` já migrada (marcas.sistema_origem_id) — produto sem
    marca correspondente no MySQL é pulado, pois marca_id é obrigatório.
  - Escreve direto no MySQL via SQLAlchemy (sem passar pela API), bem
    mais rápido para uma carga inicial.
  - É idempotente: usa INSERT ... ON DUPLICATE KEY UPDATE casando pelo
    `sistema_origem_id` (chave única na tabela). Rodar de novo atualiza
    os registros já migrados em vez de duplicar.
  - Não apaga nada em nenhum dos dois bancos.

Uso:
    cd C:\\projetos\\ello
    python ellotec\\cadastros\\migrar_produtos_mysql.py
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

logger = get_logger("migrar_produtos_mysql")


def buscar_produtos_oracle():
    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        SELECT
            fp.codigo_pro AS codigo,
            fp.NOME_PRODUTO AS descricao,
            fp.unidade,
            fp.REGISTRO_MS AS registro_anvisa,
            CASE
                WHEN suspenso='N' THEN
                    1
                ELSE
                    0
            END AS ativo,
            fm.MARCA_ID AS marca_sistema_origem_id
        FROM
            fat_produtos fp
            LEFT JOIN FAT_MARCAS fm ON fm.MARCA_ID = fp.MARCA_ID
        ORDER BY
            fp.codigo_pro
    """

    try:
        cursor.execute(query)
        columns = [col[0].lower() for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        connection.close()


def carregar_marcas(mysql_engine):
    """Monta o mapa sistema_origem_id (MARCA_ID no Oracle) -> id da marca no MySQL."""
    with mysql_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, sistema_origem_id FROM marcas WHERE sistema_origem_id IS NOT NULL")
        ).fetchall()
    return {sistema_origem_id: marca_id for marca_id, sistema_origem_id in rows}


UPSERT_SQL = text("""
    INSERT INTO produtos
        (id, codigo, descricao, unidade, registro_anvisa, ativo, marca_id, sistema_origem_id,
         sync_created_at, sync_updated_at, sync_version)
    VALUES
        (:id, :codigo, :descricao, :unidade, :registro_anvisa, :ativo, :marca_id, :sistema_origem_id,
         NOW(), NOW(), 1)
    ON DUPLICATE KEY UPDATE
        codigo = VALUES(codigo),
        descricao = VALUES(descricao),
        unidade = VALUES(unidade),
        registro_anvisa = VALUES(registro_anvisa),
        ativo = VALUES(ativo),
        marca_id = VALUES(marca_id),
        sync_updated_at = NOW(),
        sync_version = sync_version + 1
""")


def migrar():
    settings = obter_settings()
    logger.info(
        f"Destino MySQL: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    )
    mysql_engine = create_engine(settings.database_url)

    marcas_por_origem_id = carregar_marcas(mysql_engine)
    logger.info(f"{len(marcas_por_origem_id)} marcas carregadas do MySQL para resolução de marca_id.")

    logger.info("Buscando todos os produtos no Oracle...")
    rows = buscar_produtos_oracle()
    logger.info(f"{len(rows)} produtos encontrados no Oracle.")

    migrados = 0
    sem_codigo = []
    sem_marca = []

    lote = []
    TAMANHO_LOTE = 500

    def enviar_lote(mysql_conn, lote_atual):
        if not lote_atual:
            return
        mysql_conn.execute(UPSERT_SQL, lote_atual)

    with mysql_engine.begin() as mysql_conn:
        for idx, row in enumerate(rows, start=1):
            codigo = row["codigo"]
            if codigo is None:
                sem_codigo.append(row)
                continue
            codigo = str(codigo)

            marca_sistema_origem_id = row["marca_sistema_origem_id"]
            marca_sistema_origem_id = str(marca_sistema_origem_id) if marca_sistema_origem_id is not None else None
            marca_id = marcas_por_origem_id.get(marca_sistema_origem_id) if marca_sistema_origem_id else None
            if not marca_id:
                sem_marca.append((codigo, marca_sistema_origem_id))
                continue

            descricao = (row["descricao"] or "").strip()
            if len(descricao) < 3:
                sem_marca.append((codigo, "descrição inválida"))
                continue

            registro_anvisa = str(row["registro_anvisa"]).strip() if row["registro_anvisa"] is not None else None
            registro_anvisa = registro_anvisa or None

            lote.append({
                "id": str(uuid.uuid4()),
                "codigo": codigo[:40],
                "descricao": descricao[:255],
                "unidade": (row["unidade"] or "UN").strip()[:10] or "UN",
                "registro_anvisa": registro_anvisa[:30] if registro_anvisa else None,
                "ativo": bool(row["ativo"]),
                "marca_id": marca_id,
                "sistema_origem_id": codigo[:100],
            })

            if len(lote) >= TAMANHO_LOTE:
                enviar_lote(mysql_conn, lote)
                migrados += len(lote)
                logger.info(f"[{idx}/{len(rows)}] {migrados} produtos migrados até agora...")
                lote = []

        enviar_lote(mysql_conn, lote)
        migrados += len(lote)

    logger.info(f"Migração concluída. {migrados} produtos migrados/atualizados com sucesso.")
    logger.info(f"{len(sem_codigo)} sem código — pulados.")
    logger.info(f"{len(sem_marca)} sem marca correspondente ou com dados inválidos — pulados.")

    if sem_marca:
        logger.warning(f"Exemplos pulados: {sem_marca[:20]}")


if __name__ == "__main__":
    try:
        migrar()
    except Exception:
        print(traceback.format_exc())
        logger.error(traceback.format_exc())
