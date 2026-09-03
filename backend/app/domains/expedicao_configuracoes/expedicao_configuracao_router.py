from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.expedicao_configuracoes import expedicao_configuracao_service
from app.domains.expedicao_configuracoes.expedicao_configuracao_contrato import (
    ExpedicaoConfiguracaoAtualizarSchema,
    ExpedicaoConfiguracaoRespostaSchema,
)
from app.domains.expedicao_configuracoes.expedicao_configuracao_model import (
    ExpedicaoConfiguracao,
)
from app.shared.router_base import RouterBase

router = RouterBase(prefix="/expedicao-configuracoes", tags=["Configurações da expedição"])


def _para_resposta(
    configuracao: ExpedicaoConfiguracao,
) -> ExpedicaoConfiguracaoRespostaSchema:
    return ExpedicaoConfiguracaoRespostaSchema(
        permite_conferir_com_divergencia=configuracao.permite_conferir_com_divergencia,
        permite_conferir_fora_do_multiplo_de_venda=(
            configuracao.permite_conferir_fora_do_multiplo_de_venda
        ),
    )


# Sem `{id}` na URL de propósito: a configuração da expedição é uma só, e um id
# na rota convidaria a tratar como coleção o que é um registro único.
@router.get(
    "",
    response_model=ExpedicaoConfiguracaoRespostaSchema,
    summary="Obtém os parâmetros da expedição",
)
def obter(
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("expedicao_configuracoes.acessar")),
) -> ExpedicaoConfiguracaoRespostaSchema:
    return _para_resposta(expedicao_configuracao_service.obter(sessao_db))


@router.put(
    "",
    response_model=ExpedicaoConfiguracaoRespostaSchema,
    summary="Atualiza os parâmetros da expedição",
)
def atualizar(
    dados: ExpedicaoConfiguracaoAtualizarSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(
        exigir_permissao("expedicao_configuracoes.gravar.editar")
    ),
) -> ExpedicaoConfiguracaoRespostaSchema:
    return _para_resposta(expedicao_configuracao_service.atualizar(sessao_db, dados))
