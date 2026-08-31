"""
Regra de negócio e consultas do domínio Cotações (Inteligência de Mercado).

Este service é diferente de todos os outros do projeto: ele NÃO usa a sessão do
SQLAlchemy nem toca o MySQL. Toda leitura vai para o OuroWeb (SQL Server), por
`app/shared/sistema_origem/ouroweb/conexao.py`.

O acesso é SOMENTE LEITURA — nada é gravado, e nem objeto temporário é criado
no servidor deles. Quando a consulta está lenta, a saída é reescrever o SQL,
nunca criar índice ou tabela de apoio lá. Ver ARCHITECTURE.md → "Domínio de
consulta a banco externo".

Por isso o domínio também não tem `cotacao_model.py`: não existe tabela nossa
para mapear.
"""

import csv
import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterator

from fastapi import HTTPException, status

from app.domains.cotacoes.cotacao_contrato import (
    JANELA_MAXIMA_DIAS,
    ORDENACOES_VALIDAS,
    PER_PAGE_MAXIMO,
    CotacaoEmpresaSchema,
    CotacaoFiltroOpcoesSchema,
    CotacaoFiltrosSchema,
    CotacaoItemSchema,
    CotacaoListaPaginadaSchema,
)
from app.shared.sistema_origem.ouroweb import conexao as ouroweb
from app.shared.sistema_origem.ouroweb.config import obter_sqlserver_settings

# ---------------------------------------------------------------------------
# O SQL
#
# A ORDEM DO JOIN AQUI NÃO É ESTILO, É DESEMPENHO. A primeira versão partia de
# `Tab_CceBionexoPedido` e juntava tudo de uma vez; com `ORDER BY
# dte_DataVencimento` + OFFSET, o SQL Server escolhia um plano que passava de
# 10 MINUTOS. Recortando primeiro os cabeçalhos do período numa CTE — que usa o
# índice de `dte_DataVencimento` — e só então juntando os itens, a mesma
# consulta responde em ~2s. Se mexer nos JOINs, meça de novo.
#
# Todo valor de filtro entra por bind (%(nome)s). Nada é concatenado — exceto a
# coluna de ordenação, que vem de ORDENACOES_VALIDAS (lista fechada).
#
# `ouroweb/cotacoes_bionexo.sql` continua existindo como a versão legível para
# rodar à mão no SQL Server.
# ---------------------------------------------------------------------------

# Recorte do período: só cabeçalho + cadastro + cidade. É o passo barato, e é
# ele que derruba de milhões para milhares as linhas que os itens vão multiplicar.
_CABECALHOS = """
    SELECT cab.fk_int_IdCceBionexoPedido AS ped_id,
           cab.int_IdPdc,
           cab.str_TituloPdc,
           cab.dte_DataVencimento,
           cab.str_NomeHospital,
           cab.str_CnpjHospital,
           cid.Cidade,
           cid.Estado
    FROM Tab_CceBionexoPedidoCabecalho AS cab
    INNER JOIN Tab_Cadastro AS cad ON cad.pk_int_Cadastro = cab.fk_int_Cadastro
    INNER JOIN Cidade       AS cid ON cid.IdCidade        = cad.IdCidade
    {onde_cabecalho}
"""

# Explosão em itens + a empresa (o CNPJ nosso que recebeu a cotação).
_ITENS = """
FROM cabecalhos AS c
INNER JOIN Tab_CceBionexoPedidoItens AS i ON i.fk_int_IdCceBionexoPedido = c.ped_id
INNER JOIN Tab_CceBionexoPedido      AS ped ON ped.pk_int_IdCceBionexoPedido = c.ped_id
LEFT JOIN  Tab_Empresa               AS emp ON emp.IdEmpresa = ped.fk_int_IdEmpresa
{onde_item}
"""

_COLUNAS = """
    c.int_IdPdc                                AS cotacao,
    c.str_TituloPdc                            AS titulo_cotacao,
    c.dte_DataVencimento                       AS data_vencimento,
    c.str_NomeHospital                         AS hospital,
    c.str_CnpjHospital                         AS cnpj_hospital,
    c.Cidade                                   AS cidade,
    c.Estado                                   AS estado,
    ped.fk_int_IdEmpresa                       AS empresa_id,
    emp.NomeFantasia                           AS empresa,
    i.str_CodigoProduto                        AS codigo_produto_hospital,
    i.str_DescricaoProduto                     AS produto_hospital,
    i.cur_Quantidade                           AS quantidade_solicitada,
    i.cur_QuantidadeProdutoVinculado           AS quantidade_respondida,
    i.cur_QuantidadeFaturadaProdutoVinculado   AS quantidade_faturada,
    i.str_UnidadeMedida                        AS unidade,
    i.cur_PrecoUnitario                        AS preco_unitario
"""


# As mesmas colunas de `_COLUNAS`, mas partindo das tabelas diretamente (a
# etapa 2 não usa a CTE). Traz `item_id` a mais, que é como a ordem da etapa 1
# é reposta.
_COLUNAS_POR_ID = """
    cab.int_IdPdc                                AS cotacao,
    cab.str_TituloPdc                            AS titulo_cotacao,
    cab.dte_DataVencimento                       AS data_vencimento,
    cab.str_NomeHospital                         AS hospital,
    cab.str_CnpjHospital                         AS cnpj_hospital,
    cid.Cidade                                   AS cidade,
    cid.Estado                                   AS estado,
    ped.fk_int_IdEmpresa                         AS empresa_id,
    emp.NomeFantasia                             AS empresa,
    i.str_CodigoProduto                          AS codigo_produto_hospital,
    i.str_DescricaoProduto                       AS produto_hospital,
    i.cur_Quantidade                             AS quantidade_solicitada,
    i.cur_QuantidadeProdutoVinculado             AS quantidade_respondida,
    i.cur_QuantidadeFaturadaProdutoVinculado     AS quantidade_faturada,
    i.str_UnidadeMedida                          AS unidade,
    i.cur_PrecoUnitario                          AS preco_unitario,
    i.pk_int_IdCceBionexoPedidoItens             AS item_id
"""


def _condicoes(filtros: CotacaoFiltrosSchema) -> tuple[str, str, dict[str, Any]]:
    """Separa os filtros em dois grupos: os que valem no cabeçalho (entram na
    CTE, recortando cedo) e os que valem no item (entram depois do join).

    Filtro de cabeçalho aplicado tarde é o que fazia a consulta lenta: ele
    precisa reduzir o conjunto ANTES da multiplicação pelos itens.

    Hospital e cidade nulos ficam sempre de fora: linha sem os dois não serve
    para análise de mercado. O INNER JOIN com Tab_Cadastro/Cidade já elimina a
    maior parte (cerca de 23% dos cabeçalhos não têm cadastro com cidade).
    """
    cabecalho = [
        "cab.str_NomeHospital IS NOT NULL",
        "cab.str_NomeHospital <> ''",
    ]
    item: list[str] = []
    parametros: dict[str, Any] = {}

    if filtros.por_cotacao:
        # Busca por número: o PERÍODO NÃO ENTRA. Quem digita o número da
        # cotação não sabe em que data ela vence, e aplicar o período faria a
        # busca responder "não achei" para uma cotação que existe. O índice de
        # `int_IdPdc` torna essa consulta barata mesmo sem recorte de data.
        cabecalho.append("cab.int_IdPdc = %(cotacao)s")
        parametros["cotacao"] = filtros.cotacao
    else:
        cabecalho.insert(0, "cab.dte_DataVencimento < DATEADD(day, 1, %(data_fim)s)")
        cabecalho.insert(0, "cab.dte_DataVencimento >= %(data_inicio)s")
        parametros["data_inicio"] = filtros.data_inicio
        parametros["data_fim"] = filtros.data_fim

    if filtros.hospital:
        cabecalho.append("cab.str_NomeHospital LIKE %(hospital)s")
        parametros["hospital"] = f"%{filtros.hospital}%"

    if filtros.cidade:
        cabecalho.append("cid.Cidade LIKE %(cidade)s")
        parametros["cidade"] = f"%{filtros.cidade}%"

    if filtros.estado:
        cabecalho.append("cid.Estado = %(estado)s")
        parametros["estado"] = filtros.estado

    if filtros.termo:
        # Busca no que a tela mostra como identificação do item: a descrição do
        # produto pelo nome do hospital, e o código dele. LIKE com % na frente
        # não usa índice — por isso o período é obrigatório e limitado.
        item.append(
            "(i.str_DescricaoProduto LIKE %(termo)s OR i.str_CodigoProduto LIKE %(termo)s)"
        )
        parametros["termo"] = f"%{filtros.termo}%"

    if filtros.empresa_id:
        item.append("ped.fk_int_IdEmpresa = %(empresa_id)s")
        parametros["empresa_id"] = filtros.empresa_id

    if filtros.situacao == "respondidas":
        item.append("i.cur_QuantidadeProdutoVinculado > 0")
    elif filtros.situacao == "nao_respondidas":
        item.append(
            "(i.cur_QuantidadeProdutoVinculado IS NULL OR i.cur_QuantidadeProdutoVinculado = 0)"
        )

    onde_cabecalho = "WHERE " + "\n      AND ".join(cabecalho)
    onde_item = ("WHERE " + "\n  AND ".join(item)) if item else ""
    return onde_cabecalho, onde_item, parametros


def _montar(filtros: CotacaoFiltrosSchema, selecao: str, final: str = "") -> tuple[str, dict]:
    onde_cabecalho, onde_item, parametros = _condicoes(filtros)
    sql = (
        "WITH cabecalhos AS ("
        + _CABECALHOS.format(onde_cabecalho=onde_cabecalho)
        + ")\nSELECT "
        + selecao
        + _ITENS.format(onde_item=onde_item)
        + final
    )
    return sql, parametros


def _validar_filtros(filtros: CotacaoFiltrosSchema) -> None:
    """Período obrigatório e limitado a 90 dias — a menos que a busca seja por
    número de cotação, que dispensa a data.

    Sem período a consulta varre a base inteira (dezenas de milhões de linhas)
    e segura o worker até o timeout. A regra é a MESMA na tela e na exportação:
    o CSV não guarda tudo na memória (vai em streaming), mas a consulta no SQL
    Server continua custando igual.
    """
    if filtros.por_cotacao:
        return
    # O contrato já garante que os dois existem quando não há cotação.
    data_inicio, data_fim = filtros.data_inicio, filtros.data_fim
    assert data_inicio is not None and data_fim is not None
    if data_fim < data_inicio:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A data final não pode ser anterior à data inicial.",
        )
    if data_fim - data_inicio > timedelta(days=JANELA_MAXIMA_DIAS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"O período não pode passar de {JANELA_MAXIMA_DIAS} dias.",
        )



# ---------------------------------------------------------------------------
# Paginação em DUAS ETAPAS (deferred join)
#
# POR QUE NÃO UMA CONSULTA SÓ. A versão anterior selecionava todas as colunas e
# ordenava com OFFSET/FETCH numa tacada. Medido: `COUNT(*)` sobre exatamente os
# mesmos joins levava 0,3s, e a mesma página levava 69 SEGUNDOS — duas vezes
# seguidas, não foi oscilação de carga.
#
# A diferença é o que o ORDER BY tem que carregar: para devolver 50 linhas
# ordenadas, o SQL Server precisava materializar e ordenar as ~220 mil linhas
# do período JUNTO COM as colunas de texto largo (`str_DescricaoProduto` tem
# 1500 caracteres, `str_NomeHospital` 150). Isso vai para disco — e o servidor
# do OuroWeb é I/O-bound (`PAGEIOLATCH_SH` é a maior espera acumulada dele).
#
# Ordenando só as CHAVES e buscando o texto depois, para 50 ids: 6 segundos.
# É o padrão conhecido como "deferred join" e existe exatamente para isto.
#
# Se algum dia isso for reunido numa consulta só, MEÇA — a conta volta.
# ---------------------------------------------------------------------------


def _linhas_por_id(item_ids: list[int]) -> list[dict[str, Any]]:
    """As colunas completas dos itens informados, sem ORDER BY.

    A ordem é reposta em Python a partir da etapa 1 — pedir ao banco para
    ordenar de novo traria de volta o custo que as duas etapas evitam.

    Os ids entram no SQL por bind, um parâmetro por id. São inteiros vindos do
    próprio banco e já convertidos com `int()`, mas o bind é mantido porque a
    regra do projeto é que nada de fora seja concatenado em SQL.
    """
    if not item_ids:
        return []

    marcadores = ", ".join(f"%(id_{indice})s" for indice in range(len(item_ids)))
    parametros = {f"id_{indice}": valor for indice, valor in enumerate(item_ids)}

    sql = f"""
    SELECT {_COLUNAS_POR_ID}
    FROM Tab_CceBionexoPedidoItens AS i
    INNER JOIN Tab_CceBionexoPedido           AS ped ON ped.pk_int_IdCceBionexoPedido = i.fk_int_IdCceBionexoPedido
    INNER JOIN Tab_CceBionexoPedidoCabecalho  AS cab ON cab.fk_int_IdCceBionexoPedido = i.fk_int_IdCceBionexoPedido
    INNER JOIN Tab_Cadastro                   AS cad ON cad.pk_int_Cadastro = cab.fk_int_Cadastro
    INNER JOIN Cidade                         AS cid ON cid.IdCidade = cad.IdCidade
    LEFT JOIN  Tab_Empresa                    AS emp ON emp.IdEmpresa = ped.fk_int_IdEmpresa
    WHERE i.pk_int_IdCceBionexoPedidoItens IN ({marcadores})
    """
    linhas = ouroweb.buscar_todos(sql, parametros)

    # Repõe a ordem da etapa 1. O `IN` não garante ordem nenhuma, e sem isto a
    # página apareceria embaralhada mesmo com o ORDER BY certo lá atrás.
    por_id = {int(linha["item_id"]): linha for linha in linhas}
    return [por_id[item_id] for item_id in item_ids if item_id in por_id]


def listar(
    filtros: CotacaoFiltrosSchema,
    page: int = 1,
    per_page: int = 50,
    sort: str = "dataVencimento",
    sort_type: str = "desc",
) -> CotacaoListaPaginadaSchema:
    """Uma página de itens de cotação do Bionexo.

    A paginação é resolvida no SQL Server (OFFSET/FETCH), nunca em Python: são
    8 GB de dados, e trazer tudo para recortar aqui estouraria a memória do
    worker no primeiro acesso.
    """
    _validar_filtros(filtros)

    page = max(page, 1)
    per_page = min(max(per_page, 1), PER_PAGE_MAXIMO)

    coluna = ORDENACOES_VALIDAS.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ordenação inválida. Use uma destas: {', '.join(ORDENACOES_VALIDAS)}.",
        )
    direcao = "DESC" if sort_type.lower() == "desc" else "ASC"

    sql_total, parametros = _montar(filtros, "COUNT(*) AS total")
    linha_total = ouroweb.buscar_um(sql_total, parametros)
    total = int(linha_total["total"]) if linha_total else 0

    # ETAPA 1 — descobrir QUAIS 50 linhas são a página, carregando só as chaves.
    #
    # O desempate pela PK do item é obrigatório com OFFSET/FETCH: sem uma ordem
    # total, o SQL Server pode devolver a mesma linha em duas páginas e omitir
    # outra.
    sql_chaves, _ = _montar(
        filtros,
        f"{coluna} AS chave_ordem, i.pk_int_IdCceBionexoPedidoItens AS item_id",
        f"""
ORDER BY {coluna} {direcao}, i.pk_int_IdCceBionexoPedidoItens ASC
OFFSET %(offset)s ROWS FETCH NEXT %(limite)s ROWS ONLY
""",
    )
    chaves = ouroweb.buscar_todos(
        sql_chaves,
        {**parametros, "offset": (page - 1) * per_page, "limite": per_page},
    )
    if not chaves:
        return CotacaoListaPaginadaSchema(
            items=[], total=total, page=page, per_page=per_page, sort=sort, sort_type=direcao.lower()
        )

    # ETAPA 2 — buscar as colunas largas SÓ dessas 50 linhas.
    linhas = _linhas_por_id([int(chave["item_id"]) for chave in chaves])

    return CotacaoListaPaginadaSchema(
        items=[CotacaoItemSchema(**{c: v for c, v in linha.items() if c != 'item_id'}) for linha in linhas],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=direcao.lower(),
    )


def listar_opcoes_de_filtro() -> CotacaoFiltroOpcoesSchema:
    """Estados e empresas para os selects da tela.

    Vem de consulta própria e não da página carregada, senão o select ofereceria
    só o que por acaso apareceu na página 1.
    """
    estados = ouroweb.buscar_todos(
        """
        SELECT DISTINCT cid.Estado AS estado
        FROM Cidade AS cid
        WHERE cid.Estado IS NOT NULL AND cid.Estado <> ''
        ORDER BY cid.Estado
        """
    )
    empresas = ouroweb.buscar_todos(
        """
        SELECT emp.IdEmpresa AS id, emp.NomeFantasia AS nome
        FROM Tab_Empresa AS emp
        WHERE emp.NomeFantasia IS NOT NULL
        ORDER BY emp.NomeFantasia
        """
    )
    return CotacaoFiltroOpcoesSchema(
        estados=[linha["estado"] for linha in estados],
        empresas=[CotacaoEmpresaSchema(**linha) for linha in empresas],
    )


# ---------------------------------------------------------------------------
# Exportação CSV
# ---------------------------------------------------------------------------

# Cabeçalho do CSV: nome legível -> chave devolvida pela consulta. A ordem
# aqui é a ordem das colunas no arquivo.
COLUNAS_CSV: dict[str, str] = {
    "Cotação": "cotacao",
    "Título": "titulo_cotacao",
    "Vencimento": "data_vencimento",
    "Hospital": "hospital",
    "CNPJ do hospital": "cnpj_hospital",
    "Cidade": "cidade",
    "UF": "estado",
    "Empresa": "empresa",
    "Código no hospital": "codigo_produto_hospital",
    "Produto": "produto_hospital",
    "Qtd. solicitada": "quantidade_solicitada",
    "Qtd. respondida": "quantidade_respondida",
    "Qtd. faturada": "quantidade_faturada",
    "Unidade": "unidade",
    "Preço unitário": "preco_unitario",
}

# De quantas em quantas linhas o cursor é lido. 5.000 é o equilíbrio entre
# número de idas ao banco e memória por lote.
TAMANHO_LOTE = 5_000


def _formatar(valor: Any) -> str:
    """Formato brasileiro, porque o destino é o Excel em português: data
    dd/mm/aaaa e decimal com vírgula. Sem isso o Excel lê 2.5 como data e
    1/2/2026 como texto."""
    if valor is None:
        return ""
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, Decimal):
        return f"{valor:.4f}".replace(".", ",")
    return str(valor)


def exportar_csv(filtros: CotacaoFiltrosSchema, sort: str = "dataVencimento", sort_type: str = "desc") -> Iterator[str]:
    """Gera o CSV em pedaços, à medida que lê o banco.

    NÃO monta o arquivo inteiro na memória. Medido com 98 mil linhas (empresa
    de Brasília, DF, do início do ano): `fetchall()` + CSV montado chegava a
    181 MB de pico num processo que atende todos os usuários. Em streaming a
    memória fica praticamente constante, e o download começa em segundos em vez
    de esperar a consulta inteira.

    O separador é `;` e o arquivo sai com BOM: é o que faz o Excel em português
    abrir o arquivo já com as colunas separadas e os acentos certos.
    """
    _validar_filtros(filtros)

    coluna = ORDENACOES_VALIDAS.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ordenação inválida. Use uma destas: {', '.join(ORDENACOES_VALIDAS)}.",
        )
    direcao = "DESC" if sort_type.lower() == "desc" else "ASC"

    sql, parametros = _montar(
        filtros,
        _COLUNAS,
        f"\nORDER BY {coluna} {direcao}, i.pk_int_IdCceBionexoPedidoItens ASC\n",
    )

    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")

    def despejar() -> str:
        conteudo = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return conteudo

    # BOM: sem ele o Excel abre o arquivo em ANSI e os acentos viram lixo.
    yield "\ufeff"

    escritor.writerow(list(COLUNAS_CSV))
    yield despejar()

    tempo_maximo = obter_sqlserver_settings().timeout_exportacao_segundos
    for linha in ouroweb.iterar(sql, parametros, TAMANHO_LOTE, timeout=tempo_maximo):
        escritor.writerow([_formatar(linha.get(chave)) for chave in COLUNAS_CSV.values()])
        # Um yield por linha manda pedaços pequenos demais e gasta mais em
        # overhead de rede do que economiza em memória; deixar acumular o
        # buffer e despejar a cada lote seria pior para o tempo até o primeiro
        # byte. Uma linha por vez, com o buffer zerado, é o meio termo simples.
        yield despejar()
