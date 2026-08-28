import os
import time
import traceback
from datetime import datetime
import httpx

from app.shared.sistema_origem.core.log import get_logger
from app.shared.sistema_origem.gestcom.conexao import conectar
from app.shared.sistema_origem.core.api_client import requisitar_com_retry

logger = get_logger("produtos")

# pega o diretório onde está este arquivo .py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# monta o caminho absoluto do arquivo de controle no mesmo diretório
ARQUIVO_REGISTRO = os.path.join(BASE_DIR, "produtos_controle.txt")

# =========================================================
# CONFIGURAÇÕES DA API ELLOTEC
# =========================================================
BASE_URL = "http://localhost:8000"
DEVICE_ID = "3f1c2d2a-6b6e-4b61-9f2c-0d0f7b7d9a11"
LOGIN_USUARIO = "admin"
LOGIN_SENHA = "123456"

_TOKEN_ATUAL = None


# =========================================================
# CONTROLE DA ÚLTIMA DATA PROCESSADA
# =========================================================

def ler_ultima_data():
    """Lê a maior DATA_HORA_ALTERACAO salva no arquivo local.
    Retorna None se o arquivo não existir (primeira execução)."""
    if not os.path.exists(ARQUIVO_REGISTRO):
        return None

    with open(ARQUIVO_REGISTRO, "r") as f:
        valor = f.read().strip()

    if not valor:
        return None

    try:
        return datetime.strptime(valor, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        logger.warning(f"Data inválida no arquivo de controle: {valor}")
        return None


def salvar_ultima_data(data):
    """Salva a maior DATA_HORA_ALTERACAO processada com sucesso."""
    with open(ARQUIVO_REGISTRO, "w") as f:
        f.write(data.strftime("%Y-%m-%d %H:%M:%S"))


# =========================================================
# AUTENTICAÇÃO NA API
# =========================================================

def obter_token(forcar_renovacao=False):
    """Retorna o token JWT da API, fazendo login caso não tenha em cache
    (ou se `forcar_renovacao=True`, usado pelo retry em api_client
    quando a API responde 401 por token expirado)."""
    global _TOKEN_ATUAL

    if _TOKEN_ATUAL and not forcar_renovacao:
        return _TOKEN_ATUAL

    login_payload = {
        "usuario": LOGIN_USUARIO,
        "senha": LOGIN_SENHA,
    }

    headers = {
        "X-Device-Id": DEVICE_ID,
    }

    try:
        response = httpx.post(
            f"{BASE_URL}/auth/login",
            json=login_payload,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        _TOKEN_ATUAL = response.json()["token"]
        logger.info("Login na API ELLOTEC realizado com sucesso.")
        return _TOKEN_ATUAL

    except Exception as e:
        logger.error(f"Erro ao autenticar na API ELLOTEC: {e}")
        raise


def headers_api(token):
    """Headers padrão das chamadas autenticadas à API."""
    return {
        "Content-Type": "application/json",
        "X-Device-Id": DEVICE_ID,
        "Authorization": f"Bearer {token}",
    }


# =========================================================
# AUXILIARES
# =========================================================

def montar_payload(row):
    """Monta o payload do POST/PUT /produtos a partir de uma linha do banco."""
    return {
        "codigo": str(row["codigo"]),
        "descricao": str(row["descricao"]).strip(),
        "unidade": str(row["unidade"]).strip() if row["unidade"] else "UN",
        "codigoBarras": str(row["codigo_barras"]).strip() if row["codigo_barras"] else None,
        "dun14": str(row["dun14"]).strip() if row["dun14"] else None,
        "quantidadeMultiplaVenda": int(row["quantidade_multipla_venda"]) if row["quantidade_multipla_venda"] else 1,
        "registroAnvisa": str(row["registro_anvisa"]).strip() if row["registro_anvisa"] else None,
        "marcaSistemaOrigemId": str(row["marca_sistema_origem_id"]) if row["marca_sistema_origem_id"] is not None else None,
        "sistemaOrigemId": str(row["codigo"]),
        "ativo": bool(row["ativo"]),
    }


# =========================================================
# ROTINA PRINCIPAL
# =========================================================

def sincronizar_produtos():
    """Busca produtos alterados e envia para o POST /produtos da API.

    Erro definitivo num registro (rejeição real da API, não um 409 normal)
    propaga como RuntimeError — quem chama decide o que fazer (ver app.py,
    que derruba a aplicação inteira). O checkpoint avança registro a
    registro, na ordem de DATA_HORA_ALTERACAO, nunca pulando à frente de
    um registro que ainda não foi processado com sucesso."""
    with conectar() as connection:
        cursor = connection.cursor()
        try:
            maior_data = ler_ultima_data()
            logger.info(f"Última data processada: {maior_data}")

            cursor.execute("ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'")

            query = """
                SELECT
                    fp.codigo_pro AS codigo,
                    fp.NOME_PRODUTO AS descricao,
                    fp.unidade,
                    fp.CODIGO_BARRA AS codigo_barras,
                    fp.CODIGO_DUN14 AS dun14,
                    fp.QTD_MULTIPLA_VENDA AS quantidade_multipla_venda,
                    fp.REGISTRO_MS AS registro_anvisa,
                    CASE
                        WHEN suspenso='N' THEN
                            1
                        ELSE
                            0
                    END AS ativo,
                    fm.MARCA_ID AS marca_sistema_origem_id,
                    fp.DATA_HORA_ALTERACAO
                FROM
                    fat_produtos fp
                    LEFT JOIN FAT_MARCAS fm ON fm.MARCA_ID = fp.MARCA_ID
                WHERE
                    (:maior_data IS NULL OR fp.DATA_HORA_ALTERACAO > :maior_data)
                ORDER BY
                    fp.DATA_HORA_ALTERACAO
            """

            cursor.execute(query, {"maior_data": maior_data})
            columns = [col[0].lower() for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    if len(rows) == 0:
        logger.info("Nenhum produto novo/alterado para enviar.")
        return

    logger.info(f"Encontrados {len(rows)} produtos para enviar.")

    for idx, row in enumerate(rows, start=1):
        payload = montar_payload(row)
        codigo = payload["codigo"]

        response = requisitar_com_retry(
            "POST",
            f"{BASE_URL}/produtos",
            obter_token,
            headers_api,
            logger=logger,
            json=payload,
        )

        if response.status_code in [200, 201]:
            logger.info(f"[{idx}/{len(rows)}] Produto '{codigo}' enviado com sucesso.")
        elif response.status_code == 409:
            sistema_origem_id = payload["sistemaOrigemId"]
            logger.warning(
                f"[{idx}/{len(rows)}] Produto '{codigo}' já existe (409). "
                f"Atualizando via sistema_origem_id={sistema_origem_id}..."
            )
            update_response = requisitar_com_retry(
                "PUT",
                f"{BASE_URL}/produtos/{sistema_origem_id}",
                obter_token,
                headers_api,
                logger=logger,
                params={"sistema_origem_id": sistema_origem_id},
                json=payload,
            )
            if update_response.status_code == 200:
                logger.info(
                    f"[{idx}/{len(rows)}] Produto '{codigo}' atualizado com sucesso."
                )
            else:
                raise RuntimeError(
                    f"Falha ao atualizar produto '{codigo}' (sistema_origem_id={sistema_origem_id}): "
                    f"{update_response.status_code} {update_response.text}"
                )
        else:
            raise RuntimeError(
                f"Falha ao enviar produto '{codigo}' (sistema_origem_id={payload['sistemaOrigemId']}): "
                f"{response.status_code} {response.text}"
            )

        salvar_ultima_data(row["data_hora_alteracao"])

    logger.info("Todos os produtos do lote foram processados com sucesso.")


if __name__ == '__main__':
    sincronizar_produtos()
