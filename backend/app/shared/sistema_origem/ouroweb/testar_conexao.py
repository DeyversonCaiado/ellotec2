"""
Teste de conexão com o SQL Server do OUROWEB.

Não faz parte de nenhuma rotina: é um script de diagnóstico, para responder
"a máquina alcança o banco com estas credenciais?" antes de escrever
qualquer integração. Por isso ele imprime na tela em vez de usar o logger, e
devolve código de saída 1 quando falha (útil em script de deploy).

Rodar a partir de `C:\\projetos\\ellotec2\\backend`:

    python -m app.shared.sistema_origem.ouroweb.testar_conexao

Credenciais vêm do `.env` (prefixo OUROWEB_), mesmo arquivo do resto do
projeto. Ver `config.py` deste pacote.
"""

import sys

import pymssql

from app.shared.sistema_origem.ouroweb.config import obter_sqlserver_settings


def testar_conexao() -> bool:
    """Abre a conexão, pergunta a versão do servidor e fecha. Devolve True se
    tudo funcionou."""
    settings = obter_sqlserver_settings()

    print(f"Conectando em {settings.host}:{settings.porta} como '{settings.user}'...")
    if settings.database:
        print(f"Banco: {settings.database}")

    try:
        # `login_timeout` e `timeout` são explícitos porque o default do pymssql
        # é esperar praticamente para sempre — num IP errado, o script ficaria
        # pendurado sem dizer nada.
        conexao = pymssql.connect(
            server=settings.host,
            port=str(settings.porta),
            user=settings.user,
            password=settings.password,
            database=settings.database or "",
            login_timeout=10,
            timeout=30,
        )
    except Exception as erro:
        print(f"\nFALHOU ao conectar: {type(erro).__name__}: {erro}")
        print(
            "\nSe for timeout, verifique nesta ordem: a máquina alcança o IP "
            "(ping), a porta 1433 está aberta no firewall do servidor, e o "
            "SQL Server está com TCP/IP habilitado no Configuration Manager."
        )
        return False

    try:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT @@VERSION, DB_NAME(), SUSER_NAME()")
            versao, banco, usuario = cursor.fetchone()

        print("\nCONECTOU.")
        print(f"  Banco atual: {banco}")
        print(f"  Logado como: {usuario}")
        print(f"  Versão: {versao.splitlines()[0]}")

        with conexao.cursor() as cursor:
            cursor.execute("SELECT name FROM sys.databases ORDER BY name")
            bancos = [nome for (nome,) in cursor.fetchall()]
        print(f"  Bancos visíveis ({len(bancos)}): {', '.join(bancos)}")

        return True
    except Exception as erro:
        # Conectar e não conseguir consultar é outro problema: credencial ok,
        # permissão não. Vale separar da falha de conexão.
        print(f"\nConectou, mas a consulta falhou: {type(erro).__name__}: {erro}")
        return False
    finally:
        conexao.close()


if __name__ == "__main__":
    sys.exit(0 if testar_conexao() else 1)
