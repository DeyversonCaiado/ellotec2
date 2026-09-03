"""O parâmetro que liga e desliga a trava de endereçamento da expedição.

O que estes testes protegem é o padrão de fábrica: banco sem a linha e linha
recém-criada precisam responder `False` — a trava ligada, como a expedição
sempre funcionou. Um dia em que alguém trocar o default do model sem perceber,
todo o galpão passa a aceitar pedido com divergência em silêncio, e isso só
apareceria numa separação errada semanas depois.
"""

from sqlalchemy.orm import Session

from app.domains.expedicao_configuracoes import (
    expedicao_configuracao_publico,
    expedicao_configuracao_service,
)
from app.domains.expedicao_configuracoes.expedicao_configuracao_publico import (
    ParametrosExpedicao,
)
from app.domains.expedicao_configuracoes.expedicao_configuracao_contrato import (
    ExpedicaoConfiguracaoAtualizarSchema,
)
from app.domains.expedicao_configuracoes.expedicao_configuracao_model import (
    ExpedicaoConfiguracao,
)


def test_sem_linha_no_banco_as_duas_travas_estao_ligadas(sessao_db: Session) -> None:
    parametros = expedicao_configuracao_publico.obter_parametros(sessao_db)

    assert parametros.permite_conferir_com_divergencia is False
    assert parametros.permite_conferir_fora_do_multiplo_de_venda is False


def test_a_leitura_da_borda_nao_cria_linha(sessao_db: Session) -> None:
    """Ler parâmetro é leitura. Se a borda criasse a linha, ela estaria
    gravando dentro da transação de quem chamou — e um `_publico.py` não
    commita nada."""
    expedicao_configuracao_publico.obter_parametros(sessao_db)

    assert sessao_db.query(ExpedicaoConfiguracao).count() == 0


def test_obter_materializa_a_linha_com_o_padrao(sessao_db: Session) -> None:
    configuracao = expedicao_configuracao_service.obter(sessao_db)

    assert configuracao.permite_conferir_com_divergencia is False
    assert configuracao.permite_conferir_fora_do_multiplo_de_venda is False
    assert sessao_db.query(ExpedicaoConfiguracao).count() == 1


def test_obter_duas_vezes_nao_duplica_a_linha(sessao_db: Session) -> None:
    primeira = expedicao_configuracao_service.obter(sessao_db)
    segunda = expedicao_configuracao_service.obter(sessao_db)

    assert primeira.id == segunda.id
    assert sessao_db.query(ExpedicaoConfiguracao).count() == 1


def test_marcar_um_parametro_nao_marca_o_outro(sessao_db: Session) -> None:
    """O ponto da separação: os dois parâmetros governam regras diferentes, e
    ligar um não pode arrastar o outro junto."""
    expedicao_configuracao_service.atualizar(
        sessao_db,
        ExpedicaoConfiguracaoAtualizarSchema(
            permite_conferir_com_divergencia=True,
            permite_conferir_fora_do_multiplo_de_venda=False,
        ),
    )

    parametros = expedicao_configuracao_publico.obter_parametros(sessao_db)
    assert parametros.permite_conferir_com_divergencia is True
    assert parametros.permite_conferir_fora_do_multiplo_de_venda is False


def test_desmarcar_volta_a_travar(sessao_db: Session) -> None:
    expedicao_configuracao_service.atualizar(
        sessao_db,
        ExpedicaoConfiguracaoAtualizarSchema(
            permite_conferir_com_divergencia=True,
            permite_conferir_fora_do_multiplo_de_venda=True,
        ),
    )
    expedicao_configuracao_service.atualizar(
        sessao_db,
        ExpedicaoConfiguracaoAtualizarSchema(
            permite_conferir_com_divergencia=False,
            permite_conferir_fora_do_multiplo_de_venda=False,
        ),
    )

    parametros = expedicao_configuracao_publico.obter_parametros(sessao_db)
    assert parametros.permite_conferir_com_divergencia is False
    assert parametros.permite_conferir_fora_do_multiplo_de_venda is False
    assert sessao_db.query(ExpedicaoConfiguracao).count() == 1


# --------------------------------------------------------------------------
# O efeito de cada parâmetro na regra que ele governa.
#
# Aqui não passa banco: `_bloqueio_do_item` é função pura sobre o endereçamento
# já resolvido, e é ela que os cinco consumidores atravessam.
# --------------------------------------------------------------------------
from decimal import Decimal  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from app.domains.expedicao.expedicao_contrato import EnderecoItemSchema  # noqa: E402
from app.domains.expedicao.expedicao_service import _bloqueio_do_item  # noqa: E402

TUDO_TRAVADO = ParametrosExpedicao(
    permite_conferir_com_divergencia=False,
    permite_conferir_fora_do_multiplo_de_venda=False,
)

# O pedido pede 60 e os endereços somam 42 — falta mercadoria endereçada.
_ITEM_60 = SimpleNamespace(quantidade=60)
_ENDERECOS_42 = [
    EnderecoItemSchema(endereco_id="e1", descricao="07-14-08", quantidade=24.0),
    EnderecoItemSchema(endereco_id="e2", descricao="07-15-02", quantidade=18.0),
]

# O pedido pede 12 e há 19 endereçadas — saldo sobra, mas 19 não fecha em
# caixa de 12. Só a segunda regra reprova este caso.
_ITEM_12 = SimpleNamespace(quantidade=12)
_ENDERECOS_19 = [EnderecoItemSchema(endereco_id="e3", descricao="07-16-01", quantidade=19.0)]


def _saldo(enderecos: list[EnderecoItemSchema]) -> Decimal:
    return sum((Decimal(str(e.quantidade)) for e in enderecos), Decimal(0))


def test_com_tudo_travado_o_saldo_insuficiente_reprova() -> None:
    bloqueio = _bloqueio_do_item(
        _ITEM_60, _ENDERECOS_42, _saldo(_ENDERECOS_42), 1, TUDO_TRAVADO
    )

    assert bloqueio is not None
    assert "Endereçamento insuficiente" in bloqueio


def test_com_tudo_travado_o_endereco_fora_do_multiplo_reprova() -> None:
    bloqueio = _bloqueio_do_item(
        _ITEM_12, _ENDERECOS_19, _saldo(_ENDERECOS_19), 12, TUDO_TRAVADO
    )

    assert bloqueio is not None
    assert "múltiplo de 12" in bloqueio


def test_liberar_o_saldo_nao_libera_o_multiplo() -> None:
    """A razão de serem dois parâmetros: quem convive com endereçamento
    incompleto não passa a conviver com saldo quebrado na prateleira."""
    parametros = ParametrosExpedicao(
        permite_conferir_com_divergencia=True,
        permite_conferir_fora_do_multiplo_de_venda=False,
    )

    assert (
        _bloqueio_do_item(_ITEM_60, _ENDERECOS_42, _saldo(_ENDERECOS_42), 1, parametros)
        is None
    )
    assert (
        _bloqueio_do_item(_ITEM_12, _ENDERECOS_19, _saldo(_ENDERECOS_19), 12, parametros)
        is not None
    )


def test_liberar_o_multiplo_nao_libera_o_saldo() -> None:
    parametros = ParametrosExpedicao(
        permite_conferir_com_divergencia=False,
        permite_conferir_fora_do_multiplo_de_venda=True,
    )

    assert (
        _bloqueio_do_item(_ITEM_12, _ENDERECOS_19, _saldo(_ENDERECOS_19), 12, parametros)
        is None
    )
    assert (
        _bloqueio_do_item(_ITEM_60, _ENDERECOS_42, _saldo(_ENDERECOS_42), 1, parametros)
        is not None
    )


def test_regra_desligada_nao_deixa_bloqueio_pela_metade() -> None:
    """`bloqueio` preenchido significa "não pode iniciar" em todo o resto do
    código e do front. Regra desligada devolve None, não um texto de aviso."""
    parametros = ParametrosExpedicao(
        permite_conferir_com_divergencia=True,
        permite_conferir_fora_do_multiplo_de_venda=True,
    )

    assert (
        _bloqueio_do_item(_ITEM_60, _ENDERECOS_42, _saldo(_ENDERECOS_42), 12, parametros)
        is None
    )
