export interface Empresa {
  id: string;
  codigo: string | null;
  razaoSocial: string;
  nomeFantasia: string;
  /** Nome curto pelo qual a empresa é chamada no dia a dia ("MTZ", "BSB").
   *  Nulo enquanto ninguém cadastrar — quem exibe decide o fallback. */
  apelido: string | null;
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
