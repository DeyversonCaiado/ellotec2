/**
 * Estoque: o saldo do produto na empresa e o mesmo saldo aberto por lote.
 *
 * Espelha os contratos do backend (`app/domains/estoque/`). Quem alimenta as
 * duas tabelas é a integração do ERP — esta tela é de CONSULTA, e é por isso
 * que não existe formulário aqui.
 */

export interface SaldoEstoque {
  id: string;
  produtoId: string;
  /** Código e descrição vêm do cadastro VIVO do produto — a tabela de estoque
   *  guarda só o id. Vazios quando o produto não tem mais cadastro vivo. */
  produtoCodigo: string;
  produtoDescricao: string;
  empresaId: string;
  quantidade: number;
  sistemaOrigemId: string | null;
  empresaSistemaOrigemId: string | null;
  criadoEm: string;
}

export interface LoteEstoque {
  id: string;
  produtoId: string;
  /** Código e descrição vêm do cadastro VIVO do produto — a tabela de estoque
   *  guarda só o id. Vazios quando o produto não tem mais cadastro vivo. */
  produtoCodigo: string;
  produtoDescricao: string;
  empresaId: string;
  lote: string;
  quantidade: number;
  /** Datas de negócio, não auditoria: é delas que sai o FEFO e o bloqueio de
   *  mercadoria vencida. Nulas em produto sem controle de validade. */
  fabricacao: string | null;
  vencimento: string | null;
  sistemaOrigemId: string | null;
  empresaSistemaOrigemId: string | null;
  criadoEm: string;
}

export interface SaldoListaPaginada {
  items: SaldoEstoque[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}

export interface LoteListaPaginada {
  items: LoteEstoque[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}

/** Qual das duas visões a tela está mostrando. */
export type AbaEstoque = 'saldos' | 'lotes';
