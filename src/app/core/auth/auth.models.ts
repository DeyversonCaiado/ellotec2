import { PermissaoKey } from '../permissions/permission.model';

/** Usuário autenticado, guardado em memória/sessão após login.
 * `permissoes` chega do backend como array de chaves (JSON) — é convertido
 * para Set na hidratação da sessão em AuthService, ver `usuarioComPermissoesEmSet`. */
export interface UsuarioLogado {
  id: string;
  usuario: string;
  nome: string;
  email: string;
  avatarUrl?: string;
  permissoes: PermissaoKey[];
}

/** Forma em memória, com o Set já hidratado — o que `AuthService.usuario()` expõe. */
export interface UsuarioLogadoComSet extends Omit<UsuarioLogado, 'permissoes'> {
  permissoes: Set<PermissaoKey>;
}

export interface LoginPayload {
  email?: string;
  usuario?: string;
  senha: string;
}

export interface LoginResponse {
  token: string;
  refreshToken: string;
  usuario: UsuarioLogado;
}
