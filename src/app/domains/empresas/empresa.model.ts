export interface Empresa {
  id: string;
  codigo: string | null;
  razaoSocial: string;
  nomeFantasia: string;
  cnpj: string;
  ativo: boolean;
  criadoEm: string;
}

export type EmpresaFormulario = Omit<Empresa, 'id' | 'criadoEm'>;

/** Formato de resposta do GET /empresas (paginado). */
export interface EmpresaListaPaginada {
  items: Empresa[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}
