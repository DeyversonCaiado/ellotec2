"""
Registro de alterações no histórico.

Uma função só, de propósito: quem altera algo rastreável chama `registrar` e
segue. Não há leitura ainda porque nenhuma tela lista o histórico — quando
houver, ela entra aqui (ver ARCHITECTURE.md → "abstrai por dor").
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.historico.historico_model import Historico


def registrar(
    sessao_db: Session,
    *,
    empresa_id: str,
    usuario_id: str,
    tabela: str,
    campo: str,
    valor_antigo: str | None,
    valor_novo: str | None,
    tela: str,
    observacao: str | None = None,
) -> Historico:
    """Grava uma linha de histórico. NÃO dá commit.

    O commit é de quem chamou, e isso é deliberado: o histórico precisa entrar
    na mesma transação da operação que ele descreve. Se a operação falhar
    depois, o registro de auditoria não pode sobreviver sozinho dizendo que
    algo mudou quando nada mudou.

    Argumentos são keyword-only porque são oito, quase todos string — posicional
    aqui é troca de parâmetro esperando acontecer.
    """
    linha = Historico(
        empresa_id=empresa_id,
        usuario_id=usuario_id,
        tabela=tabela,
        campo=campo,
        valor_antigo=valor_antigo,
        valor_novo=valor_novo,
        tela=tela,
        observacao=observacao,
        data_alteracao=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    sessao_db.add(linha)
    return linha
