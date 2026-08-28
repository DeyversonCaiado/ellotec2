import os
import time
import traceback
from datetime import datetime
import httpx

from app.shared.sistema_origem.core.log import get_logger
from app.shared.sistema_origem.gestcom.conexao import conectar
from app.shared.sistema_origem.core.api_client import requisitar_com_retry

logger = get_logger("funcionarios")

# pega o diretório onde está este arquivo .py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# monta o caminho absoluto do arquivo de controle no mesmo diretório
ARQUIVO_REGISTRO = os.path.join(BASE_DIR, "funcionarios_controle.txt")

# =========================================================
# CONFIGURAÇÕES DA API ELLOTEC
# =========================================================
BASE_URL = "http://localhost:8000"
DEVICE_ID = "3f1c2d2a-6b6e-4b61-9f2c-0d0f7b7d9a11"
LOGIN_USUARIO = "admin"
LOGIN_SENHA = "123456"

# cargo padrão atribuído a todo funcionário sincronizado (API exige cargoId)
CARGO_ID_PADRAO = "d8258ccf-6091-44ba-b9cb-318cc23c333a"

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

def completar_senha(senha):
    """Garante que a senha enviada tenha exatos 6 caracteres.
    Se menor que 6, repete os caracteres até atingir 6.
    Se maior que 6, pega apenas os 6 primeiros."""
    if not senha:
        senha = "000000"

    senha = str(senha).strip()
    if not senha:
        senha = "000000"

    while len(senha) < 6:
        senha += senha

    return senha[:6]


def montar_payload(row):
    """Monta o payload do POST /usuarios a partir de uma linha do banco."""
    usuario = str(row["usuario"]).strip()

    # API espera `permissoes` como lista de chaves (ex: "usuarios.acessar"),
    # não mais um dicionário por domínio. Funcionário sincronizado começa
    # sem nenhuma permissão.
    permissoes = []

    return {
        "usuario": usuario,
        "sistemaOrigemId": str(row["sistema_origem_id"]),
        "nome": str(row["nome"]),
        "email": f"{usuario}@ellotec.com",
        "cargo": "",
        "cargoId": CARGO_ID_PADRAO,
        "ativo": bool(row["ativo"]),
        "senha": completar_senha(row["senha"]),
        "permissoes": permissoes,
    }


# =========================================================
# ROTINA PRINCIPAL
# =========================================================

def sincronizar_funcionarios():
    """Busca funcionários alterados e envia para o POST /usuarios da API.

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
                    nome,
                    funcionario AS usuario,
                    CASE
                        WHEN tipo = 0 THEN 0
                        ELSE 1
                    END AS ativo,
                    SUBSTR(senha, 1, 6) AS senha,
                    funcionario AS sistema_origem_id,
                    ff.DATA_HORA_ALTERACAO
                FROM
                    FAT_FUNCIONARIOS ff
                WHERE
                    (:maior_data IS NULL OR ff.DATA_HORA_ALTERACAO > :maior_data)
                ORDER BY
                    ff.DATA_HORA_ALTERACAO
            """

            cursor.execute(query, {"maior_data": maior_data})
            columns = [col[0].lower() for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    if len(rows) == 0:
        logger.info("Nenhum funcionário novo/alterado para enviar.")
        return

    logger.info(f"Encontrados {len(rows)} funcionários para enviar.")

    for idx, row in enumerate(rows, start=1):
        payload = montar_payload(row)
        usuario = payload["usuario"]

        response = requisitar_com_retry(
            "POST",
            f"{BASE_URL}/usuarios",
            obter_token,
            headers_api,
            logger=logger,
            json=payload,
        )

        if response.status_code in [200, 201]:
            logger.info(f"[{idx}/{len(rows)}] Usuário '{usuario}' enviado com sucesso.")
        elif response.status_code == 409:
            sistema_origem_id = payload["sistemaOrigemId"]
            logger.warning(
                f"[{idx}/{len(rows)}] Usuário '{usuario}' já existe (409). "
                f"Atualizando via sistema_origem_id={sistema_origem_id}..."
            )
            update_response = requisitar_com_retry(
                "PUT",
                f"{BASE_URL}/usuarios/{sistema_origem_id}",
                obter_token,
                headers_api,
                logger=logger,
                params={"sistema_origem_id": sistema_origem_id},
                json=payload,
            )
            if update_response.status_code == 200:
                logger.info(
                    f"[{idx}/{len(rows)}] Usuário '{usuario}' atualizado com sucesso."
                )
            else:
                raise RuntimeError(
                    f"Falha ao atualizar usuário '{usuario}' (sistema_origem_id={sistema_origem_id}): "
                    f"{update_response.status_code} {update_response.text}"
                )
        else:
            raise RuntimeError(
                f"Falha ao enviar usuário '{usuario}' (sistema_origem_id={payload['sistemaOrigemId']}): "
                f"{response.status_code} {response.text}"
            )

        salvar_ultima_data(row["data_hora_alteracao"])

    logger.info("Todos os funcionários do lote foram processados com sucesso.")


if __name__ == '__main__':
    sincronizar_funcionarios()
