"""
Contratos do domínio Cotações (Inteligência de Mercado).

Só existe saída: o domínio é de consulta. Não há schema de criação nem de
edição porque não há nada para gravar — os dados são do OuroWeb, banco de outro
sistema, lido em modo somente leitura.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.shared.contrato_base import ContratoBase

# Recorte por estado de resposta da cotação. "respondida" é o item que já tem
# quantidade vinculada por nós; é assim que o OuroWeb marca o que foi cotado.
SituacaoResposta = Literal["todas", "respondidas", "nao_respondidas"]

# Colunas pelas quais a tela pode ordenar. Lista fechada de propósito: `sort`
# vem da URL e vira nome de coluna no SQL — aceitar texto livre seria injeção.
# Os aliases (`c.`, `i.`, `emp.`) são os da consulta montada em
# cotacao_service.py; mexer lá exige mexer aqui.
ORDENACOES_VALIDAS: dict[str, str] = {
    "dataVencimento": "c.dte_DataVencimento",
    "cotacao": "c.int_IdPdc",
    "hospital": "c.str_NomeHospital",
    "cidade": "c.Cidade",
    "estado": "c.Estado",
    "empresa": "emp.NomeFantasia",
    "produto": "i.str_DescricaoProduto",
    "quantidadeSolicitada": "i.cur_Quantidade",
    "precoUnitario": "i.cur_PrecoUnitario",
}

# Teto de linhas por página. As tabelas do Bionexo somam dezenas de milhões de
# linhas; sem teto, `perPage=100000` traria a base inteira para a memória do
# worker.
PER_PAGE_MAXIMO = 100

# Janela máxima do período, na tela E na exportação. Um filtro de data aberto
# varreria 8 GB. Vale mesmo para o CSV: a exportação é em streaming e não
# guarda tudo na memória, mas a CONSULTA no SQL Server continua custando, e um
# período de anos seguraria um worker por muito tempo.
JANELA_MAXIMA_DIAS = 90


class CotacaoItemSchema(ContratoBase):
    """Uma linha da listagem: um item de uma cotação, para um CNPJ nosso.

    A mesma cotação aparece uma vez para CADA empresa da distribuidora — é
    assim que o Bionexo entrega, e a tela mostra tudo, com a coluna empresa
    distinguindo. Filtrar por empresa é escolha de quem consulta.
    """

    cotacao: int
    titulo_cotacao: str | None = None
    data_vencimento: datetime | None = None
    hospital: str
    cnpj_hospital: str | None = None
    cidade: str
    estado: str | None = None
    empresa_id: int | None = None
    empresa: str | None = None
    codigo_produto_hospital: str | None = None
    produto_hospital: str | None = None
    quantidade_solicitada: Decimal | None = None
    quantidade_respondida: Decimal | None = None
    quantidade_faturada: Decimal | None = None
    unidade: str | None = None
    preco_unitario: Decimal | None = None


class CotacaoFiltrosSchema(ContratoBase):
    """Os filtros da tela, já validados. Todos são resolvidos NA CONSULTA, no
    SQL Server — nunca sobre a página carregada. Filtrar depois de paginar
    responderia "não achei" para um item que existe na página 7."""

    # Opcionais só porque `cotacao` os dispensa (ver o validador abaixo).
    data_inicio: date | None = None
    data_fim: date | None = None
    # O número da cotação no Bionexo (int_IdPdc). Quando informado, o PERÍODO É
    # IGNORADO: quem procura uma cotação específica não sabe (nem deveria
    # precisar saber) em que data ela vence, e exigir o período faria a busca
    # responder "não achei" para uma cotação que existe.
    cotacao: int | None = None
    termo: str | None = None
    hospital: str | None = None
    cidade: str | None = None
    estado: str | None = None
    empresa_id: int | None = None
    situacao: SituacaoResposta = "todas"

    @model_validator(mode="after")
    def exigir_periodo_ou_cotacao(self) -> "CotacaoFiltrosSchema":
        if self.cotacao is None and (self.data_inicio is None or self.data_fim is None):
            raise ValueError("Informe o período de vencimento ou o número da cotação.")
        return self

    @property
    def por_cotacao(self) -> bool:
        """Busca por número de cotação — o período não se aplica."""
        return self.cotacao is not None


class CotacaoListaPaginadaSchema(ContratoBase):
    """Uma página da listagem, mais o total para a paginação da tela."""

    items: list[CotacaoItemSchema]
    total: int
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=PER_PAGE_MAXIMO)
    sort: str
    sort_type: str


class CotacaoEmpresaSchema(ContratoBase):
    id: int
    nome: str


class CotacaoFiltroOpcoesSchema(ContratoBase):
    """Opções para preencher os selects da tela (estados e empresas).

    Vêm de consulta própria, não da página carregada: os estados que aparecem
    na página 1 não são os estados que existem na base.
    """

    estados: list[str]
    empresas: list[CotacaoEmpresaSchema]
