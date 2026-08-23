import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, delay, map, of, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { Cidade, CidadeFormulario, CidadeListaPaginada } from './cidade.model';

const ENDPOINT = `${environment.apiUrl}/cidades`;

@Injectable({ providedIn: 'root' })
export class CidadeService {
  private readonly _cidades = signal<Cidade[]>(this.dadosFicticios());
  readonly cidades = this._cidades.asReadonly();

  constructor(private http: HttpClient) {}

  listar(): Observable<Cidade[]> {
    if (environment.mockAuth) {
      return of(this._cidades()).pipe(delay(400));
    }
    return this.http.get<CidadeListaPaginada>(ENDPOINT).pipe(
      map((resposta) => resposta.items),
      tap((lista) => this._cidades.set(lista)),
    );
  }

  /** Busca uma página de cidades no backend, com filtro opcional por nome/UF. */
  listarPagina(page: number, perPage: number, busca: string): Observable<CidadeListaPaginada> {
    if (environment.mockAuth) {
      const termo = busca.toLowerCase().trim();
      const filtradas = termo
        ? this._cidades().filter((c) => c.nome.toLowerCase().includes(termo) || c.uf.toLowerCase().includes(termo))
        : this._cidades();
      const inicio = (page - 1) * perPage;
      return of({
        items: filtradas.slice(inicio, inicio + perPage),
        total: filtradas.length,
        page,
        perPage,
        sort: 'nome',
        sortType: 'asc',
      }).pipe(delay(400));
    }
    return this.http.get<CidadeListaPaginada>(ENDPOINT, {
      params: { page, perPage, busca: busca.trim() },
    });
  }

  obterPorId(id: string): Observable<Cidade | undefined> {
    if (environment.mockAuth) {
      return of(this._cidades().find((c) => c.id === id)).pipe(delay(300));
    }
    return this.http.get<Cidade>(`${ENDPOINT}/${id}`);
  }

  /** Busca leve usada por outros domínios pra localizar uma cidade por nome/UF. */
  buscar(termo: string): Observable<Cidade[]> {
    return this.listarPagina(1, 15, termo).pipe(map((resposta) => resposta.items));
  }

  criar(dados: CidadeFormulario): Observable<Cidade> {
    if (environment.mockAuth) {
      const nova: Cidade = { ...dados, id: 'cid-' + Math.random().toString(36).slice(2, 8), criadoEm: new Date().toISOString() };
      this._cidades.update((lista) => [nova, ...lista]);
      return of(nova).pipe(delay(400));
    }
    return this.http.post<Cidade>(ENDPOINT, dados).pipe(tap((nova) => this._cidades.update((lista) => [nova, ...lista])));
  }

  atualizar(id: string, dados: CidadeFormulario): Observable<Cidade> {
    if (environment.mockAuth) {
      const atualizada: Cidade = { ...dados, id, criadoEm: this._cidades().find((c) => c.id === id)?.criadoEm ?? new Date().toISOString() };
      this._cidades.update((lista) => lista.map((c) => (c.id === id ? atualizada : c)));
      return of(atualizada).pipe(delay(400));
    }
    return this.http.put<Cidade>(`${ENDPOINT}/${id}`, dados).pipe(
      tap((atualizada) => this._cidades.update((lista) => lista.map((c) => (c.id === id ? atualizada : c)))),
    );
  }

  apagar(id: string): Observable<void> {
    if (environment.mockAuth) {
      this._cidades.update((lista) => lista.filter((c) => c.id !== id));
      return of(undefined).pipe(delay(300));
    }
    return this.http.delete<void>(`${ENDPOINT}/${id}`).pipe(tap(() => this._cidades.update((lista) => lista.filter((c) => c.id !== id))));
  }

  private dadosFicticios(): Cidade[] {
    return [
      { id: 'cid-001', codigoMunicipio: 5208707, nome: 'Goiânia', uf: 'GO', criadoEm: '2025-11-02T10:00:00Z' },
      { id: 'cid-002', codigoMunicipio: 5201108, nome: 'Anápolis', uf: 'GO', criadoEm: '2025-12-15T09:30:00Z' },
      { id: 'cid-003', codigoMunicipio: 5218805, nome: 'Rio Verde', uf: 'GO', criadoEm: '2026-01-20T11:45:00Z' },
    ];
  }
}
