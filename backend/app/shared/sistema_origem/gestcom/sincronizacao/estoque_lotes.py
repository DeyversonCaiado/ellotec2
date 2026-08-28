import os
import time
import traceback
from datetime import datetime
import httpx

from app.shared.sistema_origem.core.log import get_logger
from app.shared.sistema_origem.gestcom.conexao import conectar
from app.shared.sistema_origem.core.api_client import requisitar_com_retry

logger = get_logger("estoque_lotes")

# pega o diretório onde está este arquivo .py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# monta o caminho absoluto do arquivo de controle no mesmo diretório
ARQUIVO_REGISTRO = os.path.join(BASE_DIR, "estoque_lotes_controle.txt")

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
    """Monta o payload do POST/PUT /estoque/lotes a partir de uma linha do banco.

    sistemaOrigemId é sintético (empresa+produto+lote): FAT_ESTOQUELOTE não
    tem uma chave própria, a linha é a tripla empresa+produto+lote (mesma
    chave natural que a API usa no PUT sem id em /estoque/lotes). Quantidade
    negativa é levada a zero pelo mesmo motivo do saldo total em
    estoque_saldos.py."""
    quantidade = float(row["quantidade"]) if row["quantidade"] is not None else 0.0
    return {
        "empresaSistemaOrigemId": str(row["empresa"]),
        "produtoSistemaOrigemId": str(row["codigo_pro"]),
        "sistemaOrigemId": f"{row['empresa']}-{row['codigo_pro']}-{row['lote']}",
        "lote": str(row["lote"]).strip(),
        "quantidade": max(quantidade, 0.0),
        "fabricacao": row["fabricacao"].strftime("%Y-%m-%d") if row["fabricacao"] else None,
        "vencimento": row["vencimento"].strftime("%Y-%m-%d") if row["vencimento"] else None,
    }


# =========================================================
# ROTINA PRINCIPAL
# =========================================================

def sincronizar_estoque_lotes():
    """Busca o saldo por lote alterado e envia para o POST/PUT /estoque/lotes da API.

    Erro definitivo num registro (rejeição real da API, não um 409 normal)
    propaga como RuntimeError — quem chama decide o que fazer (ver app.py,
    que derruba a aplicação inteira). O checkpoint avança registro a
    registro, na ordem de DATA_HORA_ALTERACAO, nunca pulando à frente de
    um registro que ainda não foi processado com sucesso.

    Precisa rodar depois de produtos (a API rejeita o lote se o produto ainda
    não foi cadastrado) e antes de endereco_lotes (o vínculo de endereçamento
    exige que o lote já exista em /estoque/lotes)."""
    with conectar() as connection:
        cursor = connection.cursor()
        try:
            maior_data = ler_ultima_data()
            logger.info(f"Última data processada: {maior_data}")

            cursor.execute("ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'")

            query = """
                SELECT
                    l.EMPRESA_ID AS empresa,
                    l.CODIGO_PRO AS codigo_pro,
                    l.LOTE AS lote,
                    l.QUANTIDADE AS quantidade,
                    l.DATA_FABRICACAO AS fabricacao,
                    l.VENCIMENTO AS vencimento,
                    l.DATA_HORA_ALTERACAO
                FROM
                    FAT_ESTOQUELOTE l
                    INNER JOIN EMPRESAS emp ON emp.EMPRESA_ID = l.EMPRESA_ID
                WHERE
                    (:maior_data IS NULL OR l.DATA_HORA_ALTERACAO > :maior_data)
                ORDER BY
                    l.DATA_HORA_ALTERACAO
            """

            cursor.execute(query, {"maior_data": maior_data})
            columns = [col[0].lower() for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    if len(rows) == 0:
        logger.info("Nenhum lote de estoque novo/alterado para enviar.")
        return

    logger.info(f"Encontrados {len(rows)} lotes de estoque para enviar.")

    for idx, row in enumerate(rows, start=1):
        if not row["lote"] or not str(row["lote"]).strip():
            logger.warning(
                f"[{idx}/{len(rows)}] Registro '{row['empresa']}-{row['codigo_pro']}' sem lote, pulando."
            )
            salvar_ultima_data(row["data_hora_alteracao"])
            continue

        payload = montar_payload(row)
        sistema_origem_id = payload["sistemaOrigemId"]

        response = requisitar_com_retry(
            "POST",
            f"{BASE_URL}/estoque/lotes",
            obter_token,
            headers_api,
            logger=logger,
            json=payload,
        )

        if response.status_code in [200, 201]:
            logger.info(f"[{idx}/{len(rows)}] Lote '{sistema_origem_id}' enviado com sucesso.")
        elif response.status_code == 409:
            logger.warning(
                f"[{idx}/{len(rows)}] Lote '{sistema_origem_id}' já existe (409). "
                f"Atualizando pela chave natural (empresa+produto+lote)..."
            )
            update_response = requisitar_com_retry(
                "PUT",
                f"{BASE_URL}/estoque/lotes",
                obter_token,
                headers_api,
                logger=logger,
                json=payload,
            )
            if update_response.status_code == 200:
                logger.info(
                    f"[{idx}/{len(rows)}] Lote '{sistema_origem_id}' atualizado com sucesso."
                )
            else:
                raise RuntimeError(
                    f"Falha ao atualizar lote '{sistema_origem_id}': "
                    f"{update_response.status_code} {update_response.text}"
                )
        else:
            raise RuntimeError(
                f"Falha ao enviar lote '{sistema_origem_id}': "
                f"{response.status_code} {response.text}"
            )

        salvar_ultima_data(row["data_hora_alteracao"])

    logger.info("Todos os lotes de estoque do lote foram processados com sucesso.")


if __name__ == '__main__':
    sincronizar_estoque_lotes()
