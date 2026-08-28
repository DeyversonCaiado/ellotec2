"""
Importa os dados da Lista de Preços CMED (arquivo .xlsx baixado do site da
Conformidade/CMED) para a tabela `cotacao_tabela_cmed` do MySQL do ELLOTEC
(banco `dashboard`, config lida de C:\\projetos\\ellotec2\\backend\\.env).

A coluna `data_arquivo` (AAAAMMDD) é extraída do próprio nome do arquivo
(ex.: xls_conformidade_gov_20260811_192510234.xlsx -> 20260811), que é a
data em que a tabela de preços foi publicada — não um valor fixo.

Cada execução APAGA os registros já existentes para a mesma data_arquivo
antes de inserir (idempotente por arquivo/data).

Uso:
    cd C:\\projetos\\ello
    python ellotec\\cadastros\\importar_cotacao_cmed.py "C:\\Users\\deyverson.caiado\\Downloads\\xls_conformidade_gov_20260811_192510234.xlsx"
"""
import os
import re
import sys
import traceback

import openpyxl

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

ELLOTEC2_BACKEND_DIR = r"C:\projetos\ellotec2\backend"
if ELLOTEC2_BACKEND_DIR not in sys.path:
    sys.path.insert(0, ELLOTEC2_BACKEND_DIR)

from app.core.settings import Settings  # noqa: E402

_ENV_FILE = os.path.join(ELLOTEC2_BACKEND_DIR, ".env")


def obter_settings():
    return Settings(_env_file=_ENV_FILE)


from sqlalchemy import create_engine, text  # noqa: E402

from core.log import get_logger  # noqa: E402

logger = get_logger("importar_cotacao_cmed")

LINHA_CABECALHO = 54  # linha (1-based) onde estão os nomes das colunas na planilha

COLUNAS = [
    "substancia", "cnpj", "laboratorio", "codigo_ggrem", "registro",
    "ean_1", "ean_2", "ean_3", "produto", "apresentacao",
    "classe_terapeutica", "tipo_de_produto", "regime_de_preco",
    "pf_sem_impostos", "pf_0", "pf_12", "pf_12_alc", "pf_17", "pf_17_alc",
    "pf_17_5", "pf_17_5_alc", "pf_18", "pf_18_alc", "pf_19", "pf_19_alc",
    "pf_19_5", "pf_19_5_alc", "pf_20", "pf_20_alc", "pf_20_5", "pf_20_5_alc",
    "pf_21", "pf_21_alc", "pf_22", "pf_22_alc", "pf_22_5", "pf_22_5_alc",
    "pf_23", "pf_23_alc",
    "pmvg_sem_impostos", "pmvg_0", "pmvg_12", "pmvg_12_alc", "pmvg_17",
    "pmvg_17_alc", "pmvg_17_5", "pmvg_17_5_alc", "pmvg_18", "pmvg_18_alc",
    "pmvg_19", "pmvg_19_alc", "pmvg_19_5", "pmvg_19_5_alc", "pmvg_20",
    "pmvg_20_alc", "pmvg_20_5", "pmvg_20_5_alc", "pmvg_21", "pmvg_21_alc",
    "pmvg_22", "pmvg_22_alc", "pmvg_22_5", "pmvg_22_5_alc", "pmvg_23",
    "pmvg_23_alc",
    "restricao_hospitalar", "cap", "confaz_87", "icms_0", "analise_recursal",
    "lista_concessao_credito_tributario", "comercializacao_2025", "tarja",
    "destinacao_comercial_9",
]

COLUNAS_PRECO = {c for c in COLUNAS if c.startswith("pf_") or c.startswith("pmvg_")}

INSERT_SQL = text(f"""
    INSERT INTO cotacao_tabela_cmed ({', '.join(COLUNAS)}, data_arquivo)
    VALUES ({', '.join(':' + c for c in COLUNAS)}, :data_arquivo)
""")


def extrair_data_arquivo(caminho_arquivo):
    nome = os.path.basename(caminho_arquivo)
    m = re.search(r"(\d{8})", nome)
    if not m:
        raise ValueError(f"Não foi possível extrair a data (AAAAMMDD) do nome do arquivo: {nome}")
    return m.group(1)


def limpar_preco(valor):
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return valor
    texto = str(valor).strip()
    if not texto or texto.replace("-", "").strip() == "":
        return None
    texto = texto.rstrip("*").strip()
    texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def limpar_texto(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    if texto in ("", "    -     ", "-"):
        return None
    return texto


def ler_linhas(caminho_arquivo):
    wb = openpyxl.load_workbook(caminho_arquivo, read_only=True, data_only=True)
    ws = wb.active

    linhas = []
    for row in ws.iter_rows(min_row=LINHA_CABECALHO + 1, values_only=True):
        if row[0] is None:
            continue
        registro = {}
        for idx, nome_coluna in enumerate(COLUNAS):
            valor = row[idx] if idx < len(row) else None
            if nome_coluna in COLUNAS_PRECO:
                registro[nome_coluna] = limpar_preco(valor)
            else:
                registro[nome_coluna] = limpar_texto(valor)
        linhas.append(registro)

    wb.close()
    return linhas


def importar(caminho_arquivo):
    data_arquivo = extrair_data_arquivo(caminho_arquivo)
    logger.info(f"Lendo planilha: {caminho_arquivo} (data_arquivo={data_arquivo})")

    linhas = ler_linhas(caminho_arquivo)
    logger.info(f"{len(linhas)} linhas de produtos encontradas na planilha.")

    settings = obter_settings()
    logger.info(
        f"Destino MySQL: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    )
    mysql_engine = create_engine(settings.database_url)

    TAMANHO_LOTE = 500
    inseridos = 0

    with mysql_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM cotacao_tabela_cmed WHERE data_arquivo = :data_arquivo"),
            {"data_arquivo": data_arquivo},
        )

        lote = []
        for registro in linhas:
            registro["data_arquivo"] = data_arquivo
            lote.append(registro)
            if len(lote) >= TAMANHO_LOTE:
                conn.execute(INSERT_SQL, lote)
                inseridos += len(lote)
                logger.info(f"{inseridos}/{len(linhas)} linhas importadas até agora...")
                lote = []

        if lote:
            conn.execute(INSERT_SQL, lote)
            inseridos += len(lote)

    logger.info(f"Importação concluída. {inseridos} linhas importadas para data_arquivo={data_arquivo}.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python importar_cotacao_cmed.py <caminho_do_arquivo.xlsx>")
        sys.exit(1)

    try:
        importar(sys.argv[1])
    except Exception:
        print(traceback.format_exc())
        logger.error(traceback.format_exc())
