"""
Testes da tradução de erro de integridade (core/database/erros_integridade.py).

O que se está protegendo aqui é diagnóstico: a mensagem antiga tratava id
inexistente e registro duplicado como a mesma coisa, e quem integra ficava sem
saber para que lado olhar. Cada teste abaixo é um erro real de driver.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import erros_integridade


def _erro(mensagem: str, codigo: int | None = None) -> IntegrityError:
    """Monta um IntegrityError com o mesmo formato que o driver produz:
    `orig.args[0]` é o código numérico no MySQL, e `str(orig)` é o texto."""

    class OrigFalso(Exception):
        pass

    original = OrigFalso(codigo, mensagem) if codigo else OrigFalso(mensagem)
    original.args = (codigo, mensagem) if codigo else (mensagem,)
    return IntegrityError("INSERT ...", {}, original)


class TestUnicidade:
    def test_mysql_diz_a_restricao_as_colunas_e_o_valor(self):
        resultado = erros_integridade.descrever(
            _erro(
                "Duplicate entry '0210517-abc123' for key "
                "'pedidos.uq_pedidos_sistema_origem_id_empresa_id'",
                1062,
            )
        )

        assert resultado["tipo"] == "unicidade"
        assert resultado["restricao"] == "uq_pedidos_sistema_origem_id_empresa_id"
        # As colunas vêm do metadata do SQLAlchemy: o MySQL informa só o nome
        # da chave, e é a combinação de campos que a pessoa precisa corrigir.
        assert resultado["campos"] == ["sistema_origem_id", "empresa_id"]
        assert resultado["valor"] == "0210517-abc123"
        assert "sistema_origem_id" in resultado["detail"]
        assert "0210517-abc123" in resultado["detail"]

    def test_sqlite_extrai_as_colunas_do_proprio_texto(self):
        resultado = erros_integridade.descrever(
            _erro("UNIQUE constraint failed: pedidos.numero, pedidos.empresa_id")
        )
        assert resultado["tipo"] == "unicidade"
        assert resultado["campos"] == ["numero", "empresa_id"]


class TestChaveEstrangeira:
    def test_referencia_inexistente_nomeia_o_campo_e_a_tabela(self):
        resultado = erros_integridade.descrever(
            _erro(
                "Cannot add or update a child row: a foreign key constraint fails "
                "(`dashboard`.`entrega_notas`, CONSTRAINT `entrega_notas_ibfk_3` FOREIGN KEY "
                "(`vendedor_id`) REFERENCES `usuarios` (`id`))",
                1452,
            )
        )

        assert resultado["tipo"] == "referencia_inexistente"
        assert resultado["campos"] == ["vendedor_id"]
        assert "vendedor_id" in resultado["detail"]
        assert "usuarios" in resultado["detail"]

    def test_registro_com_dependentes_e_outro_problema(self):
        """1451 é o oposto de 1452: aqui o registro existe e é usado por
        outros. Tratar os dois com a mesma frase mandava a pessoa procurar um
        id que não estava faltando."""
        resultado = erros_integridade.descrever(
            _erro(
                "Cannot delete or update a parent row: a foreign key constraint fails "
                "(`dashboard`.`pedido_itens`, CONSTRAINT `pedido_itens_ibfk_1` FOREIGN KEY "
                "(`pedido_id`) REFERENCES `pedidos` (`id`))",
                1451,
            )
        )

        assert resultado["tipo"] == "dependencia"
        assert "dependem dele" in resultado["detail"]

    def test_sqlite_sem_detalhe_ainda_identifica_o_tipo(self):
        """O SQLite não diz qual FK falhou. Identificar o TIPO já resolve
        metade da investigação."""
        resultado = erros_integridade.descrever(_erro("FOREIGN KEY constraint failed"))
        assert resultado["tipo"] == "referencia_inexistente"


class TestCampoObrigatorio:
    def test_mysql(self):
        resultado = erros_integridade.descrever(
            _erro("Column 'numero_nota' cannot be null", 1048)
        )
        assert resultado["tipo"] == "campo_obrigatorio"
        assert resultado["campos"] == ["numero_nota"]

    def test_sqlite(self):
        resultado = erros_integridade.descrever(
            _erro("NOT NULL constraint failed: entrega_notas.numero_nota")
        )
        assert resultado["tipo"] == "campo_obrigatorio"
        assert resultado["campos"] == ["numero_nota"]


def test_erro_desconhecido_devolve_o_texto_do_banco():
    """Preferimos vazar o texto do driver a esconder atrás de uma frase
    genérica: é API interna, e sem nenhuma pista ninguém investiga."""
    resultado = erros_integridade.descrever(_erro("algo totalmente novo do driver"))
    assert resultado["tipo"] == "desconhecido"
    assert "algo totalmente novo do driver" in resultado["detail"]


def test_detail_continua_existindo_em_todos_os_casos():
    """`detail` é o que o front e os scripts de integração já leem — as chaves
    novas são adicionais, não substituem."""
    casos = [
        _erro("UNIQUE constraint failed: pedidos.numero"),
        _erro("FOREIGN KEY constraint failed"),
        _erro("NOT NULL constraint failed: pedidos.numero"),
        _erro("outra coisa"),
    ]
    for caso in casos:
        assert erros_integridade.descrever(caso)["detail"]
