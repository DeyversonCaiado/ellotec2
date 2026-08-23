import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, delay, tap, throwError } from 'rxjs';
import { environment } from '../../environments/environment';
import { LoginPayload, LoginResponse, UsuarioLogado, UsuarioLogadoComSet } from './auth.models';
import { PermissaoKey } from '../permissions/permission.model';
import { todasAsChaves } from '../navegacao/navegacao.model';

const STORAGE_TOKEN_KEY = 'ellotec_erp_token';
const STORAGE_REFRESH_KEY = 'ellotec_erp_refresh_token';
const STORAGE_USER_KEY = 'ellotec_erp_usuario';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly _usuario = signal<UsuarioLogadoComSet | null>(this.lerUsuarioPersistido());

  readonly usuario = computed(() => this._usuario());
  readonly estaLogado = computed(() => this._usuario() !== null);

  constructor(private http: HttpClient) {}

  login(payload: LoginPayload): Observable<LoginResponse> {
    const resposta$ = environment.mockAuth
      ? this.loginMock(payload)
      : this.http.post<LoginResponse>(`${environment.apiUrl}/auth/login`, payload);

    return resposta$.pipe(
      tap((resposta) => this.persistirSessao(resposta)),
    );
  }

  logout(): void {
    // Notifica o backend pra revogar a sessão (refresh token no banco)
    const refreshToken = localStorage.getItem(STORAGE_REFRESH_KEY);
    if (refreshToken && !environment.mockAuth) {
      this.http.post(`${environment.apiUrl}/auth/logout`, { refreshToken }).subscribe({
        error: () => {/* silencia erros de logout — o importante é limpar o local */},
      });
    }

    this._usuario.set(null);
    localStorage.removeItem(STORAGE_TOKEN_KEY);
    localStorage.removeItem(STORAGE_REFRESH_KEY);
    localStorage.removeItem(STORAGE_USER_KEY);
  }

  obterToken(): string | null {
    return localStorage.getItem(STORAGE_TOKEN_KEY);
  }

  /**
   * Atualiza o usuário logado em memória (e no localStorage) quando ele
   * edita a própria conta. Sem isso, o AuthService só é atualizado no
   * login — editar as próprias permissões não teria efeito nenhum na UI
   * (menu lateral, guards de rota) até um novo login, mesmo o backend já
   * tendo persistido a mudança.
   */
  atualizarUsuarioLogado(usuario: UsuarioLogado): void {
    if (usuario.id !== this._usuario()?.id) return;

    const atual = this._usuario();
    const usuarioLogado: UsuarioLogado = { ...usuario, avatarUrl: atual?.avatarUrl };
    localStorage.setItem(STORAGE_USER_KEY, JSON.stringify(usuarioLogado));
    this._usuario.set(this.comPermissoesEmSet(usuarioLogado));
  }

  /**
   * Rebusca o usuário logado no backend (GET /auth/me) e realinha o
   * AuthService com o que está no banco agora. Cobre o caso em que OUTRA
   * pessoa (ex: um admin, em outra sessão) altera as permissões de quem
   * está logado nesta aba: o servidor já bloqueia a chamada na hora (403),
   * mas o menu/guards client-side continuariam com o snapshot antigo do
   * login até isso rodar — ver authInterceptor, que chama isto sempre que
   * uma resposta 403 chega.
   */
  sincronizarUsuarioLogado(): Observable<UsuarioLogado | null> {
    if (!this.estaLogado()) return of(null);

    if (environment.mockAuth) {
      const atual = this._usuario();
      return of(atual ? { ...atual, permissoes: [...atual.permissoes] } : null);
    }

    return this.http.get<UsuarioLogado>(`${environment.apiUrl}/auth/me`).pipe(
      tap((usuario) => {
        const atual = this._usuario();
        const usuarioLogado: UsuarioLogado = { ...usuario, avatarUrl: atual?.avatarUrl };
        localStorage.setItem(STORAGE_USER_KEY, JSON.stringify(usuarioLogado));
        this._usuario.set(this.comPermissoesEmSet(usuarioLogado));
      }),
    );
  }

  obterRefreshToken(): string | null {
    return localStorage.getItem(STORAGE_REFRESH_KEY);
  }

  // --- privado -------------------------------------------------------

  private persistirSessao(resposta: LoginResponse): void {
    localStorage.setItem(STORAGE_TOKEN_KEY, resposta.token);
    localStorage.setItem(STORAGE_REFRESH_KEY, resposta.refreshToken);
    localStorage.setItem(STORAGE_USER_KEY, JSON.stringify(resposta.usuario));
    this._usuario.set(this.comPermissoesEmSet(resposta.usuario));
  }

  private lerUsuarioPersistido(): UsuarioLogadoComSet | null {
    const bruto = localStorage.getItem(STORAGE_USER_KEY);
    if (!bruto) return null;
    try {
      return this.comPermissoesEmSet(JSON.parse(bruto) as UsuarioLogado);
    } catch {
      return null;
    }
  }

  private comPermissoesEmSet(usuario: UsuarioLogado): UsuarioLogadoComSet {
    return { ...usuario, permissoes: new Set(usuario.permissoes) };
  }

  private loginMock(payload: LoginPayload): Observable<LoginResponse> {
    const identificador = payload.email ?? payload.usuario ?? '';
    const credenciaisInvalidas = !identificador || !payload.senha || payload.senha.length < 4;
    if (credenciaisInvalidas) {
      return throwError(() => ({ status: 401, message: 'Credenciais inválidas' })).pipe(delay(600));
    }

    const ehAdmin = ['admin@fuseerp.com', 'abbott.keitch'].includes(identificador.toLowerCase());

    const usuario: UsuarioLogado = {
      id: ehAdmin ? 'usr-001' : 'usr-002',
      usuario: ehAdmin ? 'abbott.keitch' : identificador.split('@')[0],
      nome: ehAdmin ? 'Abbott Keitch' : identificador.split('@')[0],
      email: payload.email ?? `${identificador}@fuseerp.com`,
      avatarUrl: undefined,
      permissoes: ehAdmin ? todasAsChaves() : this.permissoesSomenteAcesso(),
    };

    const resposta: LoginResponse = {
      token: 'mock-token-' + Math.random().toString(36).slice(2),
      refreshToken: 'mock-refresh-' + Math.random().toString(36).slice(2),
      usuario,
    };

    return of(resposta).pipe(delay(700));
  }

  private permissoesSomenteAcesso(): PermissaoKey[] {
    return todasAsChaves().filter((chave) => chave.endsWith('.acessar'));
  }
}
