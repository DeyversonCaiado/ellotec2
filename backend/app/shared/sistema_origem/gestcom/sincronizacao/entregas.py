"""
Sincronização da gestão de entregas: notas faturadas + mapas de carga.

Lê o Oracle do ERP e manda para a própria API ELLOTEC, como todos os outros
sincronizadores deste pacote — `POST /entregas/mapas` para o mapa de carga e
`POST /entregas/notas` para a nota com os itens. Os dois endpoints são upsert
(respondem 200 sempre, mesmo reprocessando), então aqui NÃO existe o
tratamento de 409/PUT que `pedidos.py` precisa ter.

A consulta veio do relatório de vendas do sistema antigo
(`C:\\projetos\\padrao_arq\\gestao_vendas\\persistence\\oracle.py`), que é onde
a classificação da nota por CFOP e o vínculo com o mapa de carga já estavam
resolvidos e conferidos. O que ficou de fora de propósito: todo o `CASE` de
prazo/SLA daquele SQL, porque prazo é regra de negócio NOSSA e mora em
`app/domains/entregas/entrega_prazo.py` — mandar o prazo calculado pelo ERP
criaria duas verdades sobre o mesmo número.

Rodar a partir de `C:\\projetos\\ellotec2\\backend`:

    python -m app.shared.sistema_origem.gestcom.sincronizacao.entregas
"""

import os
from datetime import datetime

import httpx

from app.shared.sistema_origem.core.api_client import requisitar_com_retry
from app.shared.sistema_origem.core.log import get_logger
from app.shared.sistema_origem.gestcom.conexao import conectar

logger = get_logger("entregas")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_REGISTRO = os.path.join(BASE_DIR, "entregas_controle.txt")

# =========================================================
# CONFIGURAÇÕES DA API ELLOTEC
# =========================================================
BASE_URL = "http://localhost:8000"
DEVICE_ID = "3f1c2d2a-6b6e-4b61-9f2c-0d0f7b7d9a11"
LOGIN_USUARIO = "admin"
LOGIN_SENHA = "123456"

_TOKEN_ATUAL = None

# De onde a PRIMEIRA execução começa, quando ainda não há arquivo de controle.
#
# Sem esse piso, a primeira rodada varreria a nota mais antiga do ERP — anos de
# documento que a tela de entregas não acompanha — e o lote inicial levaria
# horas antes de chegar no que interessa. Agosto/2026 é quando a gestão de
# entregas entrou no ar aqui; para recarregar mais coisa, basta apagar o
# arquivo de controle e baixar esta data.
DATA_INICIAL = datetime(2026, 8, 1)

# A chave de acesso da NF-e tem 44 posições fixas, e o contrato da API recusa
# qualquer outro tamanho. Chave em branco/parcial no ERP vira None em vez de
# derrubar a nota inteira — quem responde pela chave é o domínio fiscal.
TAMANHO_CHAVE_NFE = 44

# A classificação que o SQL do sistema antigo montava por CFOP e status → o
# slug do contrato (`TipoNota` em entrega_contrato.py). A tradução fica aqui,
# em Python e visível, e não dentro do SQL: o CASE lá embaixo é cópia fiel do
# relatório antigo, e mexer nele para trocar rótulo por slug tiraria a
# possibilidade de comparar os dois lado a lado.
TIPO_NOTA_POR_ROTULO = {
    "Venda": "venda",
    "Bonificacao": "bonificacao",
    "Dev. Cli.": "devolucao_cliente",
    "Complementar": "complementar",
    "Perda": "perda",
    "Outros": "outros",
}


# =========================================================
# CONTROLE DA ÚLTIMA DATA PROCESSADA
# =========================================================

def ler_ultima_data():
    """Lê a maior DATA_HORA_ALTERACAO salva no arquivo local.

    Sem arquivo (primeira execução) devolve `DATA_INICIAL`, e não None: aqui
    "sem checkpoint" não significa "traga tudo", significa "comece de onde a
    gestão de entregas começou"."""
    if not os.path.exists(ARQUIVO_REGISTRO):
        return DATA_INICIAL

    with open(ARQUIVO_REGISTRO, "r") as f:
        valor = f.read().strip()

    if not valor:
        return DATA_INICIAL

    try:
        return datetime.strptime(valor, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        logger.warning(f"Data inválida no arquivo de controle: {valor}")
        return DATA_INICIAL


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

    try:
        response = httpx.post(
            f"{BASE_URL}/auth/login",
            json={"usuario": LOGIN_USUARIO, "senha": LOGIN_SENHA},
            headers={"X-Device-Id": DEVICE_ID},
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
# QUERIES
# =========================================================

# Uma linha por NOTA (o relatório antigo trazia uma linha por item, porque ele
# somava valores; aqui a nota é a capa e os itens vêm na consulta seguinte).
#
# O filtro de status e o `cancelado = 'N'` são os mesmos do relatório antigo.
# LIMITAÇÃO HERDADA: uma nota cancelada DEPOIS de sincronizada deixa de ser
# devolvida por esta consulta, e a linha que já está aqui continua com a
# situação antiga. Corrigir exige trazer as canceladas e marcá-las — o que só
# faz sentido junto com a decisão de como a tela deve exibi-las.
#
# O corpo é um só e o RECORTE é que muda (`{filtro}`), porque as duas formas de
# pedir nota são a mesma consulta: o ciclo automático corta pelo checkpoint
# (o que mudou desde a última rodada) e a recarga manual corta pela data da
# nota (o que foi faturado no período). Duplicar as 70 linhas de SQL para
# trocar uma linha do WHERE faria as duas divergirem na primeira correção.
_QUERY_NOTAS_MODELO = """
    SELECT
        fn.empresa_id,
        fn.numero_nota,
        fn.serie,
        fn.status,
        fn.pedido,
        fn.codigo_exp,
        fn.data_hora_nota,
        fn.total_nota,
        fn.vendedor,
        fn.nfe_chaveacesso,
        fn.nfe_chaveacesso_ref,
        fn.data_hora_alteracao,
        CASE
            WHEN SUBSTR(fn.status, 3, 4) = 'C' THEN 'Cancelada'
            ELSE fn.status
        END AS situacao,
        fc.razao_social,
        fcid.nome AS cidade,
        fe.estado AS uf,
        ft.nome AS transportadora_nome,
        CASE
            WHEN fn.cfo = '5927' THEN 'Perda'
            WHEN fn.nfe_complementar = 'S' THEN 'Complementar'
            WHEN fn.status IN ('N1','NF','CP')
                 AND fn.especial = 'N'
                 AND cfo.cfo_venda = 'S'
                 AND fn.nfe_simplesremessa = 'N'
                THEN 'Venda'
            WHEN cfo.cfo_devolucao = 'S'
                 AND fn.especial = 'N'
                 AND fn.status = 'DC'
                 AND fn.nfe_simplesremessa = 'N'
                THEN 'Dev. Cli.'
            WHEN fn.especial = 'N'
                 AND cfo.cfo_bonificacao = 'S'
                 AND fn.nfe_simplesremessa = 'N'
                THEN 'Bonificacao'
            ELSE 'Outros'
        END AS tipo_nota,
        mc.mapadecarga_id,
        mc.data_mapa,
        mc.cgc_transportadora AS mapa_transportadora_cnpj,
        ftm.nome AS mapa_transportadora_nome,
        mc.nome_motorista AS mapa_motorista,
        mc.matricula_veiculo AS mapa_placa_veiculo
    FROM fat_notas fn
    LEFT JOIN fat_cadastros fc ON fc.codigo_exp = fn.codigo_exp
    LEFT JOIN fat_cidades fcid ON fcid.cidade = fc.cidade
    LEFT JOIN fat_estados fe ON fe.estado = fcid.estado
    LEFT JOIN fat_cfo cfo ON cfo.cfo_id = fn.cfo
    LEFT JOIN fat_transportadora ft ON ft.cgc_tran = fn.cgc_tran
    /* O mapa de carga da nota. `rn = 1` porque uma nota reembarcada aparece em
       mais de um mapa, e o que vale é o último; mapa cancelado ('C') nao conta
       — a mercadoria não saiu nele. */
    LEFT JOIN (
        SELECT
            mn.nota_empresa_id,
            mn.numero_nota,
            mn.status,
            mn.serie,
            mn.mapadecarga_id,
            mcg.data_mapa,
            mcg.cgc_transportadora,
            mcg.nome_motorista,
            mcg.matricula_veiculo,
            ROW_NUMBER() OVER (
                PARTITION BY mn.nota_empresa_id, mn.numero_nota, mn.status, mn.serie
                ORDER BY mn.mapadecarga_id DESC
            ) AS rn
        FROM fat_mapacarga_notas_motivos mn
        INNER JOIN fat_mapadecarga mcg ON mcg.mapadecarga_id = mn.mapadecarga_id
        WHERE mcg.status NOT IN ('C')
    ) mc
        ON mc.nota_empresa_id = fn.empresa_id
       AND mc.numero_nota = fn.numero_nota
       AND mc.status = fn.status
       AND mc.serie = fn.serie
       AND mc.rn = 1
    LEFT JOIN fat_transportadora ftm ON ftm.cgc_tran = mc.cgc_transportadora
    WHERE fn.status IN ('N1','NF','CP','CT','TN','TE','DC','DCW','DF','S1','DEN')
      AND fn.cancelado = 'N'
      AND {filtro}
    ORDER BY fn.data_hora_alteracao
"""

# O ciclo automático: o que foi alterado depois do checkpoint.
QUERY_NOTAS = _QUERY_NOTAS_MODELO.format(filtro="fn.data_hora_alteracao > :maior_data")

# A recarga manual: o que foi faturado a partir de uma data. O corte é pela
# DATA DA NOTA (data de negócio), e não pela data de alteração — quem pede
# "as entregas do dia 21 para cá" está falando do faturamento, não de quando o
# ERP encostou na linha.
QUERY_NOTAS_POR_DATA = _QUERY_NOTAS_MODELO.format(
    filtro="TRUNC(fn.data_nota) >= :data_nota_minima"
)

# A mesma recarga, com fim: "de 1º a 21 de agosto". As duas pontas são
# INCLUSIVAS — quem diz "até dia 21" está contando o dia 21.
#
# É uma constante separada em vez de um `BETWEEN` com data final padrão porque
# não existe padrão honesto para ela: usar "hoje" pularia em silêncio uma nota
# com data à frente do relógio da máquina, que é justamente o tipo de coisa que
# ninguém procura até faltar.
QUERY_NOTAS_POR_PERIODO = _QUERY_NOTAS_MODELO.format(
    filtro="TRUNC(fn.data_nota) BETWEEN :data_nota_minima AND :data_nota_maxima"
)

# Os itens da nota. A UNION com `fat_itemsimples` vem do relatório antigo: nota
# de simples remessa não tem linha em `fat_itemnota`, e sem ela a nota chegaria
# aqui sem produto nenhum.
QUERY_ITENS = """
    SELECT
        fin.nr_item,
        fin.codigo_pro,
        fp.nome_produto,
        fm.nome_marca,
        fin.quantidade,
        fin.quantidade_devolucao,
        fin.vpreco_venda,
        fin.preco_liquido,
        fin.lote,
        fp.refrigerado
    FROM (
        SELECT
            i.nr_item, i.codigo_pro, i.quantidade, i.quantidade_devolucao,
            i.vpreco_venda, i.preco_liquido, i.lote
        FROM fat_itemnota i
        WHERE i.empresa_id = :empresa_id
          AND i.numero_nota = :numero_nota
          AND i.serie = :serie
          AND i.status = :status
          AND i.pedido = :pedido

        UNION ALL

        SELECT
            0 AS nr_item, s.codigo_pro, s.quantidade, 0 AS quantidade_devolucao,
            s.preco AS vpreco_venda,
            ((s.preco * s.quantidade) - s.desconto) AS preco_liquido,
            s.lote
        FROM fat_itemsimples s
        WHERE s.empresa_id = :empresa_id
          AND s.numero_nota = :numero_nota
          AND s.serie = :serie
          AND s.status = :status
          AND s.pedido = :pedido
    ) fin
    LEFT JOIN fat_produtos fp ON fp.codigo_pro = fin.codigo_pro
    LEFT JOIN fat_marcas fm ON fm.marca_id = fp.marca_id
    ORDER BY fin.nr_item, fin.codigo_pro, fin.lote
"""


def buscar_itens_nota(cursor, row):
    cursor.execute(
        QUERY_ITENS,
        {
            "empresa_id": row["empresa_id"],
            "numero_nota": row["numero_nota"],
            "serie": row["serie"],
            "status": row["status"],
            "pedido": row["pedido"],
        },
    )
    colunas = [col[0].lower() for col in cursor.description]
    return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


# =========================================================
# PAYLOADS
# =========================================================

def _texto(valor):
    """Texto limpo, ou None quando não há valor. O `TRIM` fica no Python, e não
    no SQL, para o CASE continuar igual ao do relatório antigo."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _chave_nfe(valor):
    """A chave só entra se tiver as 44 posições do layout da NF-e."""
    chave = _texto(valor)
    if chave is None or len(chave) != TAMANHO_CHAVE_NFE:
        return None
    return chave


def _numero(valor):
    return float(valor) if valor is not None else 0.0


def montar_item_payload(item_row, numero_item):
    """Um item do payload de `/entregas/notas`.

    `numeroItem` é NUMERADO AQUI, e não copiado de `nr_item`: as linhas de
    `fat_itemsimples` chegam todas com 0, e o contrato exige número maior que
    zero e único dentro da nota. A ordem é a da consulta (nr_item, produto,
    lote), então a numeração é estável entre reprocessamentos da mesma nota."""
    return {
        "numeroItem": numero_item,
        "produtoCodigo": _texto(item_row["codigo_pro"]) or "",
        "produtoDescricao": _texto(item_row["nome_produto"]) or "",
        "marcaNome": _texto(item_row["nome_marca"]),
        "quantidade": _numero(item_row["quantidade"]),
        "precoUnitario": _numero(item_row["vpreco_venda"]),
        "valorTotal": _numero(item_row["preco_liquido"]),
        "lote": _texto(item_row["lote"]),
        # A validade não está na nota do ERP (mora no controle de lotes) — o
        # campo existe no domínio e continua nulo até alguém precisar dele.
        "validade": None,
        "quantidadeDevolvida": _numero(item_row["quantidade_devolucao"]),
        "observacao": None,
    }


def montar_mapa_payload(row):
    """O mapa de carga (`POST /entregas/mapas`).

    `numeroMapa` é o `mapadecarga_id` do ERP como texto — é ele que a nota
    referencia em `entregaNumeroMapa`, e é a chave do upsert junto da empresa.
    """
    return {
        "empresaSistemaOrigemId": _texto(row["empresa_id"]),
        "numeroMapa": str(row["mapadecarga_id"]),
        "dataMapa": row["data_mapa"].isoformat() if row["data_mapa"] else None,
        "transportadoraNome": _texto(row["mapa_transportadora_nome"]),
        "transportadoraCnpj": _texto(row["mapa_transportadora_cnpj"]),
        "motorista": _texto(row["mapa_motorista"]),
        "placaVeiculo": _texto(row["mapa_placa_veiculo"]),
        "sistemaOrigemId": f"{_texto(row['empresa_id'])}-{row['mapadecarga_id']}",
    }


def montar_nota_payload(row, itens, termolabil):
    """A nota e seus itens (`POST /entregas/notas`).

    Tudo é SNAPSHOT: cliente, transportadora e produto vão pelo NOME que valia
    no dia, e não por id — é o desenho da tabela `entrega_notas`, e é o que
    impede o histórico de mudar quando um cadastro é renomeado.

    O prazo NÃO vai no payload: quem calcula é `entrega_prazo.py`, a partir da
    UF, da cidade e do termolábil que estão aqui.
    """
    empresa = _texto(row["empresa_id"])
    numero_nota = _texto(row["numero_nota"]) or ""
    serie = _texto(row["serie"]) or ""
    pedido = _texto(row["pedido"]) or ""

    return {
        "empresaSistemaOrigemId": empresa,
        "numeroNota": numero_nota,
        "serie": serie,
        "pedido": pedido,
        "tipoNota": TIPO_NOTA_POR_ROTULO.get(_texto(row["tipo_nota"]), "outros"),
        # data_hora_nota e não data_nota: a segunda é só o dia (00:00), e a
        # tela mostra a hora do faturamento.
        "dataNota": row["data_hora_nota"].isoformat() if row["data_hora_nota"] else None,
        "situacao": _texto(row["situacao"]),
        "valorTotal": _numero(row["total_nota"]),
        "chaveAcessoNota": _chave_nfe(row["nfe_chaveacesso"]),
        "chaveAcessoReferenciada": _chave_nfe(row["nfe_chaveacesso_ref"]),
        "clienteCodigo": _texto(row["codigo_exp"]),
        "clienteNome": _texto(row["razao_social"]) or "",
        "clienteCidade": _texto(row["cidade"]),
        "clienteUf": _texto(row["uf"]),
        # O código do funcionário no ERP, o mesmo gravado em
        # `usuarios.sistema_origem_id` por funcionarios.py. Vendedor que não
        # resolve não recusa a nota — a API grava sem vendedor de propósito.
        "vendedorSistemaOrigemId": _texto(row["vendedor"]),
        "transportadoraNome": _texto(row["transportadora_nome"]),
        "termolabil": termolabil,
        "entregaNumeroMapa": str(row["mapadecarga_id"]) if row["mapadecarga_id"] else None,
        "sistemaOrigemId": f"{empresa}-{numero_nota}-{serie}-{pedido}",
        "itens": itens,
    }


# =========================================================
# ROTINA PRINCIPAL
# =========================================================

def _enviar(caminho, payload, descricao):
    """POST no endpoint de integração. Os dois são upsert e respondem 200 —
    qualquer outra coisa é rejeição real e vira RuntimeError."""
    response = requisitar_com_retry(
        "POST",
        f"{BASE_URL}{caminho}",
        obter_token,
        headers_api,
        logger=logger,
        json=payload,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Falha ao enviar {descricao}: {response.status_code} {response.text}"
        )


def sincronizar_entregas(limite=None, desde_data_nota=None, ate_data_nota=None):
    """Busca notas faturadas alteradas e envia mapa e nota para a API.

    O mapa vai ANTES da nota, sempre: `registrar_nota` só amarra o vínculo se o
    mapa já existir aqui. Chegar fora de ordem não perde a nota (ela fica
    "sem mapa" e é costurada quando o mapa chegar), mas mandar na ordem certa
    evita depender disso a cada rodada.

    Erro definitivo num registro propaga como RuntimeError — quem chama decide
    o que fazer (ver app.py, que derruba a aplicação inteira). O checkpoint
    avança nota a nota, na ordem de DATA_HORA_ALTERACAO, nunca pulando à frente
    de um registro que ainda não foi processado com sucesso.

    `limite` corta o lote nas N notas mais antigas da fila. É para execução
    manual — conferir a integração numa amostra pequena antes de soltar o lote
    inteiro. O checkpoint avança normalmente, então a próxima execução continua
    de onde esta parou.

    `desde_data_nota` liga a RECARGA MANUAL: em vez do checkpoint, o corte é
    "toda nota faturada a partir desta data" — para quando alguém precisa de um
    período inteiro na tela agora, sem esperar o ciclo caminhar até lá.
    `ate_data_nota` fecha o período pela outra ponta, e as duas são inclusivas:
    de 01/08 a 21/08 traz o dia 21 também.

    Nesse modo o checkpoint NÃO é gravado, e isso é o ponto: ele continua onde
    estava, e o ciclo automático segue preenchendo o intervalo que ainda falta.
    Se a recarga empurrasse o checkpoint para a frente, tudo que está entre o
    valor antigo e a data pedida seria pulado em silêncio — a integração
    pareceria em dia com um buraco no meio.
    """
    recarga_manual = desde_data_nota is not None
    if ate_data_nota is not None and not recarga_manual:
        raise ValueError(
            "ate_data_nota sozinho não define recarga: informe desde_data_nota."
        )

    with conectar() as connection:
        cursor = connection.cursor()
        try:
            if recarga_manual:
                periodo = (
                    f"de {desde_data_nota} a {ate_data_nota}"
                    if ate_data_nota is not None
                    else f"a partir de {desde_data_nota}"
                )
                logger.info(
                    f"Recarga manual: notas faturadas {periodo} "
                    "(o checkpoint do ciclo automático não será alterado)."
                )
            else:
                maior_data = ler_ultima_data()
                logger.info(f"Última data processada: {maior_data}")

            cursor.execute("ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,'")

            if recarga_manual and ate_data_nota is not None:
                cursor.execute(
                    QUERY_NOTAS_POR_PERIODO,
                    {
                        "data_nota_minima": desde_data_nota,
                        "data_nota_maxima": ate_data_nota,
                    },
                )
            elif recarga_manual:
                cursor.execute(
                    QUERY_NOTAS_POR_DATA, {"data_nota_minima": desde_data_nota}
                )
            else:
                cursor.execute(QUERY_NOTAS, {"maior_data": maior_data})
            colunas = [col[0].lower() for col in cursor.description]
            rows = [dict(zip(colunas, linha)) for linha in cursor.fetchall()]

            if limite is not None:
                rows = rows[:limite]

            if len(rows) == 0:
                logger.info("Nenhuma nota nova/alterada para enviar.")
                return

            logger.info(f"Encontradas {len(rows)} notas para enviar.")

            notas = []
            for row in rows:
                itens_rows = buscar_itens_nota(cursor, row)
                itens_validos = [
                    item for item in itens_rows if item["codigo_pro"] is not None
                ]
                itens = [
                    montar_item_payload(item, numero)
                    for numero, item in enumerate(itens_validos, start=1)
                ]
                # Termolábil é do PRODUTO no ERP e da NOTA aqui: basta um item
                # refrigerado para a carga inteira ter o SLA menor — ela viaja
                # junto, no mesmo veículo.
                termolabil = any(
                    _texto(item["refrigerado"]) == "S" for item in itens_validos
                )
                notas.append((row, itens, termolabil))
        finally:
            cursor.close()

    # O mesmo mapa de carga leva dezenas de notas, e o payload dele é idêntico
    # em todas (sai da mesma linha da consulta). Mandar uma vez por lote e não
    # uma vez por nota economiza a maior parte das chamadas — e cada POST de
    # mapa reprocessa o vínculo de TODAS as notas já penduradas nele.
    mapas_enviados = set()

    for idx, (row, itens, termolabil) in enumerate(notas, start=1):
        identificacao = (
            f"{row['empresa_id']}-{row['numero_nota']}-{row['serie']}-{row['pedido']}"
        )
        mapa_id = row["mapadecarga_id"]

        if mapa_id and (row["empresa_id"], mapa_id) not in mapas_enviados:
            _enviar(
                "/entregas/mapas",
                montar_mapa_payload(row),
                f"mapa de carga '{mapa_id}' da nota '{identificacao}'",
            )
            mapas_enviados.add((row["empresa_id"], mapa_id))

        _enviar(
            "/entregas/notas",
            montar_nota_payload(row, itens, termolabil),
            f"nota '{identificacao}'",
        )
        logger.info(
            f"[{idx}/{len(notas)}] Nota '{identificacao}' enviada com sucesso "
            f"({len(itens)} itens, mapa={mapa_id or 'sem mapa'})."
        )

        # Recarga manual não mexe no checkpoint — ver a docstring.
        if not recarga_manual:
            salvar_ultima_data(row["data_hora_alteracao"])

    logger.info(
        f"Lote processado com sucesso: {len(notas)} notas, "
        f"{len(mapas_enviados)} mapas de carga."
    )


if __name__ == '__main__':
    sincronizar_entregas()
