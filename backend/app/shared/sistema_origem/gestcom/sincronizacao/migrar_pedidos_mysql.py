"""
Migração ÚNICA (one-off) de todos os pedidos do Oracle
(fat_capapedido + fat_itempedido) para as tabelas `pedidos` e `pedido_itens`
do MySQL do ELLOTEC (banco `dashboard`, config lida de
C:\\projetos\\ellotec2\\backend\\.env).

Diferente de gestcom/sincronizacao/pedidos.py (que sincroniza via API HTTP,
incremental), este script:
  - Lê TODOS os pedidos do Oracle de uma vez (sem filtro de data),
    e todos os itens deles numa única query em massa (não uma por pedido).
  - Resolve cliente_id, empresa_id, vendedor_id, status_id e produto_id a
    partir das tabelas já migradas no MySQL (clientes, empresas, usuarios,
    pedido_status, produtos), casando pelo sistema_origem_id de cada uma.
    Pedido cuja referência (cliente/empresa/status) não existir no MySQL é
    pulado — precisa sincronizar esses cadastros antes. Item cujo produto
    não existir é descartado (o pedido segue com os demais itens).
  - `numero` recebe o número do pedido do Oracle (fat_capapedido.pedido),
    não um contador interno — evita a race condition de geração de número
    sequencial que existe na API quando os pedidos são criados em paralelo
    via HTTP.
  - `id` de cada pedido é resolvido ANTES do upsert (mapa carregado uma vez
    do MySQL + gerado localmente para os novos), então o insert de
    pedido_itens não depende de nenhum truque de "pegar o id que acabou de
    ser gerado" — tudo roda em lote de verdade (executemany), sem round
    trip extra por registro.
  - Escreve direto no MySQL via PyMySQL/SQLAlchemy (sem passar pela API),
    muito mais rápido que uma chamada HTTP por pedido para um volume desse
    tamanho (~245 mil pedidos).
  - É idempotente: upsert nos pedidos casando por (sistema_origem_id,
    empresa_id) — chave única na tabela. Itens usam upsert também, com id
    determinístico (uuid5 de pedido_id+produto_id+lote+endereco) em vez de
    delete+insert — pedido_itens não tem chave natural única, e um delete
    quebraria a FK de expedicao_conferencia_itens.pedido_item_id quando o
    item já foi referenciado por conferência/separação de estoque.
  - Cada LOTE é sua própria transação (commit por lote, não uma transação
    só pra migração inteira) — um blip de rede na volta 200 mil não pode
    fazer rollback dos 199 mil já gravados com sucesso antes dele. Falha
    de conexão num lote tenta de novo (TENTATIVAS_POR_LOTE) antes de
    desistir; reexecutar o script depois de uma falha é seguro (upsert).
  - Não apaga nenhum pedido/item que não esteja no lote atual.

Uso:
    cd C:\\projetos\\ello
    python ellotec\\cadastros\\migrar_pedidos_mysql.py
"""
import os
import sys
import time
import uuid
import traceback
from collections import defaultdict

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
from sqlalchemy.exc import OperationalError  # noqa: E402

from core.log import get_logger  # noqa: E402
from core.db import get_db_connection  # noqa: E402

logger = get_logger("migrar_pedidos_mysql")

TAMANHO_LOTE = 1000
TENTATIVAS_POR_LOTE = 5


# =========================================================
# QUERIES ORACLE (em massa — nada de N+1 por pedido)
# =========================================================

QUERY_CABECALHOS = """
    SELECT
        cp.empresa_id AS empresa,
        cp.pedido,
        cp.DATA_PEDIDO,
        cp.LIBERACAO_DATA_HORA AS liberado_em,
        c.codigo_exp,
        c.cad_cgc,
        c.razao_social || ' - ' || c.codigo_exp as razao_social,
        CASE
            WHEN CP.Status = 'OK' AND EXISTS (
                SELECT 1 FROM FAT_MAPADECARGA_PEDIDO mcp
                WHERE mcp.empresa_id = cp.empresa_id
                  AND mcp.pedido = cp.pedido
            ) THEN 'EMB'
            WHEN CP.Status = 'OK' AND EXISTS (
                SELECT 1 FROM fat_itemnota fin
                WHERE fin.empresa_id = cp.empresa_id
                  AND fin.pedido = cp.pedido
            ) THEN 'FAT'
            ELSE CP.Status
        END AS status_oracle,
        cp.vendedor AS vendedor_sistema_origem_id
    FROM
        fat_capapedido cp
        INNER JOIN fat_cadastros c ON c.codigo_exp = cp.codigo_exp
        INNER JOIN EMPRESAS e ON e.EMPRESA_ID = cp.EMPRESA_ID
"""

QUERY_ITENS = """
    SELECT
        cp.empresa_id,
        cp.pedido,
        fi.codigo_pro,
        fp.NOME_PRODUTO || ' - ' || fi.codigo_pro AS produto,
        fi.QUANTIDADE,
        fi.PRECO AS preco_unitario,
        fi.lote,
        NVL(
            (
                SELECT E.ENDERECO
                FROM FAT_ITEMPEDIDOENDERECO EL
                JOIN FAT_ENDERECO_ESTOQUE E
                  ON E.EMPRESA_ID = EL.EMPRESA_ID
                 AND E.ENDERECO_ID = EL.ENDERECO_ID
                WHERE EL.EMPRESA_ID = fi.EMPRESA_ID
                  AND EL.PEDIDO     = fi.PEDIDO
                  AND EL.CODIGO_PRO = fi.CODIGO_PRO
                  AND EL.LOTE       = fi.LOTE
                  AND ROWNUM = 1
            ),
            'N ENDERECADO'
        ) AS endereco
    FROM
        fat_capapedido cp
        INNER JOIN FAT_ITEMPEDIDO fi ON fi.pedido = cp.PEDIDO
            AND fi.EMPRESA_ID = cp.empresa_id
        LEFT JOIN FAT_PRODUTOS fp ON fp.codigo_pro = fi.CODIGO_PRO
    WHERE
        fi.codigo_pro IS NOT NULL
"""


def buscar_cabecalhos_oracle():
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'")
        cursor.execute(QUERY_CABECALHOS)
        columns = [col[0].lower() for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        connection.close()


def buscar_itens_oracle():
    """Retorna um dict {(empresa, pedido): [itens]} com todos os itens de
    todos os pedidos, buscados numa única query."""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'")
        cursor.execute(QUERY_ITENS)
        columns = [col[0].lower() for col in cursor.description]
        itens_por_pedido = defaultdict(list)
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            itens_por_pedido[(item["empresa_id"], item["pedido"])].append(item)
        return itens_por_pedido
    finally:
        cursor.close()
        connection.close()


# =========================================================
# MAPAS DE RESOLUÇÃO (MySQL já migrado)
# =========================================================

def carregar_mapa_por_origem(mysql_engine, tabela):
    with mysql_engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT sistema_origem_id, id FROM {tabela} WHERE sistema_origem_id IS NOT NULL")
        ).fetchall()
    return {sistema_origem_id: id_ for sistema_origem_id, id_ in rows}


def carregar_pedidos_existentes(mysql_engine):
    """Mapa (sistema_origem_id, empresa_id) -> id dos pedidos já migrados,
    pra reaproveitar o id em vez de gerar um novo a cada execução."""
    with mysql_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT sistema_origem_id, empresa_id, id FROM pedidos WHERE sistema_origem_id IS NOT NULL")
        ).fetchall()
    return {(sistema_origem_id, empresa_id): id_ for sistema_origem_id, empresa_id, id_ in rows}


# =========================================================
# UPSERT (em lote, sem round trip por registro)
# =========================================================

UPSERT_PEDIDO_SQL = text("""
    INSERT INTO pedidos
        (id, numero, cliente_id, cliente_nome_fantasia, cliente_cnpj, observacoes,
         sistema_origem_id, empresa_id, status_id, data_pedido, vendedor_id, liberado_em,
         sync_created_at, sync_updated_at, sync_version)
    VALUES
        (:id, :numero, :cliente_id, :cliente_nome_fantasia, :cliente_cnpj, '',
         :sistema_origem_id, :empresa_id, :status_id, :data_pedido, :vendedor_id, :liberado_em,
         NOW(), NOW(), 1)
    ON DUPLICATE KEY UPDATE
        numero = VALUES(numero),
        cliente_id = VALUES(cliente_id),
        cliente_nome_fantasia = VALUES(cliente_nome_fantasia),
        cliente_cnpj = VALUES(cliente_cnpj),
        status_id = VALUES(status_id),
        data_pedido = VALUES(data_pedido),
        vendedor_id = VALUES(vendedor_id),
        liberado_em = VALUES(liberado_em),
        sync_updated_at = NOW(),
        sync_version = sync_version + 1
""")

# Upsert, não delete+insert: um item de pedido pode já estar referenciado
# por outras tabelas (ex: expedicao_conferencia_itens.pedido_item_id), e um
# DELETE nele quebra essa FK. O id de cada item é determinístico (uuid5 de
# pedido_id+produto_id+lote+endereco — ver montar_item_linha), então rodar
# de novo bate no mesmo id e atualiza em vez de duplicar.
UPSERT_ITEM_SQL = text("""
    INSERT INTO pedido_itens
        (id, pedido_id, produto_id, produto_codigo, produto_descricao, quantidade,
         preco_unitario, endereco_produto, lote,
         sync_created_at, sync_updated_at, sync_version)
    VALUES
        (:id, :pedido_id, :produto_id, :produto_codigo, :produto_descricao, :quantidade,
         :preco_unitario, :endereco_produto, :lote,
         NOW(), NOW(), 1)
    ON DUPLICATE KEY UPDATE
        produto_codigo = VALUES(produto_codigo),
        produto_descricao = VALUES(produto_descricao),
        quantidade = VALUES(quantidade),
        preco_unitario = VALUES(preco_unitario),
        endereco_produto = VALUES(endereco_produto),
        sync_updated_at = NOW(),
        sync_version = sync_version + 1
""")


def enviar_lote(mysql_engine, lote_pedidos, itens_por_pedido_id):
    """Grava um lote numa transação PRÓPRIA (não a migração toda numa
    transação só) — um blip de rede no meio de 245 mil registros não pode
    fazer rollback do que já foi processado com sucesso antes dele.
    Reexecutar esta função depois de uma falha é seguro: upsert em pedidos
    e pedido_itens, então repetir um lote não duplica nada."""
    if not lote_pedidos:
        return

    pedido_ids = [p["id"] for p in lote_pedidos]
    itens_para_inserir = []
    for pedido_id in pedido_ids:
        itens_para_inserir.extend(itens_por_pedido_id.get(pedido_id, []))

    for tentativa in range(1, TENTATIVAS_POR_LOTE + 1):
        try:
            with mysql_engine.begin() as mysql_conn:
                mysql_conn.execute(UPSERT_PEDIDO_SQL, lote_pedidos)
                if itens_para_inserir:
                    mysql_conn.execute(UPSERT_ITEM_SQL, itens_para_inserir)
            return
        except OperationalError as e:
            if tentativa == TENTATIVAS_POR_LOTE:
                raise
            espera = 2 * tentativa
            logger.warning(
                f"Falha de conexão ao gravar lote (tentativa {tentativa}/{TENTATIVAS_POR_LOTE}): {e}. "
                f"Tentando de novo em {espera}s..."
            )
            time.sleep(espera)


def migrar():
    settings = obter_settings()
    logger.info(f"Destino MySQL: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    mysql_engine = create_engine(settings.database_url, pool_pre_ping=True)

    logger.info("Carregando mapas de resolução (clientes, empresas, usuarios, produtos, status, pedidos existentes)...")
    clientes_por_origem = carregar_mapa_por_origem(mysql_engine, "clientes")
    empresas_por_origem = carregar_mapa_por_origem(mysql_engine, "empresas")
    usuarios_por_origem = carregar_mapa_por_origem(mysql_engine, "usuarios")
    produtos_por_origem = carregar_mapa_por_origem(mysql_engine, "produtos")
    status_por_origem = carregar_mapa_por_origem(mysql_engine, "pedido_status")
    pedidos_existentes = carregar_pedidos_existentes(mysql_engine)
    logger.info(
        f"{len(clientes_por_origem)} clientes, {len(empresas_por_origem)} empresas, "
        f"{len(usuarios_por_origem)} usuarios, {len(produtos_por_origem)} produtos, "
        f"{len(status_por_origem)} status, {len(pedidos_existentes)} pedidos já migrados."
    )

    logger.info("Buscando cabeçalhos de pedidos no Oracle...")
    cabecalhos = buscar_cabecalhos_oracle()
    logger.info(f"{len(cabecalhos)} pedidos encontrados.")

    logger.info("Buscando itens de todos os pedidos no Oracle (query única)...")
    itens_por_pedido_oracle = buscar_itens_oracle()
    logger.info(f"Itens carregados para {len(itens_por_pedido_oracle)} pedidos distintos.")

    migrados = 0
    pulados_sem_cliente = []
    pulados_sem_empresa = []
    pulados_sem_status = []
    pulados_sem_itens = []

    lote_pedidos = []
    itens_por_pedido_id = {}

    for idx, row in enumerate(cabecalhos, start=1):
        empresa_origem = str(row["empresa"])
        pedido_numero = str(row["pedido"])
        codigo_exp = str(row["codigo_exp"]) if row["codigo_exp"] is not None else None

        empresa_id = empresas_por_origem.get(empresa_origem)
        if not empresa_id:
            pulados_sem_empresa.append((empresa_origem, pedido_numero))
            continue

        cliente_id = clientes_por_origem.get(codigo_exp)
        if not cliente_id:
            pulados_sem_cliente.append((empresa_origem, pedido_numero, codigo_exp))
            continue

        status_oracle = str(row["status_oracle"]).strip() if row["status_oracle"] else None
        status_id = status_por_origem.get(status_oracle) if status_oracle else None
        if not status_id:
            pulados_sem_status.append((empresa_origem, pedido_numero, status_oracle))
            continue

        vendedor_origem = row["vendedor_sistema_origem_id"]
        vendedor_id = usuarios_por_origem.get(str(vendedor_origem).strip()) if vendedor_origem else None

        chave_existente = (pedido_numero, empresa_id)
        pedido_id = pedidos_existentes.get(chave_existente) or str(uuid.uuid4())

        itens_brutos = itens_por_pedido_oracle.get((row["empresa"], row["pedido"]), [])
        itens_linha = []
        for item_row in itens_brutos:
            produto_id = produtos_por_origem.get(str(item_row["codigo_pro"]))
            if not produto_id:
                continue
            lote = str(item_row["lote"]).strip()[:100] if item_row["lote"] else None
            endereco = str(item_row["endereco"]).strip()[:100] if item_row["endereco"] else None
            # id determinístico: rodar a migração de novo bate no mesmo id
            # (upsert) em vez de duplicar ou colidir com um delete que
            # quebraria FKs de outras tabelas apontando pro item.
            item_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"pedido_item:{pedido_id}:{produto_id}:{lote}:{endereco}"))
            itens_linha.append({
                "id": item_id,
                "pedido_id": pedido_id,
                "produto_id": produto_id,
                "produto_codigo": str(item_row["codigo_pro"])[:40],
                "produto_descricao": (str(item_row["produto"]).strip() if item_row["produto"] else "")[:255],
                "quantidade": int(item_row["quantidade"]) if item_row["quantidade"] is not None else 0,
                "preco_unitario": float(item_row["preco_unitario"]) if item_row["preco_unitario"] is not None else 0.0,
                "endereco_produto": endereco,
                "lote": lote,
            })

        if not itens_linha:
            pulados_sem_itens.append((empresa_origem, pedido_numero))
            continue

        pedidos_existentes[chave_existente] = pedido_id

        lote_pedidos.append({
            "id": pedido_id,
            "numero": pedido_numero[:20],
            "cliente_id": cliente_id,
            "cliente_nome_fantasia": (str(row["razao_social"]).strip() if row["razao_social"] else "")[:150],
            "cliente_cnpj": (str(row["cad_cgc"]).strip() if row["cad_cgc"] else "")[:18],
            "sistema_origem_id": pedido_numero[:100],
            "empresa_id": empresa_id,
            "status_id": status_id,
            "data_pedido": row["data_pedido"].date(),
            "vendedor_id": vendedor_id,
            "liberado_em": row["liberado_em"],
        })
        itens_por_pedido_id[pedido_id] = itens_linha

        if len(lote_pedidos) >= TAMANHO_LOTE:
            enviar_lote(mysql_engine, lote_pedidos, itens_por_pedido_id)
            migrados += len(lote_pedidos)
            logger.info(f"[{idx}/{len(cabecalhos)}] {migrados} pedidos migrados até agora...")
            lote_pedidos = []
            itens_por_pedido_id = {}

    enviar_lote(mysql_engine, lote_pedidos, itens_por_pedido_id)
    migrados += len(lote_pedidos)

    logger.info(f"Migração concluída. {migrados} pedidos migrados/atualizados com sucesso.")
    logger.info(f"{len(pulados_sem_cliente)} pulados por cliente não encontrado no MySQL.")
    logger.info(f"{len(pulados_sem_empresa)} pulados por empresa não encontrada no MySQL.")
    logger.info(f"{len(pulados_sem_status)} pulados por status não encontrado no MySQL.")
    logger.info(f"{len(pulados_sem_itens)} pulados por não ter nenhum item com produto reconhecido.")

    if pulados_sem_cliente:
        logger.warning(f"Exemplos sem cliente: {pulados_sem_cliente[:20]}")
    if pulados_sem_empresa:
        logger.warning(f"Exemplos sem empresa: {pulados_sem_empresa[:20]}")
    if pulados_sem_status:
        logger.warning(f"Exemplos sem status: {pulados_sem_status[:20]}")
    if pulados_sem_itens:
        logger.warning(f"Exemplos sem itens: {pulados_sem_itens[:20]}")


if __name__ == "__main__":
    try:
        migrar()
    except Exception:
        print(traceback.format_exc())
        logger.error(traceback.format_exc())
