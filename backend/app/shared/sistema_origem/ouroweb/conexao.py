"""
Conexão com o banco do sistema de origem OUROWEB (SQL Server).

Este é o único arquivo do projeto que abre conexão com o SQL Server. Mesmo
papel do `gestcom/conexao.py` para o Oracle, e do `core/database/conexao.py`
para o MySQL.

**SOMENTE LEITURA.** Não existe aqui equivalente do `executar()` do gestcom, e
isso é proposital: o OuroWeb é base de outro sistema, que não é nosso e não
temos por que alterar. A conexão abre com `autocommit=False` e nada neste
módulo dá commit — se alguém escrever, a transação morre no fecho.

Como no gestcom, não há ORM nem model: o schema é de outro sistema, e mapeá-lo
criaria a ilusão de que podemos mudá-lo. O que existe é SQL explícito, sempre
com bind de parâmetro (`%(nome)s` — o estilo do pymssql).
"""

from contextlib import contextmanager
from typing import Any, Iterator

from app.shared.sistema_origem.ouroweb.config import (
    SqlServerSettings,
    obter_sqlserver_settings,
)


class OuroWebIndisponivel(RuntimeError):
    """Erro de infraestrutura: driver ausente, credencial faltando ou banco
    fora do ar. Quem chama traduz isso para a resposta HTTP — este pacote não
    conhece FastAPI."""


class OuroWebTempoEsgotado(OuroWebIndisponivel):
    """A consulta passou do teto de tempo.

    Separado de `OuroWebIndisponivel` porque a causa e a saída são outras: o
    banco está no ar, a consulta é que foi pesada demais (ou o servidor de
    origem está sob carga). Quem chama traduz para 504 e pede um período
    menor, em vez de dizer "sistema indisponível", que mandaria a pessoa
    esperar por algo que não vai melhorar sozinho.
    """


# Códigos que o DB-Lib usa para timeout de consulta. Vêm dentro da mensagem da
# exceção do pymssql, que não expõe o código de forma estruturada.
_CODIGOS_TIMEOUT = ("20003", "20047", "timed out")


def _traduzir_erro_de_consulta(erro: Exception) -> OuroWebIndisponivel:
    """Transforma qualquer erro do driver numa exceção NOSSA.

    Sem isto, um timeout no meio do `cursor.execute` sobe como
    `pymssql.OperationalError` cru até o FastAPI, que responde 500 com
    traceback — para quem está na tela, "erro interno" quando na verdade a
    consulta foi grande demais.
    """
    texto = str(erro)
    if any(codigo in texto for codigo in _CODIGOS_TIMEOUT):
        return OuroWebTempoEsgotado(
            "A consulta ao sistema de origem passou do tempo limite. "
            "Reduza o período ou use mais filtros."
        )
    return OuroWebIndisponivel(f"Falha ao consultar o OuroWeb: {erro}")


@contextmanager
def conectar(
    settings: SqlServerSettings | None = None, timeout: int | None = None
) -> Iterator[Any]:
    """Abre a conexão e garante o fecho.

    `timeout` sobrescreve o teto de tempo da consulta. A exportação usa um
    valor bem maior que a tela — ver `timeout_exportacao_segundos`."""
    settings = settings or obter_sqlserver_settings()
    if not settings.configurado:
        raise OuroWebIndisponivel(
            "Conexão com o OuroWeb não configurada (OUROWEB_SQLSERVER_HOST, "
            "OUROWEB_SQLSERVER_USER e OUROWEB_SQLSERVER_PASSWORD no .env)."
        )

    try:
        import pymssql
    except ImportError as erro:
        raise OuroWebIndisponivel("Dependência 'pymssql' não instalada.") from erro

    try:
        conexao = pymssql.connect(
            server=settings.host,
            port=str(settings.porta),
            user=settings.user,
            password=settings.password,
            database=settings.database or "",
            # Explícitos porque o default do pymssql é esperar praticamente
            # para sempre: num IP errado a requisição HTTP ficaria pendurada
            # até o cliente desistir, sem nenhum erro no log.
            login_timeout=10,
            timeout=timeout or settings.timeout_consulta_segundos,
            autocommit=False,
        )
    except Exception as erro:  # noqa: BLE001 - qualquer falha aqui é indisponibilidade
        raise OuroWebIndisponivel(f"Não foi possível conectar ao OuroWeb: {erro}") from erro

    try:
        yield conexao
    finally:
        conexao.close()


def buscar_todos(sql: str, parametros: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Roda um SELECT e devolve as linhas como dicts (chave = alias da coluna).

    Devolver dict em vez de tupla é o que permite o SQL viver num arquivo
    `.sql` legível, com aliases em português, sem o service depender da ordem
    das colunas.
    """
    with conectar() as conexao:
        cursor = conexao.cursor(as_dict=True)
        try:
            cursor.execute(sql, parametros or {})
            return cursor.fetchall()
        except OuroWebIndisponivel:
            raise
        except Exception as erro:  # noqa: BLE001 - erro do driver vira erro nosso
            raise _traduzir_erro_de_consulta(erro) from erro
        finally:
            cursor.close()


def buscar_um(sql: str, parametros: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Primeira linha do SELECT como dict, ou None."""
    with conectar() as conexao:
        cursor = conexao.cursor(as_dict=True)
        try:
            cursor.execute(sql, parametros or {})
            return cursor.fetchone()
        except OuroWebIndisponivel:
            raise
        except Exception as erro:  # noqa: BLE001 - erro do driver vira erro nosso
            raise _traduzir_erro_de_consulta(erro) from erro
        finally:
            cursor.close()


def iterar(
    sql: str,
    parametros: dict[str, Any] | None = None,
    tamanho_lote: int = 5_000,
    timeout: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Percorre o resultado em lotes, sem carregar tudo na memória.

    É o que torna a exportação viável. Medido com 98 mil linhas: `fetchall()`
    guarda ~124 MB de dicts e o CSV montado inteiro chega a 181 MB de pico —
    por linha de exportação, num processo que atende todo mundo. Lendo de
    5.000 em 5.000, a memória fica praticamente constante.

    A conexão só fecha quando o gerador termina (ou é descartado). Quem chama
    precisa consumir até o fim, ou fechar — é o que a `StreamingResponse` do
    FastAPI faz naturalmente.
    """
    with conectar(timeout=timeout) as conexao:
        cursor = conexao.cursor(as_dict=True)
        try:
            cursor.execute(sql, parametros or {})
            while True:
                lote = cursor.fetchmany(tamanho_lote)
                if not lote:
                    return
                yield from lote
        except OuroWebIndisponivel:
            raise
        except Exception as erro:  # noqa: BLE001 - erro do driver vira erro nosso
            raise _traduzir_erro_de_consulta(erro) from erro
        finally:
            cursor.close()
