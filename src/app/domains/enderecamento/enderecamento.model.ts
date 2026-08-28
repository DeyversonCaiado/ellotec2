/**
 * Endereçamento: os lugares do galpão e o lote guardado em cada um.
 *
 * Espelha os contratos do backend (`app/domains/enderecamento/`). O endereço
 * NÃO mora mais na linha do pedido — ele é do estoque, e a relação com o lote
 * é muitos-para-muitos: um lote se espalha por vários endereços.
 */

export interface EnderecoEstoque {
  id: string;
  descricao: string;
  empresaId: string;
  sistemaOrigemId: string | null;
  empresaSistemaOrigemId: string | null;
  criadoEm: string;
}

/** O que o formulário envia. A empresa é obrigatória: o mesmo código de
 *  prateleira existe em cada filial, então quem identifica o endereço é o par
 *  com a empresa, não a descrição sozinha. */
export interface EnderecoFormulario {
  descricao: string;
  empresaId: string;
}

export interface EnderecoListaPaginada {
  items: EnderecoEstoque[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}

/** Onde um lote está guardado — a linha de `estoque_endereco_lote`, já
 *  resolvida com o lote e o produto que vêm das bordas de `estoque` e
 *  `produtos`. É esta a linha da consulta "onde está este produto". */
export interface VinculoEnderecoLote {
  id: string;
  estoqueEnderecosId: string;
  estoqueLotesId: string;
  enderecoDescricao: string;
  /** Quanto daquele lote está NESTE endereço. */
  quantidade: number;
  lote: string;
  produtoId: string;
  produtoCodigo: string;
  produtoDescricao: string;
  empresaId: string;
  sistemaOrigemId: string | null;
  empresaSistemaOrigemId: string | null;
  criadoEm: string;
}

/** As duas visões da tela de endereçamento. `vinculos` é a padrão: a pergunta
 *  que se faz no dia a dia é "onde está este produto", não "que prateleiras
 *  existem". */
export type AbaEnderecamento = 'vinculos' | 'enderecos';

export interface VinculoListaPaginada {
  items: VinculoEnderecoLote[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}
