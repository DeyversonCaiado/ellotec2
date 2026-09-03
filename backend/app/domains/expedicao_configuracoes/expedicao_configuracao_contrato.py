from app.shared.contrato_base import ContratoBase


class ExpedicaoConfiguracaoAtualizarSchema(ContratoBase):
    """O que o painel manda. Todo parâmetro é obrigatório no payload: a tela
    manda o estado inteiro do painel, não um campo por vez."""

    permite_conferir_com_divergencia: bool
    permite_conferir_fora_do_multiplo_de_venda: bool


class ExpedicaoConfiguracaoRespostaSchema(ContratoBase):
    """O que a tela lê. Sem `id`: quem consome é um painel de parâmetros, não
    uma listagem — a linha existir ou não é detalhe de armazenamento."""

    permite_conferir_com_divergencia: bool
    permite_conferir_fora_do_multiplo_de_venda: bool
