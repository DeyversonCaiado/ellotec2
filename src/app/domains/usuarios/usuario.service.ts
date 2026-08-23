import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, delay, map, of, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { Usuario, UsuarioFormulario, UsuarioListaPaginada, UsuarioResumo } from './usuario.model';
import { todasAsChaves } from '../../core/navegacao/navegacao.model';
import { CargoService } from './cargo.service';

const ENDPOINT = `${environment.apiUrl}/usuarios`;

/**
 * Mesmo padrão do AuthService: quando environment.mockAuth está ligado,
 * os métodos resolvem com dados fictícios em vez de chamar a API — mas
 * a assinatura (Observable<Usuario[]>, etc.) é a mesma dos dois jeitos,
 * então essa classe é o único lugar que muda quando o backend existir.
 */
@Injectable({ providedIn: 'root' })
export class UsuarioService {
  private readonly _usuarios = signal<Usuario[]>(this.dadosFicticios());
  readonly usuarios = this._usuarios.asReadonly();

  constructor(
    private http: HttpClient,
    private cargoService: CargoService,
  ) {}

  listar(): Observable<Usuario[]> {
    if (environment.mockAuth) {
      return of(this._usuarios()).pipe(delay(400));
    }
    return this.http.get<UsuarioListaPaginada>(ENDPOINT).pipe(
      map((resposta) => resposta.items),
      tap((lista) => this._usuarios.set(lista)),
    );
  }

  /** Canal leve pra quem só precisa de "nome de usuários ativos pra escolher
   *  num select" (ex: vendedor de pedido) — não exige usuarios.acessar. */
  listarVendedores(): Observable<UsuarioResumo[]> {
    if (environment.mockAuth) {
      return of(this._usuarios().filter((u) => u.ativo).map((u) => ({ id: u.id, nome: u.nome }))).pipe(delay(200));
    }
    return this.http.get<UsuarioResumo[]>(`${ENDPOINT}/vendedores`);
  }

  /** Busca uma página de usuários no backend, com filtro opcional por nome/e-mail/usuário. */
  listarPagina(page: number, perPage: number, busca: string): Observable<UsuarioListaPaginada> {
    if (environment.mockAuth) {
      const termo = busca.toLowerCase().trim();
      const filtrados = termo
        ? this._usuarios().filter((u) => u.nome.toLowerCase().includes(termo) || u.email.toLowerCase().includes(termo))
        : this._usuarios();
      const inicio = (page - 1) * perPage;
      return of({
        items: filtrados.slice(inicio, inicio + perPage),
        total: filtrados.length,
        page,
        perPage,
        sort: 'sync_created_at',
        sortType: 'desc',
      }).pipe(delay(400));
    }
    return this.http.get<UsuarioListaPaginada>(ENDPOINT, {
      params: { page, perPage, busca: busca.trim() },
    });
  }

  obterPorId(id: string): Observable<Usuario | undefined> {
    if (environment.mockAuth) {
      return of(this._usuarios().find((u) => u.id === id)).pipe(delay(300));
    }
    return this.http.get<Usuario>(`${ENDPOINT}/${id}`);
  }

  criar(dados: UsuarioFormulario): Observable<Usuario> {
    if (environment.mockAuth) {
      const novo: Usuario = {
        ...dados,
        id: 'usr-' + Math.random().toString(36).slice(2, 8),
        cargoNome: this.cargoService.cargos().find((c) => c.id === dados.cargoId)?.nome ?? '',
        criadoEm: new Date().toISOString(),
      };
      this._usuarios.update((lista) => [novo, ...lista]);
      return of(novo).pipe(delay(400));
    }
    return this.http.post<Usuario>(ENDPOINT, dados).pipe(tap((novo) => this._usuarios.update((lista) => [novo, ...lista])));
  }

  atualizar(id: string, dados: UsuarioFormulario): Observable<Usuario> {
    if (environment.mockAuth) {
      const existente = this._usuarios().find((u) => u.id === id);
      const atualizado: Usuario = {
        ...dados,
        id,
        cargoNome: this.cargoService.cargos().find((c) => c.id === dados.cargoId)?.nome ?? existente?.cargoNome ?? '',
        criadoEm: existente?.criadoEm ?? new Date().toISOString(),
      };
      this._usuarios.update((lista) => lista.map((u) => (u.id === id ? atualizado : u)));
      return of(atualizado).pipe(delay(400));
    }
    return this.http.put<Usuario>(`${ENDPOINT}/${id}`, dados).pipe(
      tap((atualizado) => this._usuarios.update((lista) => lista.map((u) => (u.id === id ? atualizado : u)))),
    );
  }

  apagar(id: string): Observable<void> {
    if (environment.mockAuth) {
      this._usuarios.update((lista) => lista.filter((u) => u.id !== id));
      return of(undefined).pipe(delay(300));
    }
    return this.http.delete<void>(`${ENDPOINT}/${id}`).pipe(tap(() => this._usuarios.update((lista) => lista.filter((u) => u.id !== id))));
  }

  private dadosFicticios(): Usuario[] {
    return [
      {
        id: 'usr-001',
        usuario: 'abbott.keitch',
        nome: 'Abbott Keitch',
        email: 'admin@fuseerp.com',
        cargoId: 'crg-001',
        cargoNome: 'Gerente',
        ativo: true,
        permissoes: todasAsChaves(),
        criadoEm: '2026-01-12T10:00:00Z',
      },
      {
        id: 'usr-002',
        usuario: 'mariana.silva',
        nome: 'Mariana Silva',
        email: 'mariana.silva@fuseerp.com',
        cargoId: 'crg-002',
        cargoNome: 'Funcionario',
        ativo: true,
        permissoes: [
          'clientes.acessar',
          'clientes.gravar.incluir',
          'clientes.gravar.editar',
          'produtos.acessar',
          'pedidos.acessar',
          'pedidos.gravar.incluir',
          'pedidos.gravar.editar',
        ],
        criadoEm: '2026-02-03T14:30:00Z',
      },
      {
        id: 'usr-003',
        usuario: 'carlos.eduardo',
        nome: 'Carlos Eduardo',
        email: 'carlos.eduardo@fuseerp.com',
        cargoId: 'crg-002',
        cargoNome: 'Funcionario',
        ativo: false,
        permissoes: [],
        criadoEm: '2026-03-18T09:15:00Z',
      },
    ];
  }
}
