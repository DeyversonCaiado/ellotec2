import { PermissaoKey } from '../../core/permissions/permission.model';

export interface Usuario {
  id: string;
  usuario: string;
  nome: string;
  email: string;
  cargoId: string;
  cargoNome: string;
  ativo: boolean;
  permissoes: PermissaoKey[];
  criadoEm: string;
}

/** Payload de criação/edição — sem os campos derivados pelo backend. */
export type UsuarioFormulario = Omit<Usuario, 'id' | 'criadoEm' | 'cargoNome'>;

/** Versão enxuta (GET /usuarios/vendedores) — só id + nome, exige apenas
 *  estar autenticado, sem precisar da permissão usuarios.acessar. Usada por
 *  outros domínios que só precisam resolver "quem é esse usuário" (ex:
 *  vendedor de um pedido). */
export interface UsuarioResumo {
  id: string;
  nome: string;
}

/** Formato de resposta do GET /usuarios (paginado). */
export interface UsuarioListaPaginada {
  items: Usuario[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}
