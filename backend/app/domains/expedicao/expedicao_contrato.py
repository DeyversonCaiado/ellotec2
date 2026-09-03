from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.shared.contrato_base import ContratoBase, DataHoraUtc

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


class FinalizarNoSistemaOrigemSchema(ContratoBase):
    """Os dados de embarque que o ERP pede para fechar o pedido.

    São quatro números que o galpão só conhece DEPOIS de conferir e embalar —
    por isso não saem de lugar nenhum do sistema, e o operador digita.

    `volume` é `Decimal` e não `int` só porque é assim que quantidade entra em
    contrato neste projeto; ele é sempre inteiro (contagem de volumes), e é isso
    que o `ge=1` e `decimal_places=0` garantem. No ERP a coluna
    `VOLUME_PEDIDO` é `VARCHAR2(10)` — a conversão para texto acontece em
    `sistema_origem_service._volume_para_o_erp`, e o `le` acima é o que impede
    um número que não caberia lá.
    """

    volume: Decimal = Field(ge=1, le=9_999_999_999, decimal_places=0)
    # 10 caracteres é o tamanho da coluna ESPECIE_PEDIDO no ERP — VARCHAR2(10),
    # conferido em `all_tab_columns`, não estimado (ex: CX, FD, SC, CAIXA).
    # Digitado livre, e a maiúscula é garantida no service — o front também
    # força, mas ele é conveniência, não barreira.
    especie: str = Field(min_length=1, max_length=10)
    # Peso em quilos. `gt=0` porque pedido embarcado sem peso não existe, e o
    # zero passaria batido até a nota sair errada.
    peso_liquido: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    peso_bruto: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


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
    data_atribuicao: DataHoraUtc


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


class EnderecoItemSchema(ContratoBase):
    """Um endereço em que o lote do item está, e quanto tem nele.

    A quantidade é o ponto: antes a expedição mostrava só o total do item
    somado, o que não dizia ao operador quanto pegar em cada prateleira. Agora
    ele lê "07-14-08-03-01: 24" e sabe exatamente o que tirar de lá.
    """

    endereco_id: str
    descricao: str
    quantidade: float


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
    # Onde a mercadoria está guardada, COM a quantidade de cada endereço —
    # lista, porque um lote se espalha por vários endereços do galpão de
    # verdade. Vem de `estoque_endereco_lote` (domínio `enderecamento`)
    # partindo do par (produto, lote).
    enderecos: list[EnderecoItemSchema]
    # A soma dos endereços acima. Vem pronta para a tela não ter que somar
    # float no navegador e chegar num total diferente do que o backend usou
    # para decidir o bloqueio.
    quantidade_enderecada: float
    # Nulo = item consistente. Preenchido = a frase que a tela mostra no quadro
    # vermelho (endereçamento insuficiente ou saldo que não fecha caixa).
    bloqueio: str | None
    lote: str | None
    quantidade_pedida: int
    quantidade_processada: int
    # Unidades por embalagem de venda do produto (1 = vendido na unidade).
    # Vem do cadastro vivo, não do snapshot do pedido: é o que vale na hora
    # de bipar, e é por ele que cada leitura é multiplicada.
    quantidade_multipla_venda: int
    data_inicio: DataHoraUtc | None
    data_fim: DataHoraUtc | None
    divergente: bool
    # Derivado das datas, não é coluna: pendente | em_andamento | finalizado.
    situacao: str


class ProcessoRespostaSchema(ContratoBase):
    id: str
    tipo: TipoProcesso
    pedido_id: str
    pedido_numero: str | None
    status: str
    # De quem é o TRABALHO — o operador. Não muda quando o gerente executa em
    # nome dele; quem clicou vai nos campos `gestor` abaixo.
    usuario_inicio_id: str
    usuario_inicio_nome: str | None
    usuario_fim_id: str | None
    # Quem CLICOU, quando não foi o próprio operador. Nulos no caso normal.
    usuario_gestor_inicio_nome: str | None = None
    usuario_gestor_fim_nome: str | None = None
    data_inicio: DataHoraUtc | None
    data_fim: DataHoraUtc | None
    # Desfecho da baixa no ERP. Só a conferência tem — na separação vem sempre
    # nulo, porque não existe nada para fechar no sistema de origem ali.
    finalizado_origem_em: DataHoraUtc | None = None
    motivo_falha_origem: str | None = None
    # Quem tentou e quando, na última tentativa — deu certo ou não. É o que
    # responde "quem tentou fechar este pedido, e a que horas?" sem depender de
    # ninguém lembrar. O nome, e não o id: quem lê é gente.
    tentativa_origem_em: DataHoraUtc | None = None
    tentativa_origem_usuario_nome: str | None = None
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
    data_primeiro_bipe: DataHoraUtc | None = None
    data_fim: DataHoraUtc | None = None
    # Quando a etapa foi ABERTA. Existe por causa da execução delegada: ali
    # ninguém bipa, então `data_primeiro_bipe` é nulo para sempre e a tela não
    # tinha de onde tirar hora de início nem duração — mostrava um traço numa
    # etapa que começou e terminou. Quando o gerente registra o início, é este
    # o instante em que o trabalho começou, e é dele que o tempo conta.
    data_inicio: DataHoraUtc | None = None
    # Execução delegada: o gerente iniciou e/ou finalizou a etapa no nome do
    # operador atribuído (ver "Execução delegada" no README do domínio). Nulos
    # no caso normal, em que o operador abre e fecha sozinho.
    usuario_gestor_inicio_nome: str | None = None
    usuario_gestor_fim_nome: str | None = None
    # Derivado dos dois acima. Existe para a tela não repetir a mesma condição
    # em três lugares só para decidir se desenha o selo.
    delegado: bool = False
    # Mesmo par de ProcessoRespostaSchema — a tela do pedido precisa saber se
    # a conferência já foi baixada no ERP para decidir entre oferecer o botão
    # de finalizar e mostrar o selo de finalizado.
    finalizado_origem_em: DataHoraUtc | None = None
    motivo_falha_origem: str | None = None
    # Mesmo par de ProcessoRespostaSchema — ver lá.
    tentativa_origem_em: DataHoraUtc | None = None
    tentativa_origem_usuario_nome: str | None = None


class PedidoExpedicaoListaSchema(ContratoBase):
    pedido_id: str
    # Nulo quando a origem externa ainda não deu número ao pedido — a tela
    # mostra o traço, e o pedido continua trabalhável no galpão.
    numero: str | None
    sistema_origem_id: str | None
    data_pedido: date
    # Chave do status vindo do ERP (PED, OK, CAN…). Só 'PED' autoriza abrir
    # separação ou conferência — os demais aparecem para consulta.
    status_pedido: str
    # Já considera as DUAS barreiras: o status do ERP e a consistência do
    # endereçamento. A tela não precisa combinar nada — se veio False, o botão
    # não aparece, e `bloqueioEnderecamento` diz o porquê quando a causa foi o
    # galpão.
    pode_iniciar: bool
    # Nulo = endereçamento em ordem. Preenchido = a primeira pendência do
    # pedido, já com o código do produto na frente, para a listagem conseguir
    # explicar o bloqueio sem abrir o detalhe.
    bloqueio_enderecamento: str | None
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
    # Quantos pedidos há em CADA situação NO PERÍODO — uma chave por valor de
    # SITUACOES_VALIDAS, inclusive 'todos'.
    #
    # Contam só o período: ignoram termo, status do ERP, empresa, operador e a
    # própria situação escolhida. São um painel fixo do galpão naquele intervalo,
    # e por isso não mudam enquanto a pessoa mexe nos filtros da lista.
    #
    # A exceção é a visibilidade por atribuição, que entra porque não é filtro e
    # sim regra de acesso — contar o que a lista esconde vazaria pelo número.
    contagens_por_situacao: dict[str, int]


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
    # Ver ItemProcessoRespostaSchema acima — mesmos três campos, mesma origem.
    enderecos: list[EnderecoItemSchema]
    quantidade_enderecada: float
    bloqueio: str | None
    lote: str | None
    quantidade: int
    quantidade_multipla_venda: int
    separacao_situacao: str
    separacao_quantidade: int
    conferencia_situacao: str
    conferencia_quantidade: int


class PedidoExpedicaoDetalheSchema(ContratoBase):
    pedido_id: str
    numero: str | None
    sistema_origem_id: str | None
    data_pedido: date
    # Mesmo par da listagem: o status do ERP e se ele autoriza abrir processo —
    # aqui `pode_iniciar` também já embute a consistência do endereçamento.
    status_pedido: str
    pode_iniciar: bool
    bloqueio_enderecamento: str | None
    # Só a barreira do ERP, sem o endereçamento. Existe por causa da liberação
    # de emergência: quem tem `expedicao.enderecamento.liberar` pode iniciar com
    # o galpão inconsistente, mas nunca com o status errado — e, com um booleano
    # só, a tela não teria como distinguir as duas causas de `pode_iniciar`
    # False. A alternativa seria o front comparar `status_pedido` com 'PED' por
    # conta própria, reimplementando a regra do domínio `pedidos`.
    status_permite_iniciar: bool
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
