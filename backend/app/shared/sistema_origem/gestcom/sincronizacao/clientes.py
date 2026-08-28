import os
import time
import traceback
from datetime import datetime
import httpx

from app.shared.sistema_origem.core.log import get_logger
from app.shared.sistema_origem.gestcom.conexao import conectar
from app.shared.sistema_origem.core.api_client import requisitar_com_retry

logger = get_logger("clientes")

# pega o diretório onde está este arquivo .py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# monta o caminho absoluto do arquivo de controle no mesmo diretório
ARQUIVO_REGISTRO = os.path.join(BASE_DIR, "clientes_controle.txt")

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
    """Monta o payload do POST/PUT /clientes a partir de uma linha do banco."""
    return {
        "codigo": str(row["codigo"])[:10] if row["codigo"] is not None else None,
        "sistemaOrigemId": str(row["sistema_origem_id"]),
        "razaoSocial": str(row["razao_social"]).strip(),
        "nomeFantasia": str(row["nome_fantasia"]).strip() if row["nome_fantasia"] else str(row["razao_social"]).strip(),
        "cpfCnpj": str(row["cpf_cnpj"]).strip() if row["cpf_cnpj"] else "",
        "email": str(row["email"]).strip() if row["email"] else None,
        "telefone": str(row["telefone"]).strip() if row["telefone"] else "",
        "celular": str(row["celular"]).strip() if row["celular"] else None,
        "logradouro": str(row["logradouro"]).strip() if row["logradouro"] else None,
        "numero": str(row["numero"]).strip() if row["numero"] else None,
        "complemento": str(row["complemento"]).strip() if row["complemento"] else None,
        "bairro": str(row["bairro"]).strip() if row["bairro"] else None,
        "cep": str(row["cep"]).strip() if row["cep"] else None,
        "cidadeIbge": int(row["cidade_ibge"]) if row["cidade_ibge"] is not None else None,
        "ativo": bool(row["ativo"]),
    }


# =========================================================
# ROTINA PRINCIPAL
# =========================================================

def sincronizar_clientes():
    """Busca clientes alterados e envia para o POST /clientes da API.

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
                    fc.telefone,
                    fc.endereco AS logradouro,
                    'N/D' AS numero,
                    fc.complemento_endereco AS complemento,
                    fc.bairro,
                    fc.cep,
                    fc.DATA_HORA_ALTERACAO
                FROM
                    fat_cadastros fc
                LEFT JOIN fat_cidades cid ON cid.cidade = fc.cidade
                WHERE
                    (:maior_data IS NULL OR fc.DATA_HORA_ALTERACAO > :maior_data)
                ORDER BY
                    fc.DATA_HORA_ALTERACAO
            """

            cursor.execute(query, {"maior_data": maior_data})
            columns = [col[0].lower() for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    if len(rows) == 0:
        logger.info("Nenhum cliente novo/alterado para enviar.")
        return

    logger.info(f"Encontrados {len(rows)} clientes para enviar.")

    for idx, row in enumerate(rows, start=1):
        payload = montar_payload(row)
        cpf_cnpj = payload["cpfCnpj"]

        response = requisitar_com_retry(
            "POST",
            f"{BASE_URL}/clientes",
            obter_token,
            headers_api,
            logger=logger,
            json=payload,
        )

        if response.status_code in [200, 201]:
            logger.info(f"[{idx}/{len(rows)}] Cliente '{cpf_cnpj}' enviado com sucesso.")
        elif response.status_code == 409:
            sistema_origem_id = payload["sistemaOrigemId"]
            logger.warning(
                f"[{idx}/{len(rows)}] Cliente '{cpf_cnpj}' já existe (409). "
                f"Atualizando via sistema_origem_id={sistema_origem_id}..."
            )
            update_response = requisitar_com_retry(
                "PUT",
                f"{BASE_URL}/clientes/{sistema_origem_id}",
                obter_token,
                headers_api,
                logger=logger,
                params={"sistema_origem_id": sistema_origem_id},
                json=payload,
            )
            if update_response.status_code == 200:
                logger.info(
                    f"[{idx}/{len(rows)}] Cliente '{cpf_cnpj}' atualizado com sucesso."
                )
            else:
                raise RuntimeError(
                    f"Falha ao atualizar cliente '{cpf_cnpj}' (sistema_origem_id={sistema_origem_id}): "
                    f"{update_response.status_code} {update_response.text}"
                )
        else:
            raise RuntimeError(
                f"Falha ao enviar cliente '{cpf_cnpj}' (sistema_origem_id={payload['sistemaOrigemId']}): "
                f"{response.status_code} {response.text}"
            )

        salvar_ultima_data(row["data_hora_alteracao"])

    logger.info("Todos os clientes do lote foram processados com sucesso.")


if __name__ == '__main__':
    sincronizar_clientes()
