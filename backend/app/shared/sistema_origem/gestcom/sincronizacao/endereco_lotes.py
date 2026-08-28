import os
import time
import traceback
from datetime import datetime
import httpx

from app.shared.sistema_origem.core.log import get_logger
from app.shared.sistema_origem.gestcom.conexao import conectar
from app.shared.sistema_origem.core.api_client import requisitar_com_retry

logger = get_logger("endereco_lotes")

# pega o diretório onde está este arquivo .py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# monta o caminho absoluto do arquivo de controle no mesmo diretório
ARQUIVO_REGISTRO = os.path.join(BASE_DIR, "endereco_lotes_controle.txt")

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
    """Monta o payload do POST /enderecamento/vinculos a partir de uma linha do banco.

    O vínculo é resolvido pela API por texto, não por id: `enderecoDescricao`
    (endereço dentro da empresa) e produto+`lote` (que por sua vez já precisa
    existir em /estoque/lotes — ver `_resolver_lote_id` no backend). Não tem
    quantidade — o schema só amarra lote a endereço, quem guarda o saldo é
    /estoque/lotes."""
    return {
        "empresaSistemaOrigemId": str(row["empresa"]),
        "sistemaOrigemId": f"{row['empresa']}-{row['endereco_id']}-{row['codigo_pro']}-{row['lote']}",
        "enderecoDescricao": str(row["descricao"]).strip(),
        "produtoSistemaOrigemId": str(row["codigo_pro"]),
        "lote": str(row["lote"]).strip(),
    }


# =========================================================
# QUERY
# =========================================================

QUERY_ENDERECO_LOTES = """
    SELECT
        v.EMPRESA_ID AS empresa,
        v.ENDERECO_ID AS endereco_id,
        v.CODIGO_PRO AS codigo_pro,
        v.LOTE AS lote,
        v.DATA_HORA_ALTERACAO,
        (
            SELECT E.ENDERECO
            FROM FAT_ENDERECO_ESTOQUE E
            WHERE E.EMPRESA_ID = v.EMPRESA_ID
              AND E.ENDERECO_ID = v.ENDERECO_ID
              AND ROWNUM = 1
        ) AS descricao
    FROM
        FAT_ENDERECO_ESTOQUE_LOTE v
        INNER JOIN EMPRESAS emp ON emp.EMPRESA_ID = v.EMPRESA_ID
    WHERE
        (:maior_data IS NULL OR v.DATA_HORA_ALTERACAO > :maior_data)
    ORDER BY
        v.DATA_HORA_ALTERACAO
"""


# =========================================================
# ROTINA PRINCIPAL
# =========================================================

def sincronizar_endereco_lotes():
    """Busca os vínculos lote-endereço alterados e envia para o POST
    /enderecamento/vinculos da API.

    Diferente dos outros cadastros, o vínculo não tem PUT pela chave natural
    nem campo que mude sozinho (não guarda quantidade) — então um 409 (lote
    já vinculado a esse endereço, ver `_vinculo_por_chave_natural` no
    backend) significa que não há nada a atualizar, só avança o checkpoint.

    Erro definitivo (rejeição real da API) propaga como RuntimeError — quem
    chama decide o que fazer (ver app.py, que derruba a aplicação inteira).
    Precisa rodar depois de estoque_lotes e enderecos (o vínculo exige que
    o lote e o endereço já existam)."""
    with conectar() as connection:
        cursor = connection.cursor()
        try:
            maior_data = ler_ultima_data()
            logger.info(f"Última data processada: {maior_data}")

            cursor.execute("ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'")

            cursor.execute(QUERY_ENDERECO_LOTES, {"maior_data": maior_data})
            columns = [col[0].lower() for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    if len(rows) == 0:
        logger.info("Nenhum vínculo endereço-lote novo/alterado para enviar.")
        return

    logger.info(f"Encontrados {len(rows)} vínculos endereço-lote para enviar.")

    for idx, row in enumerate(rows, start=1):
        if not row["descricao"] or not row["lote"] or not str(row["lote"]).strip():
            logger.warning(
                f"[{idx}/{len(rows)}] Vínculo '{row['empresa']}-{row['endereco_id']}-{row['codigo_pro']}' "
                f"sem endereço ou lote resolvido, pulando."
            )
            salvar_ultima_data(row["data_hora_alteracao"])
            continue

        payload = montar_payload(row)
        sistema_origem_id = payload["sistemaOrigemId"]

        response = requisitar_com_retry(
            "POST",
            f"{BASE_URL}/enderecamento/vinculos",
            obter_token,
            headers_api,
            logger=logger,
            json=payload,
        )

        if response.status_code in [200, 201]:
            logger.info(f"[{idx}/{len(rows)}] Vínculo '{sistema_origem_id}' enviado com sucesso.")
        elif response.status_code == 409:
            logger.info(
                f"[{idx}/{len(rows)}] Vínculo '{sistema_origem_id}' já existe (409), nada a atualizar."
            )
        else:
            raise RuntimeError(
                f"Falha ao enviar vínculo '{sistema_origem_id}': "
                f"{response.status_code} {response.text}"
            )

        salvar_ultima_data(row["data_hora_alteracao"])

    logger.info("Todos os vínculos endereço-lote do lote foram processados com sucesso.")


if __name__ == '__main__':
    sincronizar_endereco_lotes()
