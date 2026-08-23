// Não é mais um conjunto fechado de 4 valores — o catálogo pedido_status no
// backend é administrável e hoje já tem chaves de integração externa (ex:
// "OK", "FEC", "PCP") além das 4 originais. Ver rotuloStatus/corStatus em
// pedido-list.ts para o fallback usado quando a chave não é uma das conhecidas.
export type StatusPedido = string;

export interface ItemPedido {
  produtoId: string;
  produtoCodigo: string;
  produtoDescricao: string;
  quantidade: number;
  precoUnitario: number;
}

export interface Pedido {
  id: string;
  numero: string;
  dataPedido: string;
  clienteId: string;
  cliente: { id: string; nomeFantasia: string; cnpj: string };
  empresaId: string;
  vendedorId: string | null;
  sistemaOrigemId: string | null;
  itens: ItemPedido[];
  status: StatusPedido;
  statusId: string;
  observacoes: string;
  criadoEm: string;
}

/** Resposta do GET /pedidos, paginado no banco: são ~230 mil pedidos, e
 *  trazer tudo (com os itens de cada um) derruba a API antes do navegador.
 *  Mesmo formato dos outros domínios — ver ProdutoListaPaginada. */
export interface PedidoListaPaginada {
  items: Pedido[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}

// Item do catálogo pedido_status (GET /pedidos/status) — usado pro select de
// status no formulário, já que status não é mais um enum fechado de 4
// valores (ver StatusPedido acima).
export interface PedidoStatusCatalogo {
  id: string;
  chave: string;
}

export interface PedidoFormulario {
  dataPedido: string;
  clienteId: string;
  /** Snapshot do cliente na emissão. O backend não consulta o cadastro de
   *  clientes — grava o que vem aqui, e o pedido não muda depois se o
   *  cadastro do cliente mudar. */
  clienteNomeFantasia: string;
  clienteCnpj: string;
  empresaId: string;
  vendedorId: string | null;
  itens: ItemPedido[];
  statusId: string;
  observacoes: string;
}

export function calcularTotalPedido(itens: ItemPedido[]): number {
  return (itens ?? []).reduce((soma, item) => soma + item.quantidade * item.precoUnitario, 0);
}

// Pedidos vindos de integração externa trazem o identificador de lá em
// sistemaOrigemId — quando presente, é ele que representa o pedido pra quem
// está olhando, não o número sequencial interno.
export function numeroExibicaoPedido(pedido: Pedido): string {
  return pedido.sistemaOrigemId || pedido.numero;
}
