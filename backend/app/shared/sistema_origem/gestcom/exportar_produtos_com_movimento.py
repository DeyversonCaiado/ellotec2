"""
Gera um CSV do cadastro de produtos do GESTCOM (Oracle), SÓ com os produtos
que têm movimentação.

"Movimentação" é ter pelo menos uma linha em `fat_itemnota` (venda),
`fat_itementradas` (entrada) ou `fat_itempedido` (pedido) — qualquer uma das
três, não as três. Na base atual isso recorta 23.007 produtos para 6.662.

O filtro usa `EXISTS`, não `JOIN`, de propósito: um JOIN com as três tabelas de
item multiplicaria o produto por cada nota, entrada e pedido dele, e o mesmo
produto sairia milhares de vezes. `EXISTS` responde "tem ou não tem" e devolve
uma linha por produto, que é o que um cadastro pede.

As colunas são lidas do cabeçalho de `relacao produtos.csv` para o arquivo novo
sair idêntico ao antigo — mesma ordem, mesmas 252 colunas (a tabela tem 257; as
5 restantes são posteriores àquele dump).

Rodar a partir de `C:\\projetos\\ellotec2\\backend`:

    python -m app.shared.sistema_origem.gestcom.exportar_produtos_com_movimento

Por padrão usa a conexão do `.env` (a mesma da sincronização). Para exportar de
OUTRO servidor Oracle, informe a conexão por variável de ambiente — nunca em
arquivo, que iria para o git:

    EXPORT_ORACLE_DSN=192.168.100.254/ORCL
    EXPORT_ORACLE_USER=...
    EXPORT_ORACLE_PASSWORD=...
    EXPORT_ORACLE_SCHEMA=GESTCOM   (opcional, default GESTCOM)
"""

import csv
import io
import os
import time
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.shared.sistema_origem.gestcom.config import obter_oracle_settings
from app.shared.sistema_origem.gestcom.conexao import conectar as conectar_padrao

@contextmanager
def conectar():
    """A conexão do `.env`, ou a apontada pelas variáveis EXPORT_ORACLE_*.

    O override existe porque o cadastro de produtos vive em mais de um servidor
    do ERP, e exportar de outro não deveria exigir mexer no `.env` da aplicação
    (que é o da sincronização e está em uso). Credencial passa por variável de
    ambiente, nunca por arquivo — arquivo vai para o git.

    Aqui NÃO se chama `BCO_FUNCAO`, que a conexão padrão faz: o SELECT do
    cadastro não depende do contexto do ERP, e servidores mais antigos podem
    não ter a função.
    """
    dsn = os.environ.get("EXPORT_ORACLE_DSN")
    if not dsn:
        with conectar_padrao() as conexao:
            yield conexao
        return

    import oracledb

    diretorio = os.environ.get("EXPORT_ORACLE_CLIENT_DIR") or obter_oracle_settings().oracle_client_dir
    try:
        oracledb.init_oracle_client(lib_dir=diretorio)
    except Exception as erro:  # noqa: BLE001 - já inicializado é caso normal
        if "already been initialized" not in str(erro).lower():
            raise

    conexao = oracledb.connect(
        user=os.environ["EXPORT_ORACLE_USER"],
        password=os.environ["EXPORT_ORACLE_PASSWORD"],
        dsn=dsn,
    )
    try:
        cursor = conexao.cursor()
        try:
            schema = os.environ.get("EXPORT_ORACLE_SCHEMA", "GESTCOM")
            cursor.execute(f"ALTER SESSION SET CURRENT_SCHEMA={schema}")
        finally:
            cursor.close()
        yield conexao
    finally:
        conexao.close()

PASTA = Path(__file__).parent
MODELO = PASTA / "relacao produtos.csv"
def caminho_de_saida() -> Path:
    """Inclui a origem no nome: exportar de dois servidores no mesmo dia
    sobrescreveria o arquivo do outro, e nada no conteúdo diria de onde veio."""
    dsn = os.environ.get("EXPORT_ORACLE_DSN", "")
    origem = dsn.split("/")[0].replace(":", "-") if dsn else "padrao"
    return PASTA / f"produtos com movimento {origem} {datetime.now():%Y-%m-%d}.csv"

# De quantas em quantas linhas o cursor é lido. O cadastro é pequeno (milhares
# de linhas), mas o `arraysize` do oracledb é 100 por padrão — subir reduz
# bastante o número de idas ao banco.
TAMANHO_LOTE = 1_000


def colunas_do_modelo() -> list[str]:
    """As colunas do CSV antigo, na ordem em que estão lá."""
    with io.open(MODELO, encoding="utf-8-sig", errors="replace") as arquivo:
        return [coluna.strip() for coluna in arquivo.readline().strip().split(";") if coluna.strip()]


def montar_sql(colunas: list[str]) -> str:
    selecao = ",\n       ".join(f"p.{coluna}" for coluna in colunas)
    return f"""
SELECT {selecao}
FROM fat_produtos p
WHERE EXISTS (SELECT 1 FROM fat_itemnota     n WHERE n.codigo_pro = p.codigo_pro)
   OR EXISTS (SELECT 1 FROM fat_itementradas e WHERE e.codigo_pro = p.codigo_pro)
   OR EXISTS (SELECT 1 FROM fat_itempedido   i WHERE i.codigo_pro = p.codigo_pro)
ORDER BY p.codigo_pro
"""


def formatar(valor) -> str:
    """Mesmo formato do dump original: decimal com PONTO e data com
    milissegundos. Não é o formato brasileiro de propósito — o arquivo é
    substituto direto do antigo, e mudar a formatação quebraria quem já o lê."""
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d %H:%M:%S.") + f"{valor.microsecond // 1000:03d}"
    if isinstance(valor, Decimal):
        # `normalize` tira zeros à direita (1.000 -> 1); o `+ 0` desfaz a
        # notação científica que o normalize produz em números redondos.
        return str(valor.normalize() + Decimal(0))
    if hasattr(valor, "read"):  # CLOB
        return valor.read() or ""
    return str(valor)


def exportar() -> Path:
    colunas = colunas_do_modelo()
    sql = montar_sql(colunas)
    saida = caminho_de_saida()

    inicio = time.perf_counter()
    with conectar() as conexao:
        cursor = conexao.cursor()
        cursor.arraysize = TAMANHO_LOTE
        try:
            cursor.execute(sql)
            # UTF-8 SEM BOM e quebra CRLF: é exatamente o que o dump original
            # usa, e o arquivo novo precisa ser substituto direto dele.
            # `newline=""` é exigência do módulo csv no Windows; sem isso cada
            # linha sai com uma linha em branco no meio.
            with io.open(saida, "w", encoding="utf-8", newline="") as arquivo:
                escritor = csv.writer(arquivo, delimiter=";", lineterminator="\r\n")
                escritor.writerow(colunas)
                total = 0
                while True:
                    lote = cursor.fetchmany(TAMANHO_LOTE)
                    if not lote:
                        break
                    escritor.writerows([formatar(valor) for valor in linha] for linha in lote)
                    total += len(lote)
        finally:
            cursor.close()

    tamanho = os.path.getsize(saida) / 1024 / 1024
    print(f"{total} produtos | {len(colunas)} colunas | {tamanho:.2f} MB | {time.perf_counter() - inicio:.1f}s")
    print(saida)
    return saida


if __name__ == "__main__":
    exportar()
