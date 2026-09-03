from sqlalchemy.orm import Session

from app.domains.expedicao_configuracoes.expedicao_configuracao_contrato import (
    ExpedicaoConfiguracaoAtualizarSchema,
)
from app.domains.expedicao_configuracoes.expedicao_configuracao_model import (
    ExpedicaoConfiguracao,
)
from app.shared.sync_helpers import incrementar_versao


def _linha_viva(sessao_db: Session) -> ExpedicaoConfiguracao | None:
    return (
        sessao_db.query(ExpedicaoConfiguracao)
        .filter(ExpedicaoConfiguracao.sync_deleted_at.is_(None))
        .first()
    )


def obter(sessao_db: Session) -> ExpedicaoConfiguracao:
    """A configuração da expedição, materializando os padrões na primeira vez.

    O GET cria a linha quando ela não existe, e isso é deliberado: a alternativa
    seria devolver um objeto de mentira que some quando alguém salva, e o painel
    passaria a exibir um estado que não está em lugar nenhum. Como os valores
    gravados são exatamente os padrões declarados no model, criar aqui não muda
    o comportamento de nada — só dá endereço ao que já valia.

    Não há corrida de verdade a proteger: duas telas abrindo ao mesmo tempo no
    banco vazio criariam duas linhas com o mesmo conteúdo, e a leitura pega a
    primeira. Se isso um dia incomodar, o lugar de resolver é uma coluna
    sentinela com unique, não um lock aqui.
    """
    configuracao = _linha_viva(sessao_db)
    if configuracao is None:
        configuracao = ExpedicaoConfiguracao()
        sessao_db.add(configuracao)
        sessao_db.commit()
        sessao_db.refresh(configuracao)
    return configuracao


def atualizar(
    sessao_db: Session, dados: ExpedicaoConfiguracaoAtualizarSchema
) -> ExpedicaoConfiguracao:
    configuracao = obter(sessao_db)
    for campo, valor in dados.model_dump().items():
        setattr(configuracao, campo, valor)
    incrementar_versao(configuracao)
    sessao_db.commit()
    sessao_db.refresh(configuracao)
    return configuracao
