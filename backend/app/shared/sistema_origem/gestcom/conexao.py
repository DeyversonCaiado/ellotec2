"""
Conexão com o banco do sistema de origem (Oracle do ERP).

Este é o único arquivo do projeto que abre conexão com o Oracle. Qualquer
rotina que precise ler ou escrever lá passa por aqui — é o mesmo papel que
`core/database/conexao.py` cumpre para o MySQL.

Diferente do MySQL, aqui não há ORM nem model: o schema é de outro sistema, não
é nosso, e mapeá-lo criaria a ilusão de que podemos mudá-lo. O que existe é SQL
explícito, sempre com bind de parâmetro.
"""

import platform
from contextlib import contextmanager
from typing import Any, Iterator

from app.shared.sistema_origem.gestcom.config import OracleSettings, obter_oracle_settings


class OracleIndisponivel(RuntimeError):
    """Erro de infraestrutura: driver ausente, credencial faltando ou banco
    fora do ar. Quem chama traduz isso para a resposta HTTP — este pacote não
    conhece FastAPI."""


def _iniciar_client(diretorio: str) -> None:
    """Liga o modo thick. Não é opcional: o servidor do ERP é antigo demais
    para o modo thin, que recusa a conexão com DPY-3010. Sem `diretorio`, o
    caminho certo é falhar aqui com uma mensagem que aponta para o .env — e
    não deixar o driver tentar thin e errar com outra coisa.

    O `diretorio` normalmente vem de `settings.client_dir_efetivo`, que
    descobre o caminho pelo sistema operacional. Ver `config.py`.
    """
    if not diretorio:
        raise OracleIndisponivel(
            f"Não há Instant Client conhecido para o sistema '{platform.system()}' e "
            "ELLOTEC_ORACLE_CLIENT_DIR não foi preenchido. O Oracle do ERP exige o "
            "Instant Client (modo thick) — o modo thin não conecta neste servidor."
        )
    import oracledb

    try:
        oracledb.init_oracle_client(lib_dir=diretorio)
    except Exception as erro:  # noqa: BLE001 - já inicializado é caso normal
        # `init_oracle_client` levanta se chamado duas vezes no mesmo processo.
        # Com --reload isso acontece o tempo todo, e não é problema.
        if "already been initialized" not in str(erro).lower():
            raise OracleIndisponivel(
                f"Não foi possível inicializar o Oracle Instant Client em '{diretorio}' "
                f"(sistema: {platform.system()}): {erro}. Se o caminho for de outro "
                "sistema operacional, apague ELLOTEC_ORACLE_CLIENT_DIR do .env — sem "
                "ele o diretório é descoberto pelo próprio sistema."
            ) from erro


@contextmanager
def conectar(settings: OracleSettings | None = None) -> Iterator[Any]:
    """Abre a conexão, ajusta o schema e o contexto do ERP, e garante o fecho.

    O `ALTER SESSION` e o `CALL` não são enfeite: sem eles a sessão não enxerga
    as tabelas do ERP, e todo SELECT/UPDATE falha com "table or view does not
    exist" — um erro que não parece ter relação com configuração.
    """
    settings = settings or obter_oracle_settings()
    if not settings.configurado:
        raise OracleIndisponivel(
            "Conexão com o sistema de origem não configurada (ELLOTEC_ORACLE_USER, "
            "ELLOTEC_ORACLE_PASSWORD, ELLOTEC_ORACLE_DSN e ELLOTEC_ORACLE_CLIENT_DIR no .env)."
        )

    try:
        import oracledb
    except ImportError as erro:
        raise OracleIndisponivel("Dependência 'oracledb' não instalada.") from erro

    _iniciar_client(settings.client_dir_efetivo)

    try:
        conexao = oracledb.connect(
            user=settings.oracle_user,
            password=settings.oracle_password,
            dsn=settings.oracle_dsn,
        )
    except Exception as erro:  # noqa: BLE001 - qualquer falha aqui é indisponibilidade
        raise OracleIndisponivel(f"Não foi possível conectar ao sistema de origem: {erro}") from erro

    try:
        cursor = conexao.cursor()
        try:
            cursor.execute(f"ALTER SESSION SET CURRENT_SCHEMA={settings.oracle_schema}")
            cursor.execute("CALL BCO_FUNCAO(:funcao)", {"funcao": settings.oracle_funcao_contexto})
        finally:
            cursor.close()
        yield conexao
    finally:
        conexao.close()


def buscar_um(sql: str, parametros: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Primeira linha do SELECT como dict de colunas em minúsculo, ou None."""
    with conectar() as conexao:
        cursor = conexao.cursor()
        try:
            cursor.execute(sql, parametros or {})
            linha = cursor.fetchone()
            if linha is None:
                return None
            colunas = [descricao[0].lower() for descricao in cursor.description]
            return dict(zip(colunas, linha))
        finally:
            cursor.close()


def executar(sql: str, parametros: dict[str, Any] | None = None) -> int:
    """Roda um comando de escrita e devolve quantas linhas foram afetadas.

    Faz `commit` — o Oracle não tem autocommit por padrão, e sem isso o UPDATE
    é descartado no fecho da conexão sem erro nenhum, que é o tipo de bug que
    some em teste e aparece em produção.
    """
    with conectar() as conexao:
        cursor = conexao.cursor()
        try:
            cursor.execute(sql, parametros or {})
            afetadas = cursor.rowcount
            conexao.commit()
            return afetadas
        finally:
            cursor.close()
