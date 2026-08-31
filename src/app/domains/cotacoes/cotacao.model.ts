/**
 * Cotações (Inteligência de Mercado).
 *
 * Espelha os contratos do backend (`app/domains/cotacoes/`). Os dados NÃO são
 * nossos: vêm do OuroWeb, o SQL Server do Bionexo, lido em modo somente
 * leitura. Por isso esta tela é de CONSULTA e não existe formulário aqui.
 */

export interface CotacaoItem {
  /** O número da cotação no Bionexo (int_IdPdc). Não é único na listagem: a
   *  mesma cotação chega uma vez para cada CNPJ da nossa distribuidora. */
  cotacao: number;
  tituloCotacao: string | null;
  dataVencimento: string | null;
  hospital: string;
  cnpjHospital: string | null;
  cidade: string;
  estado: string | null;
  /** Qual empresa nossa recebeu esta cópia da cotação. */
  empresaId: number | null;
  empresa: string | null;
  /** Código e descrição do produto NO CADASTRO DO HOSPITAL — não é o nosso. */
  codigoProdutoHospital: string | null;
  produtoHospital: string | null;
  quantidadeSolicitada: number | null;
  /** O que nós respondemos. Nulo/zero = item ainda não cotado. */
  quantidadeRespondida: number | null;
  quantidadeFaturada: number | null;
  unidade: string | null;
  precoUnitario: number | null;
}

export interface CotacaoListaPaginada {
  items: CotacaoItem[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}

export interface CotacaoEmpresa {
  id: number;
  nome: string;
}

export interface CotacaoFiltroOpcoes {
  estados: string[];
  empresas: CotacaoEmpresa[];
}

/** Recorte por estado de resposta. Espelha o Literal do backend. */
export type SituacaoResposta = 'todas' | 'respondidas' | 'nao_respondidas';

/** O que a tela manda para a API.
 *
 *  Período é obrigatório — sem ele a consulta varreria a base inteira (são
 *  8 GB), e o backend recusa. A exceção é `cotacao`: quem busca pelo número
 *  não sabe em que data ela vence, então informar o número DISPENSA a data, e
 *  o backend ignora o período nesse caso. */
export interface CotacaoFiltros {
  dataInicio: string;
  dataFim: string;
  /** Número da cotação no Bionexo. Preenchido = o período é ignorado. */
  cotacao: string;
  q: string;
  hospital: string;
  cidade: string;
  estado: string;
  empresaId: string;
  situacao: SituacaoResposta;
}

/** Janela máxima aceita pelo backend. Repetida aqui só para a tela avisar
 *  antes de fazer a chamada — a barreira real continua no servidor. */
export const JANELA_MAXIMA_DIAS = 90;
