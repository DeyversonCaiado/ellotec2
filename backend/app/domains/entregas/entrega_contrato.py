from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.shared.contrato_base import ContratoBase

# Os 7 status da entrega, agora como SLUG e não como a frase exibida. O sistema
# antigo guardava o texto ("Em trânsito", "Devolucao parcial") na coluna, com e
# sem acento conforme quem digitou — o que fazia o filtro por status perder
# linhas em silêncio. O rótulo bonito é responsabilidade do front.
StatusEntrega = Literal[
    "aguardando_embarque",
    "com_ocorrencia",
    "em_transito",
    "entrega_realizada",
    "recusada_no_ato",
    "retida_fiscalizacao",
    "devolucao_parcial",
]

# O status com que a nota NASCE, antes de qualquer interação. A coluna é
# NOT NULL e o ERP não tem status de acompanhamento — ele começa a existir aqui,
# na primeira interação lançada.
STATUS_NASCIMENTO = "aguardando_embarque"

# Os status que uma PESSOA pode escolher ao lançar ou corrigir uma interação.
#
# É o `StatusEntrega` menos o de nascimento, e a diferença entre os dois é o
# ponto: o conjunto que a coluna pode GUARDAR é maior que o que o usuário pode
# ESCOLHER. Lançar um evento dizendo "aguardando embarque" seria registrar como
# fato o estado de quem ainda não registrou nada — a tela mostra "Sem
# interação" nesse caso, e não um status que alguém teria afirmado.
#
# Vale como barreira de verdade porque está no servidor: o front esconder a
# opção é só UX, e a API é chamável direto.
StatusInteracao = Literal[
    "com_ocorrencia",
    "em_transito",
    "entrega_realizada",
    "recusada_no_ato",
    "retida_fiscalizacao",
    "devolucao_parcial",
]

# A classificação que o SQL do sistema antigo montava a partir do CFOP e do
# status da nota. Chega pronta pela API — quem sabe classificar é o ERP.
TipoNota = Literal["venda", "bonificacao", "devolucao_cliente", "complementar", "perda", "outros"]

# Calculado, nunca gravado — depende de que dia é hoje (ver entrega_prazo.py).
StatusPrazo = Literal["entregue", "em_atraso", "no_prazo", "sem_mapa", "prazo_nao_definido"]

# O status que encerra a entrega. Fica aqui, e não solto no service, porque a
# regra "entrega realizada carimba a data de entrega" depende dele.
STATUS_ENCERRA_ENTREGA = "entrega_realizada"


# ---------------------------------------------------------------------------
# Entrada — o que a integração manda (o ERP faz POST; nada é lido do Oracle)
# ---------------------------------------------------------------------------


class EntregaCriarSchema(ContratoBase):
    """O mapa de carga."""

    empresa_id: str | None = None
    # Se informado, a empresa é resolvida por esse campo em vez de empresa_id —
    # mesmo padrão de pedidos. O ERP conhece a empresa pelo CNPJ/código dele,
    # não pelo nosso UUID.
    empresa_sistema_origem_id: str | None = None
    numero_mapa: str = Field(max_length=30)
    data_mapa: datetime | None = None
    transportadora_nome: str | None = Field(default=None, max_length=200)
    transportadora_cnpj: str | None = Field(default=None, max_length=18)
    motorista: str | None = Field(default=None, max_length=150)
    placa_veiculo: str | None = Field(default=None, max_length=10)
    sistema_origem_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validar_referencia_de_empresa(self) -> "EntregaCriarSchema":
        if not self.empresa_id and not self.empresa_sistema_origem_id:
            raise ValueError("Informe empresaId ou empresaSistemaOrigemId.")
        return self


class ItemEntregaNotaEntradaSchema(ContratoBase):
    numero_item: int = Field(gt=0)
    produto_codigo: str = Field(default="", max_length=40)
    produto_descricao: str = Field(default="", max_length=255)
    marca_nome: str | None = Field(default=None, max_length=100)
    quantidade: Decimal = Field(default=Decimal(0), ge=0)
    preco_unitario: Decimal = Field(default=Decimal(0), ge=0)
    valor_total: Decimal = Field(default=Decimal(0), ge=0)
    lote: str | None = Field(default=None, max_length=60)
    validade: date | None = None
    quantidade_devolvida: Decimal = Field(default=Decimal(0), ge=0)
    observacao: str | None = Field(default=None, max_length=255)


class EntregaNotaCriarSchema(ContratoBase):
    """A nota e seus itens, num payload só.

    Tudo aqui é SNAPSHOT: o backend não consulta `notas_fiscais` nem o cadastro
    de produtos para completar nada. O que o ERP mandou é o que fica gravado.
    """

    empresa_id: str | None = None
    empresa_sistema_origem_id: str | None = None

    numero_nota: str = Field(max_length=20)
    serie: str = Field(default="", max_length=5)
    pedido: str = Field(default="", max_length=50)
    tipo_nota: TipoNota = "outros"
    data_nota: datetime | None = None
    situacao: str | None = Field(default=None, max_length=30)
    valor_total: Decimal = Field(default=Decimal(0), ge=0)

    # 44 posições exatas quando vier — é o tamanho fixo do layout da NF-e, e o
    # mesmo `min_length=44` que `notas_fiscais` exige. Recusar uma chave de 43
    # na entrada é melhor que gravar lixo que só vai aparecer no dia em que
    # alguém tentar cruzar esta linha com a nota fiscal.
    chave_acesso_nota: str | None = Field(default=None, min_length=44, max_length=44)
    chave_acesso_referenciada: str | None = Field(default=None, min_length=44, max_length=44)

    cliente_codigo: str | None = Field(default=None, max_length=20)
    cliente_nome: str = Field(default="", max_length=200)
    cliente_cidade: str | None = Field(default=None, max_length=100)
    cliente_uf: str | None = Field(default=None, max_length=2)

    # O código do vendedor no ERP (`fat_funcionarios.funcionario`), resolvido
    # para usuario_id via usuario_publico. Não recusa a nota se não resolver:
    # nota sem vendedor identificado é melhor que nota não gravada.
    vendedor_sistema_origem_id: str | None = Field(default=None, max_length=100)
    transportadora_nome: str | None = Field(default=None, max_length=200)
    termolabil: bool = False

    # Vínculo com o mapa de carga. O ERP manda o número do mapa; se ele ainda
    # não existir aqui, a nota é gravada sem mapa (status_prazo "sem_mapa") e o
    # vínculo se resolve quando o mapa chegar.
    entrega_numero_mapa: str | None = Field(default=None, max_length=30)
    sistema_origem_id: str | None = Field(default=None, max_length=100)

    itens: list[ItemEntregaNotaEntradaSchema] = Field(default_factory=list)

    @field_validator("itens")
    @classmethod
    def itens_sem_numero_repetido(
        cls, itens: list[ItemEntregaNotaEntradaSchema]
    ) -> list[ItemEntregaNotaEntradaSchema]:
        numeros = {item.numero_item for item in itens}
        if len(numeros) != len(itens):
            raise ValueError("Existem dois itens com o mesmo numeroItem na nota.")
        return itens

    @model_validator(mode="after")
    def validar_referencia_de_empresa(self) -> "EntregaNotaCriarSchema":
        if not self.empresa_id and not self.empresa_sistema_origem_id:
            raise ValueError("Informe empresaId ou empresaSistemaOrigemId.")
        return self


class InteracaoCriarSchema(ContratoBase):
    """O usuário NÃO vem no payload: é o do token. Deixar quem registra ser
    escolhido por quem chama permitiria lançar interação no nome de outro.

    `StatusInteracao` e não `StatusEntrega`: o status de nascimento não é uma
    escolha — ver o comentário dele lá em cima."""

    status: StatusInteracao
    observacao: str = Field(default="", max_length=1000)


class InteracaoAtualizarSchema(ContratoBase):
    """Interação é editável — quem lança digita errado, e obrigar um segundo
    evento só para corrigir uma palavra sujaria a timeline. A edição fica
    registrada (editadoPor/editadoEm) e NÃO reordena a linha do tempo.

    Corrigir uma interação antiga para o status de nascimento também não é
    permitido: as interações legadas que ainda têm esse status são história e
    continuam sendo exibidas, mas nenhuma nova pode ser gravada assim."""

    status: StatusInteracao
    observacao: str = Field(default="", max_length=1000)


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------


class ItemEntregaNotaRespostaSchema(ContratoBase):
    id: str
    numero_item: int
    produto_codigo: str
    produto_descricao: str
    marca_nome: str | None
    # Serializados como number, igual aos outros domínios: o Pydantic v2
    # devolveria Decimal como string em modo JSON, e o front faz conta.
    quantidade: float
    preco_unitario: float
    valor_total: float
    lote: str | None
    validade: date | None
    quantidade_devolvida: float
    observacao: str | None


class InteracaoRespostaSchema(ContratoBase):
    id: str
    status: StatusEntrega
    observacao: str
    usuario_id: str
    usuario_nome: str
    # O instante do EVENTO, campo de negócio com coluna própria. É por ele que
    # a timeline ordena e exibe "há quanto tempo" — nunca pelos campos sync_*,
    # que são auditoria da linha (ver ARCHITECTURE.md).
    data_interacao: datetime
    editado_em: datetime | None
    editado_por_nome: str | None


class EntregaNotaResumoSchema(ContratoBase):
    """O que a LISTAGEM devolve — sem itens e sem interações.

    Uma nota tem dezenas de itens e um punhado de eventos; carregar os dois numa
    página de 20 notas seriam centenas de linhas que a lista não mostra.
    """

    id: str
    empresa_id: str
    # Apelido da empresa emissora ("Matriz", "BSB") — cai no nome fantasia
    # quando não há apelido cadastrado. É o que a coluna "Empresa" mostra: num
    # galpão que atende várias filiais, saber de qual é a entrega é a primeira
    # pergunta, e o nome fantasia inteiro não cabe numa coluna.
    empresa_apelido: str | None = None
    numero_nota: str
    serie: str
    pedido: str
    tipo_nota: str
    data_nota: datetime | None
    situacao: str | None
    valor_total: float
    cliente_nome: str
    cliente_cidade: str | None
    cliente_uf: str | None
    vendedor_id: str | None
    vendedor_nome: str | None
    transportadora_nome: str | None
    termolabil: bool
    numero_mapa: str | None
    data_mapa: datetime | None
    prazo_dias: int | None
    data_prevista_entrega: date | None
    status_atual: str
    # Calculado no service a cada leitura — depende de hoje.
    status_prazo: StatusPrazo
    data_entrega_realizada: datetime | None
    qtd_interacoes: int


class NotaDevolucaoSchema(ContratoBase):
    """Uma nota que devolve a nota aberta na tela.

    Resumo curto de propósito: a seção responde "o que voltou desta entrega?",
    e quem quiser o resto clica e abre a nota de devolução, que é uma nota
    como qualquer outra nesta mesma tela.
    """

    id: str
    numero_nota: str
    serie: str
    data_nota: datetime | None
    tipo_nota: str
    situacao: str | None
    valor_total: float
    chave_acesso_nota: str | None
    status_atual: str
    # Vai junto com o status porque a tela não rotula um pelo outro: sem
    # interação nenhuma, o que se mostra é "Sem interação", não o status de
    # nascimento. Sem este campo aqui, o card da devolução seria o único lugar
    # da tela a exibir "Aguardando embarque" para uma nota que ninguém tocou.
    qtd_interacoes: int = 0


class EntregaNotaRespostaSchema(EntregaNotaResumoSchema):
    """O detalhe: o resumo + itens + a timeline inteira."""

    cliente_codigo: str | None
    # No DETALHE e não no resumo: a chave tem 44 dígitos, não cabe numa coluna
    # da listagem e ninguém a lê de relance. Quem precisa dela está olhando uma
    # nota específica, para cruzar com o fiscal ou achar a nota de origem.
    chave_acesso_nota: str | None = None
    chave_acesso_referenciada: str | None = None
    entrega_id: str | None
    motorista: str | None
    placa_veiculo: str | None
    sistema_origem_id: str | None
    itens: list[ItemEntregaNotaRespostaSchema]
    interacoes: list[InteracaoRespostaSchema]
    # As notas que DEVOLVEM esta. Achadas pela chave: são as notas cuja
    # `chave_acesso_referenciada` é igual à `chave_acesso_nota` desta. Vazio
    # quando não houve devolução — e também quando esta nota ainda não tem
    # chave, porque aí não há por onde ninguém apontar para ela.
    notas_devolucao: list[NotaDevolucaoSchema] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Filtros da listagem
#
# Todo filtro é uma LISTA de valores escolhidos, e não um valor só. O desenho
# vem da tela: cada campo é um autocomplete múltiplo, alimentado pelos valores
# que EXISTEM no período (`GET /entregas/opcoes-filtros`) — a pessoa escolhe
# entre o que há, em vez de digitar no escuro e receber lista vazia.
#
# Lista vazia significa "não filtrar por este campo". Vários valores no mesmo
# campo é OU (transportadora A ou B); campos diferentes é E (transportadora A
# E cidade Goiânia) — que é como se lê um painel de filtros.
#
# `status_prazo` NÃO está aqui: ele é as abas da tela (Em atraso, No prazo,
# Sem mapa...), é um valor só e continua parâmetro próprio.
# ---------------------------------------------------------------------------


class FiltrosListagemSchema(ContratoBase):
    """Os valores escolhidos em cada campo do painel de filtros.

    Chega como query string repetida (`?uf=GO&uf=DF`), que é a forma padrão de
    lista em URL e o que o `HttpParams` do Angular gera.
    """

    # Apelido da empresa (ou o nome fantasia, quando não há apelido) — nunca o
    # UUID: quem escolhe é uma pessoa, e a lista de opções mostra o apelido.
    empresa: list[str] = Field(default_factory=list)
    tipo_nota: list[str] = Field(default_factory=list)
    pedido: list[str] = Field(default_factory=list)
    numero_nota: list[str] = Field(default_factory=list)
    data_nota: list[date] = Field(default_factory=list)
    cliente: list[str] = Field(default_factory=list)
    uf: list[str] = Field(default_factory=list)
    cidade: list[str] = Field(default_factory=list)
    # Situação da nota no ERP (N1, NF, CP...), texto livre vindo da integração.
    situacao: list[str] = Field(default_factory=list)
    # Nome do vendedor, pelo mesmo motivo da empresa: a tela lista gente, não id.
    vendedor: list[str] = Field(default_factory=list)
    transportadora: list[str] = Field(default_factory=list)
    # Status da ENTREGA (aguardando_embarque, em_transito...) — slug, não frase.
    status: list[str] = Field(default_factory=list)
    numero_mapa: list[str] = Field(default_factory=list)
    data_mapa: list[date] = Field(default_factory=list)
    # O NÚMERO da nota que esta devolve, extraído da chave referenciada.
    #
    # Não é uma coluna: são as 9 posições a partir da 26ª de
    # `chave_acesso_referenciada`, que é onde o layout da NF-e guarda o número
    # do documento (cUF 2, AAMM 4, CNPJ 14, modelo 2, série 3, **nNF 9**...).
    # A chave inteira tem 44 dígitos e ninguém procura por ela; quem pergunta
    # "quais notas devolveram a 0116606?" digita o número.
    nota_devolvida: list[str] = Field(default_factory=list)
    # Os quatro abaixo moram no ITEM, não na nota. Filtrar por eles significa
    # "notas que CONTÊM este produto/marca/lote/quantidade" — a nota inteira
    # entra no resultado, com todos os seus itens. É o que a tela pergunta
    # ("quais entregas levam o produto X"), e é por isso que a consulta usa
    # EXISTS e não JOIN: o join multiplicaria a nota por item e quebraria a
    # contagem do rodapé e a paginação.
    produto: list[str] = Field(default_factory=list)
    marca: list[str] = Field(default_factory=list)
    lote: list[str] = Field(default_factory=list)
    quantidade: list[Decimal] = Field(default_factory=list)

    def algum_preenchido(self) -> bool:
        return any(getattr(self, campo) for campo in type(self).model_fields)


class SugestoesFiltroSchema(ContratoBase):
    """As sugestões de UM campo do painel, para o autocomplete da tela.

    Um endpoint só serve todos os campos — `campo` diz qual. A alternativa era
    devolver todos os valores de todos os campos numa resposta só, e foi o que
    existiu primeiro: num mês real deu ~600 pedidos e centenas de números de
    nota, e crescia com o período escolhido.

    As sugestões saem do PERÍODO, e não dos outros filtros já escolhidos. Se
    saíssem, escolher uma transportadora encolheria a lista de cidades e trocar
    de ideia exigiria limpar tudo antes.
    """

    campo: str
    # Sempre string: o autocomplete é campo de texto e o query param é texto.
    # Quem converte de volta para data/decimal é o contrato de entrada.
    valores: list[str]
    # True quando havia mais valores do que o teto. A tela usa para dizer
    # "refine a busca" em vez de deixar a pessoa achar que aquilo é tudo.
    truncado: bool


class EntregaNotaListaPaginadaSchema(ContratoBase):
    """Mesmo formato de página dos outros domínios."""

    items: list[EntregaNotaResumoSchema]
    total: int
    page: int
    per_page: int
    sort: str
    sort_type: str


class EntregaRespostaSchema(ContratoBase):
    id: str
    empresa_id: str
    numero_mapa: str
    data_mapa: datetime | None
    transportadora_nome: str | None
    transportadora_cnpj: str | None
    motorista: str | None
    placa_veiculo: str | None
    sistema_origem_id: str | None
