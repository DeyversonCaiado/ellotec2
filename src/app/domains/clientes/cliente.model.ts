export interface Cliente {
  id: string;
  codigo: string | null;
  razaoSocial: string;
  nomeFantasia: string;
  cpfCnpj: string;
  email: string | null;
  telefone: string;
  celular: string | null;
  logradouro: string | null;
  numero: string | null;
  complemento: string | null;
  bairro: string | null;
  cep: string | null;
  cidadeId: string;
  cidadeNome: string;
  cidadeUf: string;
  ativo: boolean;
  criadoEm: string;
}

export type ClienteFormulario = Omit<Cliente, 'id' | 'criadoEm' | 'cidadeNome' | 'cidadeUf'>;

/** Formato de resposta do GET /clientes (paginado). */
export interface ClienteListaPaginada {
  items: Cliente[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}
