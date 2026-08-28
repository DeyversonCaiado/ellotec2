"""
Migração ÚNICA (one-off) de todos os clientes do Oracle (fat_cadastros)
para a tabela `clientes` do MySQL do ELLOTEC (banco `dashboard`, config
lida de C:\\projetos\\ellotec2\\backend\\.env).

Diferente de gestcom/sincronizacao/clientes.py (que sincroniza via API HTTP,
incremental, 10 em 10 segundos), este script:
  - Lê TODOS os clientes do Oracle de uma vez (sem filtro de data).
  - Escreve direto no MySQL via SQLAlchemy (sem passar pela API), bem
    mais rápido para uma carga inicial de ~36 mil registros.
  - É idempotente: usa INSERT ... ON DUPLICATE KEY UPDATE casando pelo
    `sistema_origem_id` (chave única na tabela). Rodar de novo atualiza
    os registros já migrados em vez de duplicar.
  - Não apaga nada em nenhum dos dois bancos.

Uso:
    cd C:\\projetos\\ello
    python ellotec\\cadastros\\migrar_clientes_mysql.py
"""
import os
import re
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

logger = get_logger("migrar_clientes_mysql")

PADRAO_CPF = re.compile(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$")
PADRAO_CNPJ = re.compile(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$")

# Códigos IBGE cadastrados errados em fat_cidades (Oracle), identificados
# na migração: o nome da cidade bate, mas o código não corresponde ao
# IBGE real. Corrigidos só aqui, na saída para o MySQL — o Oracle não é
# alterado. Chave = código errado como veio do Oracle, valor = código
# IBGE correto (conferido contra a tabela `cidades` do MySQL).
CORRECOES_CIDADE_IBGE = {
    1234769: 3162955,  # "São José da Lapa" (MG) — Oracle tinha código placeholder
    4303803: 4302808,  # "Caçapava do Sul" (RS) — Oracle tinha código trocado
}


def normalizar_cpf_cnpj(valor):
    """Reformata para 000.000.000-00 (CPF) ou 00.000.000/0000-00 (CNPJ)
    a partir dos dígitos, independente da pontuação original.
    Quando não dá pra reconhecer como CPF/CNPJ (nem 11 nem 14 dígitos),
    manda o valor bruto mesmo assim (só espaços nas pontas removidos) —
    a pedido explícito do usuário, sem validação de formato nesse caso."""
    if not valor:
        return None

    valor = valor.strip()
    if not valor:
        return None

    if PADRAO_CPF.match(valor) or PADRAO_CNPJ.match(valor):
        return valor

    digitos = re.sub(r"\D", "", valor)

    if len(digitos) == 11:
        return f"{digitos[0:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:11]}"
    if len(digitos) == 14:
        return f"{digitos[0:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:14]}"

    return valor[:18]


def carregar_cidades(mysql_engine):
    """Monta o mapa codigo_municipio (IBGE) -> id da cidade no MySQL."""
    with mysql_engine.connect() as conn:
        rows = conn.execute(text("SELECT id, codigo_municipio FROM cidades")).fetchall()
    return {codigo_municipio: cidade_id for cidade_id, codigo_municipio in rows}


def buscar_clientes_oracle():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'")

    query = """
        SELECT
            fc.codigo_exp AS codigo,
            fc.codigo_exp AS sistema_origem_id,
            fc.cad_cgc AS cpf_cnpj,
            fc.razao_social,
            fc.nome_fantazia AS nome_fantasia,
            fc.E_MAIL AS email,
            CASE
                WHEN ativo='N' THEN
                    0
                ELSE
                    1
            END AS ativo,
            fc.telefone,
            cid.codigo_municipio AS cidade_ibge,
            fc.celular,
            fc.endereco AS logradouro,
            'N/D' AS numero,
            fc.complemento_endereco AS complemento,
            fc.bairro,
            fc.cep
        FROM
            fat_cadastros fc
        LEFT JOIN fat_cidades cid ON cid.cidade = fc.cidade
        ORDER BY
            fc.codigo_exp
    """

    try:
        cursor.execute(query)
        columns = [col[0].lower() for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        connection.close()


UPSERT_SQL = text("""
    INSERT INTO clientes
        (id, codigo, razao_social, nome_fantasia, cpf_cnpj, email, telefone, celular,
         logradouro, numero, complemento, bairro, cep, sistema_origem_id, cidade_id, ativo,
         sync_created_at, sync_updated_at, sync_version)
    VALUES
        (:id, :codigo, :razao_social, :nome_fantasia, :cpf_cnpj, :email, :telefone, :celular,
         :logradouro, :numero, :complemento, :bairro, :cep, :sistema_origem_id, :cidade_id, :ativo,
         NOW(), NOW(), 1)
    ON DUPLICATE KEY UPDATE
        codigo = VALUES(codigo),
        razao_social = VALUES(razao_social),
        nome_fantasia = VALUES(nome_fantasia),
        cpf_cnpj = VALUES(cpf_cnpj),
        email = VALUES(email),
        telefone = VALUES(telefone),
        celular = VALUES(celular),
        logradouro = VALUES(logradouro),
        numero = VALUES(numero),
        complemento = VALUES(complemento),
        bairro = VALUES(bairro),
        cep = VALUES(cep),
        cidade_id = VALUES(cidade_id),
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

    cidades_por_ibge = carregar_cidades(mysql_engine)
    logger.info(f"{len(cidades_por_ibge)} cidades carregadas do MySQL para resolução de cidade_id.")

    logger.info("Buscando todos os clientes no Oracle...")
    rows = buscar_clientes_oracle()
    logger.info(f"{len(rows)} clientes encontrados no Oracle.")

    migrados = 0
    sem_cpf_cnpj_valido = []
    sem_cidade = []
    sem_sistema_origem_id = []
    erros = []

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

            cpf_cnpj = normalizar_cpf_cnpj(row["cpf_cnpj"])
            if not cpf_cnpj:
                sem_cpf_cnpj_valido.append((sistema_origem_id, row["cpf_cnpj"]))
                continue

            cidade_ibge = int(row["cidade_ibge"]) if row["cidade_ibge"] is not None else None
            cidade_ibge = CORRECOES_CIDADE_IBGE.get(cidade_ibge, cidade_ibge)
            cidade_id = cidades_por_ibge.get(cidade_ibge) if cidade_ibge is not None else None
            if not cidade_id:
                sem_cidade.append((sistema_origem_id, cidade_ibge))
                continue

            razao_social = (row["razao_social"] or "").strip()
            nome_fantasia = (row["nome_fantasia"] or razao_social).strip()
            if len(razao_social) < 3 or len(nome_fantasia) < 1:
                erros.append((sistema_origem_id, "razao_social/nome_fantasia inválidos"))
                continue

            lote.append({
                "id": str(uuid.uuid4()),
                "codigo": str(row["codigo"])[:10] if row["codigo"] is not None else None,
                "razao_social": razao_social[:200],
                "nome_fantasia": nome_fantasia[:150],
                "cpf_cnpj": cpf_cnpj,
                "email": (row["email"] or "").strip()[:255] or None,
                "telefone": (row["telefone"] or "").strip()[:30],
                "celular": (row["celular"] or "").strip()[:50] or None,
                "logradouro": (row["logradouro"] or "").strip()[:255] or None,
                "numero": (row["numero"] or "").strip()[:50] or None,
                "complemento": (row["complemento"] or "").strip()[:255] or None,
                "bairro": (row["bairro"] or "").strip()[:100] or None,
                "cep": (row["cep"] or "").strip()[:10] or None,
                "sistema_origem_id": sistema_origem_id[:100],
                "cidade_id": cidade_id,
                "ativo": bool(row["ativo"]),
            })

            if len(lote) >= TAMANHO_LOTE:
                enviar_lote(mysql_conn, lote)
                migrados += len(lote)
                logger.info(f"[{idx}/{len(rows)}] {migrados} clientes migrados até agora...")
                lote = []

        enviar_lote(mysql_conn, lote)
        migrados += len(lote)

    logger.info(f"Migração concluída. {migrados} clientes migrados/atualizados com sucesso.")
    logger.info(f"{len(sem_sistema_origem_id)} sem codigo_exp (sistema_origem_id) — pulados.")
    logger.info(f"{len(sem_cpf_cnpj_valido)} com CPF/CNPJ irrecuperável (não deu pra normalizar) — pulados.")
    logger.info(f"{len(sem_cidade)} com cidade IBGE não encontrada no MySQL — pulados.")
    logger.info(f"{len(erros)} com outros erros de validação — pulados.")

    if sem_cpf_cnpj_valido:
        logger.warning(f"Exemplos sem CPF/CNPJ válido: {sem_cpf_cnpj_valido[:20]}")
    if sem_cidade:
        logger.warning(f"Exemplos sem cidade: {sem_cidade[:20]}")
    if erros:
        logger.warning(f"Exemplos com outros erros: {erros[:20]}")


if __name__ == "__main__":
    try:
        migrar()
    except Exception:
        print(traceback.format_exc())
        logger.error(traceback.format_exc())
