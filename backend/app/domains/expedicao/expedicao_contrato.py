from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.shared.contrato_base import ContratoBase

# Os dois processos da expedição têm exatamente o mesmo ciclo de vida — o
# tipo entra como parte da URL e é validado aqui, num lugar só.
TipoProcesso = Literal["separacao", "conferencia"]


class CredencialGerenteSchema(ContratoBase):
    """Override de gerente. Não é login: nenhuma sessão é criada, nenhum
    token é emitido, quem está logado continua sendo quem estava."""

    usuario_gerente: str = Field(min_length=1, max_length=50)
    senha: str = Field(min_length=1)


class BiparSchema(ContratoBase):
    # Cabe tanto o código linear quanto o conteúdo inteiro de um QR Code GS1 —
    # quem separa os dois é `shared/gs1.py`, do lado de lá. 300 e não 60 porque
    # o QR carrega lote, validade e série junto com o código do produto.
    codigo_barras: str = Field(min_length=1, max_length=300)
    # O coletor permite digitar um multiplicador antes de bipar, pra não
    # obrigar o operador a passar o leitor 32 vezes numa caixa fechada.
    multiplicador: int = Field(default=1, ge=1)


class FinalizarItemSchema(ContratoBase):
    """Credencial só é exigida quando a quantidade processada está abaixo da
    pedida (ver `finalizar_item` em expedicao_service.py). Item completo
    fecha sem pedir nada."""

    usuario_gerente: str | None = None
    senha: str | None = None


class AtribuirSchema(ContratoBase):
    """Atribui (ou desatribui) uma etapa de vários pedidos de uma vez.

    `usuario_id` nulo significa "sem responsável" — desatribuir é um VALOR
    deste campo, não uma operação separada, do mesmo jeito que 'Unassigned' é
    um valor de responsável nas ferramentas de tarefa. Um endpoint, um
    service, uma permissão.
    """

    pedido_ids: list[str] = Field(min_length=1)
    tipo: TipoProcesso
    usuario_id: str | None = None


class AtribuicaoSchema(ContratoBase):
    """Quem responde por uma etapa do pedido. Nulo na listagem = sem dono."""

    usuario_id: str
    usuario_nome: str
    atribuido_por_nome: str | None
    data_atribuicao: datetime


class OperadorSchema(ContratoBase):
    """Opção do seletor de responsável — só quem pode executar a etapa.

    O mesmo formato serve o filtro por operador da listagem, com uma diferença
    de conteúdo: o seletor pede uma etapa e recebe quem executa AQUELA etapa; o
    filtro não pede etapa e recebe quem executa qualquer uma.
    """

    id: str
    nome: str


class EmpresaFiltroSchema(ContratoBase):
    """Opção do filtro por empresa da listagem — matriz e filiais.

    Contrato próprio, e não o schema do domínio de empresas: amarrar o formato
    desta resposta ao de lá faria mudar a API de empresas quebrar a expedição
    (ver ARCHITECTURE.md → "Regras de import entre domínios").
    """

    id: str
    nome: str


class ItemProcessoRespostaSchema(ContratoBase):
    pedido_item_id: str
    produto_id: str
    produto_codigo: str
    produto_descricao: str
    # Unidade do cadastro do produto (UN, CX…), não do snapshot do pedido.
    produto_unidade: str
    # Marca e códigos de barras também vêm do cadastro vivo, pelo mesmo motivo
    # do múltiplo de venda: é o que está impresso na caixa que o operador tem na
    # mão agora, e é contra o cadastro de hoje que a bipagem valida.
    produto_marca_nome: str
    # O da nota (vindo do ERP) e os de logística (cadastrados aqui) vão
    # separados porque a tela os rotula diferente — o operador precisa saber
    # qual deles ele está olhando.
    produto_codigo_barra_notas: str | None
    produto_codigos_barras_logistica: list[str]
    produto_dun_14: str | None
    endereco_produto: str | None
    lote: str | None
    quantidade_pedida: int
    quantidade_processada: int
    # Unidades por embalagem de venda do produto (1 = vendido na unidade).
    # Vem do cadastro vivo, não do snapshot do pedido: é o que vale na hora
    # de bipar, e é por ele que cada leitura é multiplicada.
    quantidade_multipla_venda: int
    data_inicio: datetime | None
    data_fim: datetime | None
    divergente: bool
    # Derivado das datas, não é coluna: pendente | em_andamento | finalizado.
    situacao: str


class ProcessoRespostaSchema(ContratoBase):
    id: str
    tipo: TipoProcesso
    pedido_id: str
    pedido_numero: str
    status: str
    usuario_inicio_id: str
    usuario_inicio_nome: str | None
    usuario_fim_id: str | None
    data_inicio: datetime | None
    data_fim: datetime | None
    itens: list[ItemProcessoRespostaSchema]


class SituacaoProcessoSchema(ContratoBase):
    """Estado resumido de um processo, do ponto de vista de quem só quer
    saber "já separou? já conferiu?" — usado na listagem e no cabeçalho."""

    # nulos quando o processo ainda não foi aberto
    id: str | None
    status: str  # nao_iniciada | em_andamento | finalizada
    usuario_id: str | None
    usuario_nome: str | None
    itens_finalizados: int
    itens_total: int
    tem_divergencia: bool
    # Quando o trabalho de fato começou (primeira leitura) e quando fechou. O
    # início é o primeiro bipe, não a abertura do processo — abrir a lista e ir
    # até o endereço não é tempo de separação. Nulos enquanto não aconteceram.
    data_primeiro_bipe: datetime | None = None
    data_fim: datetime | None = None


class PedidoExpedicaoListaSchema(ContratoBase):
    pedido_id: str
    numero: str
    sistema_origem_id: str | None
    data_pedido: date
    # Chave do status vindo do ERP (PED, OK, CAN…). Só 'PED' autoriza abrir
    # separação ou conferência — os demais aparecem para consulta.
    status_pedido: str
    pode_iniciar: bool
    cliente_nome_fantasia: str
    cliente_cnpj: str
    # Cidade de entrega vem do cadastro vivo do cliente, não do snapshot do
    # pedido — mesma regra do endereço no detalhe (ver obter_pedido).
    cliente_cidade_nome: str
    cliente_cidade_uf: str
    # Empresa emissora do pedido — matriz ou filial. A expedição filtra por
    # ela quando o galpão atende mais de uma.
    empresa_id: str
    empresa_nome: str
    # Nome curto do dia a dia ("Matriz", "BSB"). É ele que a coluna "Emp" da
    # listagem mostra: nome fantasia inteiro não cabe numa coluna estreita, e
    # numa fila de pedidos de várias empresas o que se precisa é distinguir, não
    # ler o nome completo. Nulo enquanto ninguém cadastrar o apelido.
    empresa_apelido: str | None
    quantidade_itens: int
    quantidade_total: int
    # Quando o pedido mudou pela última vez — é por este campo que a listagem
    # ordena e filtra o período.
    alterado_em: datetime
    # Milestone da liberação (ex: aprovação de crédito no ERP). É daqui que o
    # ciclo do pedido é contado — não da data do pedido.
    liberado_em: datetime | None
    # Chave do catálogo pedido_status gravada pela expedição em
    # expedicao_pedido_status. Nula = pedido que ainda não entrou no galpão.
    expedicao_status: str | None
    separacao: SituacaoProcessoSchema
    conferencia: SituacaoProcessoSchema
    # Responsável designado por etapa. Nulo = ninguém designado ainda. É por
    # estes campos que o operador comum enxerga (ou não) a linha — ver
    # `listar_pedidos` em expedicao_service.py.
    atribuicao_separacao: AtribuicaoSchema | None
    atribuicao_conferencia: AtribuicaoSchema | None


class PedidoExpedicaoListaPaginadaSchema(ContratoBase):
    """Mesmo formato de página usado nos outros domínios (ver
    ProdutoListaPaginadaSchema) — a tela não inventa um contrato próprio."""

    items: list[PedidoExpedicaoListaSchema]
    total: int
    page: int
    per_page: int
    # Devolvidos para a tela saber qual cabeçalho desenhar com a seta — sem
    # isso ela teria que assumir que o servidor obedeceu.
    sort: str
    sort_type: str


class ItemPedidoExpedicaoSchema(ContratoBase):
    """Item na tela de detalhe do pedido — mostra o estado nas DUAS etapas
    lado a lado, que é o que o conferente precisa ver antes de escolher o
    que abrir."""

    pedido_item_id: str
    produto_id: str
    produto_codigo: str
    produto_descricao: str
    # Do cadastro vivo do produto, não do snapshot do pedido — ver
    # ItemProcessoRespostaSchema acima.
    produto_marca_nome: str
    produto_codigo_barra_notas: str | None
    produto_codigos_barras_logistica: list[str]
    produto_dun_14: str | None
    endereco_produto: str | None
    lote: str | None
    quantidade: int
    quantidade_multipla_venda: int
    separacao_situacao: str
    separacao_quantidade: int
    conferencia_situacao: str
    conferencia_quantidade: int


class PedidoExpedicaoDetalheSchema(ContratoBase):
    pedido_id: str
    numero: str
    sistema_origem_id: str | None
    data_pedido: date
    # Mesmo par da listagem: o status do ERP e se ele autoriza abrir processo.
    status_pedido: str
    pode_iniciar: bool
    observacoes: str
    vendedor_nome: str | None
    cliente_codigo: str | None
    cliente_razao_social: str
    cliente_nome_fantasia: str
    cliente_cnpj: str
    cliente_endereco: str
    cliente_bairro: str | None
    cliente_cep: str | None
    cliente_cidade_nome: str
    cliente_cidade_uf: str
    quantidade_itens: int
    quantidade_total: int
    # Chave do catálogo pedido_status gravada pela expedição em
    # expedicao_pedido_status. Nula = pedido que ainda não entrou no galpão.
    expedicao_status: str | None
    separacao: SituacaoProcessoSchema
    conferencia: SituacaoProcessoSchema
    # Qual botão o rodapé deve oferecer: 'separacao', 'conferencia' ou None
    # (nada a fazer — as duas etapas já fecharam).
    proxima_etapa: TipoProcesso | None
    atribuicao_separacao: AtribuicaoSchema | None
    atribuicao_conferencia: AtribuicaoSchema | None
    itens: list[ItemPedidoExpedicaoSchema]
