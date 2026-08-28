"""
Traduz a recusa do banco numa mensagem que diz O QUE deu errado.

O handler de `IntegrityError` em `main.py` devolvia sempre a mesma frase:
"Registro referenciado não existe ou viola uma restrição de unicidade." Isso
transforma dois problemas opostos — um id que não existe e um registro
duplicado — na mesma resposta, e quem integra fica sem saber para que lado
olhar. O caso concreto que motivou este arquivo:

    RuntimeError: Falha ao atualizar pedido '0210517':
    422 {"detail":"Registro referenciado não existe ou viola uma restrição
    de unicidade."}

Com a tradução, a mesma falha diz qual constraint reprovou, em quais colunas, e
qual valor foi recusado.

O módulo é do `core/database` porque conhece detalhes do driver e do metadata do
SQLAlchemy — é infraestrutura, não regra de negócio de nenhum domínio.
"""

import re
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.database.conexao import Base

# Códigos de erro do MySQL. São estáveis e documentados; o texto da mensagem
# muda entre versões, por isso o código é a primeira fonte e o regex é o
# complemento.
_MYSQL_DUPLICADO = 1062
_MYSQL_FK_FILHO = 1452  # INSERT/UPDATE apontando para pai inexistente
_MYSQL_FK_PAI = 1451  # DELETE/UPDATE de pai que ainda tem filhos
_MYSQL_NAO_NULO = 1048

_RE_MYSQL_DUPLICADO = re.compile(r"Duplicate entry '(?P<valor>.*)' for key '(?P<chave>[^']+)'")
_RE_MYSQL_FK = re.compile(
    r"CONSTRAINT `(?P<constraint>[^`]+)` FOREIGN KEY \(`(?P<colunas>[^)]+)`\) "
    r"REFERENCES `(?P<tabela_pai>[^`]+)`"
)
_RE_MYSQL_NAO_NULO = re.compile(r"Column '(?P<coluna>[^']+)' cannot be null")

# SQLite (usado nos testes) não tem código numérico — só o texto.
_RE_SQLITE_UNIQUE = re.compile(r"UNIQUE constraint failed: (?P<colunas>.+)")
_RE_SQLITE_NAO_NULO = re.compile(r"NOT NULL constraint failed: (?P<coluna>.+)")


def _colunas_da_constraint(nome: str) -> list[str]:
    """Descobre as colunas de uma constraint pelo nome, lendo o metadata do
    SQLAlchemy.

    O MySQL informa o nome da chave violada, mas não quais colunas a compõem —
    e é justamente isso que a pessoa precisa saber para corrigir o payload.
    Como os models já declaram tudo, a informação está aqui dentro; não custa
    consulta ao banco.
    """
    for tabela in Base.metadata.tables.values():
        for constraint in tabela.constraints:
            if constraint.name == nome:
                return [coluna.name for coluna in constraint.columns]
        for indice in tabela.indexes:
            if indice.name == nome:
                return [coluna.name for coluna in indice.columns]
    return []


def _limpar_nome_chave(chave: str) -> str:
    """O MySQL 8 devolve 'tabela.constraint'; versões antigas, só 'constraint'."""
    return chave.split(".")[-1]


def descrever(exc: IntegrityError) -> dict[str, Any]:
    """Devolve o corpo da resposta 422: `detail` legível + campos estruturados.

    `detail` continua existindo com o mesmo nome porque é o que o front e os
    scripts de integração já leem — as chaves novas são adicionais.
    """
    original = getattr(exc, "orig", None)
    texto = str(original) if original is not None else str(exc)
    codigo = None
    args = getattr(original, "args", None)
    if args and isinstance(args[0], int):
        codigo = args[0]

    # --- Unicidade ---
    achado = _RE_MYSQL_DUPLICADO.search(texto)
    if codigo == _MYSQL_DUPLICADO or achado:
        if achado:
            constraint = _limpar_nome_chave(achado.group("chave"))
            valor = achado.group("valor")
            colunas = _colunas_da_constraint(constraint)
        else:
            constraint, valor, colunas = "", "", []

        detalhe = "Já existe um registro com esse valor."
        if colunas:
            detalhe += f" A combinação de {', '.join(colunas)} precisa ser única."
        if valor:
            detalhe += f" Valor recusado: '{valor}'."
        if constraint:
            detalhe += f" (restrição {constraint})"
        return {
            "detail": detalhe,
            "tipo": "unicidade",
            "restricao": constraint or None,
            "campos": colunas,
            "valor": valor or None,
        }

    achado = _RE_SQLITE_UNIQUE.search(texto)
    if achado:
        # No SQLite vêm as colunas direto, no formato "tabela.coluna, tabela.coluna".
        colunas = [parte.strip().split(".")[-1] for parte in achado.group("colunas").split(",")]
        return {
            "detail": (
                "Já existe um registro com esse valor. A combinação de "
                f"{', '.join(colunas)} precisa ser única."
            ),
            "tipo": "unicidade",
            "restricao": None,
            "campos": colunas,
            "valor": None,
        }

    # --- Chave estrangeira ---
    if codigo in (_MYSQL_FK_FILHO, _MYSQL_FK_PAI) or "foreign key constraint" in texto.lower():
        achado = _RE_MYSQL_FK.search(texto)
        constraint = achado.group("constraint") if achado else None
        colunas = (
            [c.strip().strip("`") for c in achado.group("colunas").split(",")] if achado else []
        )
        tabela_pai = achado.group("tabela_pai") if achado else None

        if codigo == _MYSQL_FK_PAI:
            detalhe = (
                "Este registro não pode ser alterado ou removido porque outros registros "
                "dependem dele."
            )
            if tabela_pai:
                detalhe += f" Dependência declarada em {tabela_pai}."
            tipo = "dependencia"
        else:
            campo = ", ".join(colunas) if colunas else "um dos campos de referência"
            detalhe = f"O campo {campo} aponta para um registro que não existe"
            detalhe += f" em {tabela_pai}." if tabela_pai else "."
            tipo = "referencia_inexistente"

        if constraint:
            detalhe += f" (restrição {constraint})"
        return {
            "detail": detalhe,
            "tipo": tipo,
            "restricao": constraint,
            "campos": colunas,
            "valor": None,
        }

    # --- Campo obrigatório ---
    achado = _RE_MYSQL_NAO_NULO.search(texto) or _RE_SQLITE_NAO_NULO.search(texto)
    if codigo == _MYSQL_NAO_NULO or achado:
        coluna = achado.group("coluna").split(".")[-1] if achado else None
        detalhe = (
            f"O campo {coluna} é obrigatório e veio vazio."
            if coluna
            else "Um campo obrigatório veio vazio."
        )
        return {
            "detail": detalhe,
            "tipo": "campo_obrigatorio",
            "restricao": None,
            "campos": [coluna] if coluna else [],
            "valor": None,
        }

    # --- Não reconhecido ---
    # Devolve o texto do banco em vez de esconder atrás de uma frase genérica:
    # é uma API interna, e quem está integrando precisa de algo para investigar.
    return {
        "detail": f"O banco recusou a operação por violação de integridade: {texto}",
        "tipo": "desconhecido",
        "restricao": None,
        "campos": [],
        "valor": None,
    }
