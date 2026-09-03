"""
Borda do domínio `expedicao_configuracoes` para os outros domínios.

Só leitura, nenhum `commit()` — ver ARCHITECTURE.md → "Regras de import entre
domínios".

Quem consome hoje é `expedicao_service`, para saber se cada uma das duas regras
da trava de endereçamento deve barrar o pedido ou não.
"""

from sqlalchemy.orm import Session

from app.domains.expedicao_configuracoes.expedicao_configuracao_model import (
    ExpedicaoConfiguracao,
)
from app.shared.contrato_base import ContratoBase


class ParametrosExpedicao(ContratoBase):
    """Contrato próprio da borda — não é o model, não é o schema do router.

    Os dois parâmetros saem juntos de propósito: quem os consome precisa dos
    dois na mesma decisão, e uma função por parâmetro daria duas consultas para
    ler uma linha só.
    """

    permite_conferir_com_divergencia: bool
    permite_conferir_fora_do_multiplo_de_venda: bool


# O padrão de fábrica, e a resposta de um banco em que a linha ainda não existe:
# as duas travas ligadas, que é como a expedição sempre funcionou.
PADRAO = ParametrosExpedicao(
    permite_conferir_com_divergencia=False,
    permite_conferir_fora_do_multiplo_de_venda=False,
)


def obter_parametros(sessao_db: Session) -> ParametrosExpedicao:
    """Os parâmetros da expedição, ou `PADRAO` se ninguém nunca abriu o painel.

    **Não cria a linha.** Ler um parâmetro é leitura, e leitura que grava é
    escrita disfarçada — pior ainda vinda de um `_publico.py`, que por regra não
    dá `commit()` e deixaria a linha pendurada na transação de quem chamou.
    """
    configuracao = (
        sessao_db.query(ExpedicaoConfiguracao)
        .filter(ExpedicaoConfiguracao.sync_deleted_at.is_(None))
        .first()
    )
    if configuracao is None:
        return PADRAO
    return ParametrosExpedicao(
        permite_conferir_com_divergencia=configuracao.permite_conferir_com_divergencia,
        permite_conferir_fora_do_multiplo_de_venda=(
            configuracao.permite_conferir_fora_do_multiplo_de_venda
        ),
    )
