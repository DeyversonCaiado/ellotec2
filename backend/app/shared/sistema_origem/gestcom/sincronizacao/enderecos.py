import os
import time
import traceback
from datetime import datetime
import httpx

from app.shared.sistema_origem.core.log import get_logger
from app.shared.sistema_origem.gestcom.conexao import conectar
from app.shared.sistema_origem.core.api_client import requisitar_com_retry

logger = get_logger("enderecos")

# pega o diretório onde está este arquivo .py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# monta o caminho absoluto do arquivo de controle no mesmo diretório
ARQUIVO_REGISTRO = os.path.join(BASE_DIR, "enderecos_controle.txt")

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
    """Monta o payload do POST/PUT /enderecamento/enderecos a partir de uma linha do banco."""
    return {
        "empresaSistemaOrigemId": str(row["empresa"]),
        "sistemaOrigemId": f"{row['empresa']}-{row['endereco_id']}",
        "descricao": str(row["descricao"]).strip(),
    }


def buscar_endereco_id_existente(empresa, descricao):
    """Resolve o UUID de um endereço já cadastrado pela descrição.

    /enderecamento/enderecos não tem um PUT pela chave natural como
    /estoque/saldos e /estoque/lotes têm — só GET (busca por texto, `q`) e
    PUT/{id}. Então, quando o POST bate em 409 (endereço já existe para essa
    descrição na empresa — ver `_endereco_por_descricao` no backend), a única
    forma de atualizar é achar o id por aqui primeiro."""
    response = requisitar_com_retry(
        "GET",
        f"{BASE_URL}/enderecamento/enderecos",
        obter_token,
        headers_api,
        logger=logger,
        params={"q": descricao, "per_page": 100},
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Falha ao buscar endereço existente '{descricao}': "
            f"{response.status_code} {response.text}"
        )

    for item in response.json().get("items", []):
        if item.get("descricao") == descricao and item.get("empresaSistemaOrigemId") == str(empresa):
            return item["id"]

    return None


# =========================================================
# QUERY
# =========================================================

QUERY_ENDERECOS = """
    SELECT
        e.EMPRESA_ID AS empresa,
        e.ENDERECO_ID AS endereco_id,
        e.ENDERECO AS descricao,
        MAX(e.DATA_HORA_ALTERACAO) AS data_hora_alteracao
    FROM
        FAT_ENDERECO_ESTOQUE e
        INNER JOIN EMPRESAS emp ON emp.EMPRESA_ID = e.EMPRESA_ID
    GROUP BY
        e.EMPRESA_ID, e.ENDERECO_ID, e.ENDERECO
    HAVING
        (:maior_data IS NULL OR MAX(e.DATA_HORA_ALTERACAO) > :maior_data)
    ORDER BY
        MAX(e.DATA_HORA_ALTERACAO)
"""


# =========================================================
# ROTINA PRINCIPAL
# =========================================================

def sincronizar_enderecos():
    """Busca os endereços de estoque (posições do galpão) alterados e envia
    para o POST/PUT /enderecamento/enderecos da API.

    FAT_ENDERECO_ESTOQUE não tem uma tabela mestre separada dos endereços —
    é uma linha por produto guardado em cada posição, e DATA_HORA_ALTERACAO
    muda a cada movimentação de estoque, não só quando o endereço em si é
    criado/renomeado. Por isso a consulta agrupa por empresa+endereço e usa o
    maior DATA_HORA_ALTERACAO do grupo como corte: reprocessa o endereço com
    mais frequência do que o necessário, mas nunca perde uma criação/renome,
    e o reenvio é seguro (POST em 409 vira PUT, idempotente).

    Erro definitivo num registro (rejeição real da API, não um 409 normal)
    propaga como RuntimeError — quem chama decide o que fazer (ver app.py,
    que derruba a aplicação inteira). Precisa rodar antes de endereco_lotes
    (o vínculo de endereçamento exige que o endereço já exista)."""
    with conectar() as connection:
        cursor = connection.cursor()
        try:
            maior_data = ler_ultima_data()
            logger.info(f"Última data processada: {maior_data}")

            cursor.execute("ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'")

            cursor.execute(QUERY_ENDERECOS, {"maior_data": maior_data})
            columns = [col[0].lower() for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    if len(rows) == 0:
        logger.info("Nenhum endereço novo/alterado para enviar.")
        return

    logger.info(f"Encontrados {len(rows)} endereços para enviar.")

    for idx, row in enumerate(rows, start=1):
        payload = montar_payload(row)
        sistema_origem_id = payload["sistemaOrigemId"]
        descricao = payload["descricao"]

        response = requisitar_com_retry(
            "POST",
            f"{BASE_URL}/enderecamento/enderecos",
            obter_token,
            headers_api,
            logger=logger,
            json=payload,
        )

        if response.status_code in [200, 201]:
            logger.info(f"[{idx}/{len(rows)}] Endereço '{sistema_origem_id}' enviado com sucesso.")
        elif response.status_code == 409:
            logger.warning(
                f"[{idx}/{len(rows)}] Endereço '{sistema_origem_id}' já existe (409). "
                f"Localizando id pela descrição '{descricao}' para atualizar..."
            )
            endereco_id = buscar_endereco_id_existente(row["empresa"], descricao)
            if endereco_id is None:
                raise RuntimeError(
                    f"Endereço '{sistema_origem_id}' respondeu 409 mas não foi encontrado "
                    f"na busca por descrição '{descricao}'."
                )

            update_response = requisitar_com_retry(
                "PUT",
                f"{BASE_URL}/enderecamento/enderecos/{endereco_id}",
                obter_token,
                headers_api,
                logger=logger,
                json=payload,
            )
            if update_response.status_code == 200:
                logger.info(
                    f"[{idx}/{len(rows)}] Endereço '{sistema_origem_id}' atualizado com sucesso."
                )
            else:
                raise RuntimeError(
                    f"Falha ao atualizar endereço '{sistema_origem_id}': "
                    f"{update_response.status_code} {update_response.text}"
                )
        else:
            raise RuntimeError(
                f"Falha ao enviar endereço '{sistema_origem_id}': "
                f"{response.status_code} {response.text}"
            )

        if row["data_hora_alteracao"] is not None:
            salvar_ultima_data(row["data_hora_alteracao"])
        else:
            # Endereço cuja linha mais recente em FAT_ENDERECO_ESTOQUE nunca
            # recebeu DATA_HORA_ALTERACAO (dado legado). Sem data não dá pra
            # avançar o checkpoint com segurança — deixa como está e ele volta
            # a aparecer na próxima consulta (reenvio idempotente via 409/PUT).
            logger.warning(
                f"[{idx}/{len(rows)}] Endereço '{sistema_origem_id}' sem DATA_HORA_ALTERACAO, "
                f"checkpoint não avançado para este registro."
            )

    logger.info("Todos os endereços do lote foram processados com sucesso.")


if __name__ == '__main__':
    sincronizar_enderecos()
