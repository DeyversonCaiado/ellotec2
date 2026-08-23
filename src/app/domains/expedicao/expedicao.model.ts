/** Separação e conferência têm o mesmo ciclo de vida — o tipo entra na URL. */
export type TipoProcesso = 'separacao' | 'conferencia';

/** Estado de um item dentro de um processo. Derivado das datas no backend,
 *  nunca calculado aqui (a regra é de lá, ver expedicao_service.py). */
export type SituacaoItem = 'pendente' | 'em_andamento' | 'finalizado';

export type StatusProcesso = 'nao_iniciada' | 'em_andamento' | 'finalizada';

export interface SituacaoProcesso {
  id: string | null;
  status: StatusProcesso;
  usuarioId: string | null;
  usuarioNome: string | null;
  itensFinalizados: number;
  itensTotal: number;
  temDivergencia: boolean;
  /** Quando a primeira leitura foi registrada — é daqui que o tempo de
   *  trabalho conta, não da abertura do processo. Nulo = ninguém bipou ainda. */
  dataPrimeiroBipe: string | null;
  /** Quando o processo fechou. Nulo = ainda em andamento. */
  dataFim: string | null;
}

/** Duração já quebrada em partes, pronta para o badge. */
export interface Duracao {
  texto: string;
  emAndamento: boolean;
}

/**
 * "1d 2h 30m" a partir de dois instantes. `fim` nulo mede até agora — é o que
 * faz o badge de um processo aberto mostrar quanto tempo ele já está correndo.
 *
 * Minutos são a menor unidade de propósito: segundos numa listagem só poluem,
 * e ninguém decide nada no galpão por causa de 40 segundos.
 */
export function duracaoEntre(inicio: string | null, fim: string | null): Duracao | null {
  if (!inicio) return null;
  const emAndamento = !fim;
  const ms = (fim ? new Date(fim).getTime() : Date.now()) - new Date(inicio).getTime();
  if (Number.isNaN(ms) || ms < 0) return null;

  const minutos = Math.floor(ms / 60000);
  const dias = Math.floor(minutos / 1440);
  const horas = Math.floor((minutos % 1440) / 60);
  const restoMinutos = minutos % 60;

  const partes: string[] = [];
  if (dias) partes.push(`${dias}d`);
  if (horas) partes.push(`${horas}h`);
  // Sempre mostra minutos quando não há dia nem hora, senão "menos de 1 min"
  // apareceria como texto vazio.
  if (restoMinutos || !partes.length) partes.push(`${restoMinutos}m`);

  return { texto: partes.join(' '), emAndamento };
}

/** Responsável designado por uma etapa. Null na listagem = ninguém designado.
 *  É por isto que o operador comum enxerga (ou não) a linha — o filtro é do
 *  backend, aqui é só exibição. */
export interface Atribuicao {
  usuarioId: string;
  usuarioNome: string;
  atribuidoPorNome: string | null;
  dataAtribuicao: string;
}

/** Opção do seletor de responsável — só quem pode executar aquela etapa. */
export interface Operador {
  id: string;
  nome: string;
}

export interface PedidoExpedicaoLista {
  pedidoId: string;
  numero: string;
  sistemaOrigemId: string | null;
  dataPedido: string;
  /** Status vindo do ERP (PED, OK, CAN…). */
  statusPedido: string;
  /** Só pedido em PED pode abrir separação ou conferência — quem decide é o
   *  backend, a tela só reflete. */
  podeIniciar: boolean;
  /** Data da última alteração: é por ela que a listagem ordena e filtra. */
  alteradoEm: string;
  clienteNomeFantasia: string;
  clienteCnpj: string;
  clienteCidadeNome: string;
  clienteCidadeUf: string;
  /** Quando o pedido foi liberado no ERP (ex: aprovação de crédito). É deste
   *  marco que o ciclo da expedição é contado — não da data do pedido. */
  liberadoEm: string | null;
  /** Empresa emissora — matriz ou filial. */
  empresaId: string;
  empresaNome: string;
  /** Nome curto do dia a dia ("Matriz", "BSB") — o que a coluna "Emp" mostra.
   *  Nome fantasia inteiro não cabe numa coluna estreita, e numa fila de várias
   *  empresas o que se precisa é distinguir, não ler o nome completo. Nulo
   *  enquanto ninguém cadastrar o apelido da empresa. */
  empresaApelido: string | null;
  quantidadeItens: number;
  quantidadeTotal: number;
  separacao: SituacaoProcesso;
  conferencia: SituacaoProcesso;
  atribuicaoSeparacao: Atribuicao | null;
  atribuicaoConferencia: Atribuicao | null;
}

/** Formato de resposta do GET /expedicao/pedidos, paginado no banco: são
 *  centenas de milhares de pedidos, e trazer tudo estoura o navegador. */
export interface PedidoExpedicaoListaPaginada {
  items: PedidoExpedicaoLista[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}

/** Colunas por onde o servidor sabe ordenar. Só existem as que saem da própria
 *  tabela `pedidos` — cidade, quantidade de itens e andamento das etapas vêm de
 *  outras tabelas e não entram na consulta paginada. */
export type ColunaOrdenavel =
  | 'numero'
  | 'data_pedido'
  | 'cliente_nome_fantasia'
  | 'quantidade_itens'
  | 'liberado_em'
  | 'sync_updated_at';

export interface ItemPedidoExpedicao {
  pedidoItemId: string;
  produtoId: string;
  produtoCodigo: string;
  produtoDescricao: string;
  /** Marca e códigos de barras vêm do cadastro vivo do produto (não do
   *  snapshot do pedido): é o que está impresso na caixa que o operador tem na
   *  mão. O da nota e os de logística vão separados porque a tela os rotula
   *  diferente. */
  produtoMarcaNome: string;
  produtoCodigoBarraNotas: string | null;
  produtoCodigosBarrasLogistica: string[];
  produtoDun14: string | null;
  enderecoProduto: string | null;
  lote: string | null;
  quantidade: number;
  /** Unidades por embalagem de venda do produto (1 = vendido na unidade).
   *  Cada leitura no coletor vale essa quantidade. */
  quantidadeMultiplaVenda: number;
  separacaoSituacao: SituacaoItem;
  separacaoQuantidade: number;
  conferenciaSituacao: SituacaoItem;
  conferenciaQuantidade: number;
}

export interface PedidoExpedicaoDetalhe {
  pedidoId: string;
  numero: string;
  sistemaOrigemId: string | null;
  dataPedido: string;
  /** Status vindo do ERP. */
  statusPedido: string;
  /** Só pedido em PED autoriza abrir separação ou conferência. */
  podeIniciar: boolean;
  observacoes: string;
  vendedorNome: string | null;
  clienteCodigo: string | null;
  clienteRazaoSocial: string;
  clienteNomeFantasia: string;
  clienteCnpj: string;
  clienteEndereco: string;
  clienteBairro: string | null;
  clienteCep: string | null;
  clienteCidadeNome: string;
  clienteCidadeUf: string;
  quantidadeItens: number;
  quantidadeTotal: number;
  separacao: SituacaoProcesso;
  conferencia: SituacaoProcesso;
  /** Qual botão o rodapé deve oferecer. null = as duas etapas já fecharam. */
  proximaEtapa: TipoProcesso | null;
  atribuicaoSeparacao: Atribuicao | null;
  atribuicaoConferencia: Atribuicao | null;
  itens: ItemPedidoExpedicao[];
}

export interface ItemProcesso {
  pedidoItemId: string;
  produtoId: string;
  produtoCodigo: string;
  produtoDescricao: string;
  /** Unidade do cadastro do produto (UN, CX…). */
  produtoUnidade: string;
  /** Do cadastro vivo do produto — ver ItemPedidoExpedicao. */
  produtoMarcaNome: string;
  produtoCodigoBarraNotas: string | null;
  produtoCodigosBarrasLogistica: string[];
  produtoDun14: string | null;
  enderecoProduto: string | null;
  lote: string | null;
  quantidadePedida: number;
  quantidadeProcessada: number;
  /** Unidades por embalagem de venda do produto (1 = vendido na unidade). */
  quantidadeMultiplaVenda: number;
  dataInicio: string | null;
  dataFim: string | null;
  divergente: boolean;
  situacao: SituacaoItem;
}

export interface Processo {
  id: string;
  tipo: TipoProcesso;
  pedidoId: string;
  pedidoNumero: string;
  status: 'em_andamento' | 'finalizada';
  usuarioInicioId: string;
  usuarioInicioNome: string | null;
  usuarioFimId: string | null;
  dataInicio: string | null;
  dataFim: string | null;
  itens: ItemProcesso[];
}

export interface CredencialGerente {
  usuarioGerente: string;
  senha: string;
}

export function rotuloTipo(tipo: TipoProcesso): string {
  return tipo === 'separacao' ? 'Separação' : 'Conferência';
}

/** Pedidos vindos de integração externa trazem o identificador de lá — quando
 *  presente, é ele que representa o pedido pra quem está olhando. Mesma regra
 *  de `numeroExibicaoPedido` no domínio de pedidos. */
export function numeroExibicao(pedido: { numero: string; sistemaOrigemId: string | null }): string {
  return pedido.sistemaOrigemId || pedido.numero;
}

/** O item em andamento bloqueia todos os outros — é essa a regra que a tela de
 *  itens usa pra desabilitar os botões das outras linhas. */
export function itemEmAndamento(processo: Processo | null): ItemProcesso | undefined {
  return processo?.itens.find((item) => item.situacao === 'em_andamento');
}

/**
 * Situação do pedido no galpão — o filtro de uma linha da listagem.
 *
 * Mora no model, e não na tela, porque virou contrato de API: o valor vai na
 * query string de GET /expedicao/pedidos e é o backend que recorta a base
 * inteira por ele (ver SITUACOES_VALIDAS em expedicao_service.py). Enquanto o
 * filtro era aplicado sobre a página carregada, era detalhe da tela.
 */
export type FiltroSituacao =
  | 'todos'
  | 'nao_iniciados'
  | 'em_separacao'
  | 'aguardando_conferencia'
  | 'em_conferencia'
  | 'concluidos'
  | 'divergentes';

/**
 * Tudo que recorta a listagem. Um objeto e não onze parâmetros posicionais:
 * são todos opcionais entre si, e a ordem deles não significa nada para quem lê
 * a chamada.
 *
 * TODOS vão para o servidor. Nenhum filtra a lista já carregada — com ~230 mil
 * pedidos, o que chega na tela é uma amostra, e recortar a amostra responde
 * "não achei" para pedido que existe na página seguinte.
 */
export interface FiltrosPedidoExpedicao {
  page: number;
  perPage: number;
  dataInicio: string;
  dataFim: string;
  q: string;
  statusPedido: string[];
  /** Vazio = todas as empresas. */
  empresaId: string;
  /** Quem abriu a separação ou a conferência. Vazio = qualquer um. */
  operadorId: string;
  situacao: FiltroSituacao;
  sort: string;
  sortType: string;
}
