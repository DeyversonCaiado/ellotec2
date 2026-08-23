export interface Cidade {
  id: string;
  codigoMunicipio: number;
  nome: string;
  uf: string;
  criadoEm: string;
}

export type CidadeFormulario = Omit<Cidade, 'id' | 'criadoEm'>;

/** Formato de resposta do GET /cidades (paginado). */
export interface CidadeListaPaginada {
  items: Cidade[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}
