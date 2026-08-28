import os
import time
import traceback
from datetime import datetime
import httpx

from app.shared.sistema_origem.core.log import get_logger
from app.shared.sistema_origem.gestcom.conexao import conectar
from app.shared.sistema_origem.core.api_client import requisitar_com_retry

logger = get_logger("pedidos")

# pega o diretório onde está este arquivo .py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# monta o caminho absoluto do arquivo de controle no mesmo diretório
ARQUIVO_REGISTRO = os.path.join(BASE_DIR, "pedidos_controle.txt")

# =========================================================
# CONFIGURAÇÕES DA API ELLOTEC
# =========================================================
BASE_URL = "http://localhost:8000"
DEVICE_ID = "3f1c2d2a-6b6e-4b61-9f2c-0d0f7b7d9a11"
LOGIN_USUARIO = "admin"
LOGIN_SENHA = "123456"

_TOKEN_ATUAL = None
_CACHE_CLIENTE_ID = {}


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

def _eh_conflito_pedido_existente(response):
    """A API historicamente respondia 409 quando sistemaOrigemId+empresaId já
    existia (checagem prévia em _validar_sistema_origem_disponivel), e é isso
    que o restante do código trata como "já existe, faz PUT". Só que essa
    checagem prévia tem uma janela de corrida (dois processos sincronizando
    o mesmo pedido ao mesmo tempo): quando ela passa pros dois, o segundo
    INSERT esbarra direto na constraint do banco e a API devolve 422 (erro de
    integridade), não 409. Essa função reconhece esse 422 específico como o
    mesmo tipo de conflito, pra não derrubar a aplicação por uma corrida que
    o PUT já resolve sozinho."""
    if response.status_code != 422:
        return False
    try:
        detalhe = response.json()
    except ValueError:
        return False
    return (
        detalhe.get("tipo") == "unicidade"
        and detalhe.get("restricao") == "uq_pedidos_sistema_origem_id_empresa_id"
    )


def buscar_cliente_id(codigo_exp):
    """Resolve o id (UUID) do cliente na API a partir do codigo_exp (sistema_origem_id),
    usando cache em memória para não repetir a consulta a cada pedido do mesmo cliente."""
    codigo_exp = str(codigo_exp)

    if codigo_exp in _CACHE_CLIENTE_ID:
        return _CACHE_CLIENTE_ID[codigo_exp]

    response = requisitar_com_retry(
        "GET",
        f"{BASE_URL}/clientes/{codigo_exp}",
        obter_token,
        headers_api,
        logger=logger,
        params={"sistema_origem_id": codigo_exp},
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Cliente com sistema_origem_id={codigo_exp} não encontrado na API ELLOTEC "
            f"(necessário sincronizar clientes antes de pedidos): "
            f"{response.status_code} {response.text}"
        )

    cliente_id = response.json()["id"]
    _CACHE_CLIENTE_ID[codigo_exp] = cliente_id
    return cliente_id


def montar_item_payload(item_row):
    """Monta um item do payload de /pedidos a partir de uma linha da query de itens.

    A chave natural do item no ERP tem três pernas: empresa + pedido + produto
    (ver PedidoItem em pedido_model.py). Nenhuma sozinha identifica a linha —
    o mesmo produto se repete em pedidos diferentes, e o mesmo pedido existe
    em mais de uma empresa. empresaSistemaOrigemId e pedidoSistemaOrigemId aqui
    são redundantes com o que a capa já manda (o service usa a capa como
    padrão quando o item omite os campos), mas mandar explícito por item deixa
    o snapshot completo sem depender desse fallback."""
    return {
        "produtoSistemaOrigemId": str(item_row["codigo_pro"]) if item_row["codigo_pro"] is not None else None,
        "produtoCodigo": str(item_row["codigo_pro"]) if item_row["codigo_pro"] is not None else "",
        "produtoDescricao": str(item_row["produto"]).strip() if item_row["produto"] else "",
        "quantidade": int(item_row["quantidade"]) if item_row["quantidade"] is not None else 0,
        "enderecoProduto": str(item_row["endereco"]).strip() if item_row["endereco"] else None,
        "lote": str(item_row["lote"]).strip() if item_row["lote"] else None,
        "empresaSistemaOrigemId": str(item_row["empresa_id"]).strip(),
        "pedidoSistemaOrigemId": str(item_row["pedido"]).strip(),
    }


def montar_payload(row, itens, cliente_id):
    """Monta o payload do POST/PUT /pedidos a partir de uma linha da query de cabeçalho.

    statusSistemaOrigemId manda o código bruto do Oracle (ex: "OK", "CAN",
    "ORC"...) direto, sem tradução — o catálogo pedido_status no backend
    ELLOTEC2 é cadastrado manualmente com chave/descrição/sistema_origem_id
    iguais ao próprio código Oracle."""
    return {
        "dataPedido": row["data_pedido"].strftime("%Y-%m-%d"),
        "liberadoEm": row["liberacao_data_hora"].isoformat() if row["liberacao_data_hora"] else None,
        "clienteId": cliente_id,
        "clienteNomeFantasia": str(row["razao_social"]).strip() if row["razao_social"] else "",
        "clienteCnpj": str(row["cad_cgc"]).strip() if row["cad_cgc"] else "",
        "empresaSistemaOrigemId": str(row["empresa"]),
        "vendedorSistemaOrigemId": str(row["vendedor_sistema_origem_id"]).strip() if row["vendedor_sistema_origem_id"] else None,
        "sistemaOrigemId": str(row["pedido"]),
        "statusSistemaOrigemId": str(row["status_oracle"]).strip() if row["status_oracle"] else None,
        "itens": itens,
        "observacoes": "",
    }


# =========================================================
# QUERIES
# =========================================================

QUERY_CABECALHO = """
    SELECT
        cp.empresa_id AS empresa,
        cp.pedido,
        cp.DATA_PEDIDO,
        cp.liberacao_data_hora,
        cp.DATA_HORA_ALTERACAO,
        c.codigo_exp,
        c.cad_cgc,
        c.razao_social || ' - ' || c.codigo_exp as razao_social,
        c.inscricao_estadual as ie,
        fc.NOME AS cidade,
        fc.ESTADO,
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
        LEFT JOIN FAT_CIDADES fc ON fc.CIDADE = c.CIDADE
    WHERE
        cp.liberacao_data_hora IS NOT NULL
        AND (:maior_data IS NULL OR cp.DATA_HORA_ALTERACAO > :maior_data)
    ORDER BY
        cp.DATA_HORA_ALTERACAO
"""

QUERY_ITENS = """
    SELECT
        cp.empresa_id,
        cp.pedido,
        cp.DATA_PEDIDO,
        fi.item AS numero_item,
        fi.codigo_pro,
        fp.NOME_PRODUTO || ' - ' || fi.codigo_pro AS produto,
        fp.unidade,
        fm.nome_marca,
        fi.QUANTIDADE,
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
            'NAO ENDERECADO'
        ) AS endereco
    FROM
        fat_capapedido cp
        LEFT JOIN FAT_ITEMPEDIDO fi ON fi.pedido = cp.PEDIDO
            AND fi.EMPRESA_ID = cp.empresa_id
        LEFT JOIN FAT_PRODUTOS fp ON fp.codigo_pro = fi.CODIGO_PRO
        LEFT JOIN FAT_MARCAS fm ON fm.MARCA_ID = fp.MARCA_ID
    WHERE
        0=0
        AND cp.empresa_id = :empresa_id
        AND cp.pedido = :pedido
"""


def buscar_itens_pedido(cursor, empresa_id, pedido):
    cursor.execute(QUERY_ITENS, {"empresa_id": empresa_id, "pedido": pedido})
    columns = [col[0].lower() for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# =========================================================
# ROTINA PRINCIPAL
# =========================================================

def sincronizar_pedidos():
    """Busca pedidos liberados e envia para o POST /pedidos da API.

    Erro definitivo num registro (rejeição real da API, não um 409 normal)
    propaga como RuntimeError — quem chama decide o que fazer (ver app.py,
    que derruba a aplicação inteira). O checkpoint avança registro a
    registro, na ordem de DATA_HORA_ALTERACAO (não liberacao_data_hora):
    um pedido já liberado que sofra qualquer alteração no ERP depois disso
    (item, endereço, status etc.) precisa ser pego de novo e reenviado via
    PUT, o que não aconteceria se o corte fosse pela data de liberação, que
    não muda depois de setada. Nunca pula à frente de um registro que ainda
    não foi processado com sucesso."""
    with conectar() as connection:
        cursor = connection.cursor()
        try:
            maior_data = ler_ultima_data()
            logger.info(f"Última data processada: {maior_data}")

            cursor.execute("ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'")

            cursor.execute(QUERY_CABECALHO, {"maior_data": maior_data})
            columns = [col[0].lower() for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

            if len(rows) == 0:
                logger.info("Nenhum pedido novo/liberado para enviar.")
                return

            logger.info(f"Encontrados {len(rows)} pedidos para enviar.")

            pedidos = []
            for row in rows:
                itens_rows = buscar_itens_pedido(cursor, row["empresa"], row["pedido"])
                itens = [
                    montar_item_payload(item_row)
                    for item_row in itens_rows
                    if item_row["codigo_pro"] is not None and (item_row["quantidade"] or 0) > 0
                ]
                pedidos.append((row, itens))
        finally:
            cursor.close()

    for idx, (row, itens) in enumerate(pedidos, start=1):
        if not itens:
            logger.warning(
                f"[{idx}/{len(pedidos)}] Pedido '{row['empresa']}-{row['pedido']}' sem itens, pulando."
            )
            salvar_ultima_data(row["data_hora_alteracao"])
            continue

        cliente_id = buscar_cliente_id(row["codigo_exp"])
        payload = montar_payload(row, itens, cliente_id)
        sistema_origem_id = payload["sistemaOrigemId"]

        response = requisitar_com_retry(
            "POST",
            f"{BASE_URL}/pedidos",
            obter_token,
            headers_api,
            logger=logger,
            json=payload,
        )

        if response.status_code in [200, 201]:
            logger.info(f"[{idx}/{len(pedidos)}] Pedido '{sistema_origem_id}' enviado com sucesso.")
        elif response.status_code == 409 or _eh_conflito_pedido_existente(response):
            logger.warning(
                f"[{idx}/{len(pedidos)}] Pedido '{sistema_origem_id}' já existe "
                f"({response.status_code}). Atualizando via sistema_origem_id={sistema_origem_id}..."
            )
            update_response = requisitar_com_retry(
                "PUT",
                f"{BASE_URL}/pedidos/{sistema_origem_id}",
                obter_token,
                headers_api,
                logger=logger,
                params={"sistema_origem_id": sistema_origem_id},
                json=payload,
            )
            if update_response.status_code == 200:
                logger.info(
                    f"[{idx}/{len(pedidos)}] Pedido '{sistema_origem_id}' atualizado com sucesso."
                )
            else:
                raise RuntimeError(
                    f"Falha ao atualizar pedido '{sistema_origem_id}': "
                    f"{update_response.status_code} {update_response.text}"
                )
        else:
            raise RuntimeError(
                f"Falha ao enviar pedido '{sistema_origem_id}': "
                f"{response.status_code} {response.text}"
            )

        salvar_ultima_data(row["data_hora_alteracao"])

    logger.info("Todos os pedidos do lote foram processados com sucesso.")


if __name__ == '__main__':
    sincronizar_pedidos()
