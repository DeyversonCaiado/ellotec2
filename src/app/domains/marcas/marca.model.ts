export interface Marca {
  id: string;
  nome: string;
  ativo: boolean;
  criadoEm: string;
}

export type MarcaFormulario = Omit<Marca, 'id' | 'criadoEm'>;

/** Formato de resposta do GET /marcas (paginado). */
export interface MarcaListaPaginada {
  items: Marca[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}
