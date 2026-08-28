/**
 * Documento fiscal — entrada e saída são o MESMO registro, distinguidos por
 * `tipoOperacao`. Não existe um modelo `NotaEntrada` e outro `NotaSaida`: no
 * banco é uma tabela só, porque é literalmente o mesmo documento visto dos
 * dois lados (a saída do fornecedor é a nossa entrada).
 *
 * Nenhum campo aqui cita "NFe": `modelo` diz de qual leiaute o registro veio
 * ('55' NF-e, '65' NFC-e, '57' CT-e, 'NFSE'), e todo campo é conceito de
 * negócio que existe nos quatro. O que é específico de um leiaute não vira
 * campo — fica no XML original, que o backend guarda inteiro.
 */

export type TipoOperacao = 'entrada' | 'saida';
export type StatusNota = 'autorizada' | 'cancelada' | 'denegada' | 'rejeitada';

/** O que a LISTAGEM devolve — sem os itens e sem o XML. */
export interface NotaFiscalResumo {
  id: string;
  modelo: string;
  tipoOperacao: TipoOperacao;
  /** Nula em NFS-e, que não tem chave de 44 dígitos. */
  chaveAcesso: string | null;
  numero: string;
  serie: string;
  naturezaOperacao: string;
  dataEmissao: string;
  status: StatusNota;
  empresaId: string;
  emitenteCnpjCpf: string;
  emitenteRazaoSocial: string;
  destinatarioCnpjCpf: string;
  destinatarioRazaoSocial: string;
  valorTotal: number;
  quantidadeVolumes: number | null;
  sistemaOrigemId: string | null;
  // Sem `criadoEm`: ele vinha do `sync_created_at` do backend, e publicar
  // auditoria da linha como fato do documento é o que a regra dos campos
  // `sync*` proíbe (ver ARCHITECTURE.md). A data de negócio da nota é
  // `dataEmissao`.
}

export interface ItemNotaFiscal {
  id: string;
  /** O nItem do documento — a posição do item definida por quem emitiu, não
   *  uma sequência nossa. É por ele que se confere item a item. */
  numeroItem: number;
  /** Nulo quando o produto da nota não existe no cadastro daqui, o que é
   *  normal numa nota de entrada: o produto é do fornecedor. */
  produtoId: string | null;
  produtoCodigo: string;
  produtoDescricao: string;
  codigoBarras: string | null;
  ncm: string | null;
  cfop: string | null;
  unidade: string;
  quantidade: number;
  /** Até 10 casas decimais — é o que o leiaute da NF-e permite em vUnCom. */
  precoUnitario: number;
  valorTotalItem: number;
  valorFrete: number;
  valorDesconto: number;
  cstIcms: string | null;
  aliquotaIcms: number | null;
  valorIcms: number | null;
  valorIcmsSt: number | null;
  cstIpi: string | null;
  aliquotaIpi: number | null;
  valorIpi: number | null;
  lote: string | null;
  validade: string | null;
  informacoesAdicionais: string | null;
}

/** O detalhe de uma nota: o resumo + o que a listagem não carrega. */
export interface NotaFiscal extends NotaFiscalResumo {
  pedidoId: string | null;
  finalidade: string | null;
  dataSaidaEntrada: string | null;
  protocoloAutorizacao: string | null;
  dataAutorizacao: string | null;
  emitenteNomeFantasia: string | null;
  emitenteInscricaoEstadual: string | null;
  emitenteMunicipio: string | null;
  emitenteUf: string | null;
  destinatarioInscricaoEstadual: string | null;
  destinatarioMunicipio: string | null;
  destinatarioUf: string | null;
  valorProdutos: number;
  valorFrete: number;
  valorSeguro: number;
  valorDesconto: number;
  valorOutrasDespesas: number;
  valorIcms: number;
  valorIpi: number;
  transportadoraNome: string | null;
  transportadoraCnpjCpf: string | null;
  modalidadeFrete: string | null;
  pesoBruto: number | null;
  pesoLiquido: number | null;
  informacoesComplementares: string | null;
  itens: ItemNotaFiscal[];
}

/** Formato de resposta do GET /notas-fiscais (paginado). */
export interface NotaFiscalListaPaginada {
  items: NotaFiscalResumo[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}

export interface NotaFiscalXml {
  id: string;
  chaveAcesso: string | null;
  xmlOriginal: string | null;
}

/**
 * Os filtros da tela. Todos vão para o servidor — filtrar no navegador
 * recortaria só a página carregada, e o resultado mudaria conforme a página
 * aberta.
 */
export interface FiltrosNotaFiscal {
  q: string;
  /** Vazio = todas. É este filtro que substitui os dois itens de menu. */
  tipoOperacao: TipoOperacao | '';
  /** Período de EMISSÃO — a data de negócio do documento. */
  dataInicio: string;
  dataFim: string;
}

export const FILTROS_VAZIOS: FiltrosNotaFiscal = {
  q: '',
  tipoOperacao: '',
  dataInicio: '',
  dataFim: '',
};
