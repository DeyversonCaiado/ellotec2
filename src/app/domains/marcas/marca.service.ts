import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, delay, map, of, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { Marca, MarcaFormulario, MarcaListaPaginada } from './marca.model';

const ENDPOINT = `${environment.apiUrl}/marcas`;

@Injectable({ providedIn: 'root' })
export class MarcaService {
  private readonly _marcas = signal<Marca[]>(this.dadosFicticios());
  readonly marcas = this._marcas.asReadonly();

  constructor(private http: HttpClient) {}

  listar(): Observable<Marca[]> {
    if (environment.mockAuth) {
      return of(this._marcas()).pipe(delay(400));
    }
    return this.http.get<MarcaListaPaginada>(ENDPOINT).pipe(
      map((resposta) => resposta.items),
      tap((lista) => this._marcas.set(lista)),
    );
  }

  /** Busca uma página de marcas no backend, com filtro opcional por nome. */
  listarPagina(page: number, perPage: number, q: string): Observable<MarcaListaPaginada> {
    if (environment.mockAuth) {
      const termo = q.toLowerCase().trim();
      const filtradas = termo ? this._marcas().filter((m) => m.nome.toLowerCase().includes(termo)) : this._marcas();
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
    return this.http.get<MarcaListaPaginada>(ENDPOINT, { params: { page, perPage, q: q.trim() } });
  }

  obterPorId(id: string): Observable<Marca | undefined> {
    if (environment.mockAuth) {
      return of(this._marcas().find((m) => m.id === id)).pipe(delay(300));
    }
    return this.http.get<Marca>(`${ENDPOINT}/${id}`);
  }

  criar(dados: MarcaFormulario): Observable<Marca> {
    if (environment.mockAuth) {
      const nova: Marca = { ...dados, id: 'mrc-' + Math.random().toString(36).slice(2, 8), criadoEm: new Date().toISOString() };
      this._marcas.update((lista) => [nova, ...lista]);
      return of(nova).pipe(delay(400));
    }
    return this.http.post<Marca>(ENDPOINT, dados).pipe(tap((nova) => this._marcas.update((lista) => [nova, ...lista])));
  }

  atualizar(id: string, dados: MarcaFormulario): Observable<Marca> {
    if (environment.mockAuth) {
      const atualizada: Marca = { ...dados, id, criadoEm: this._marcas().find((m) => m.id === id)?.criadoEm ?? new Date().toISOString() };
      this._marcas.update((lista) => lista.map((m) => (m.id === id ? atualizada : m)));
      return of(atualizada).pipe(delay(400));
    }
    return this.http.put<Marca>(`${ENDPOINT}/${id}`, dados).pipe(
      tap((atualizada) => this._marcas.update((lista) => lista.map((m) => (m.id === id ? atualizada : m)))),
    );
  }

  apagar(id: string): Observable<void> {
    if (environment.mockAuth) {
      this._marcas.update((lista) => lista.filter((m) => m.id !== id));
      return of(undefined).pipe(delay(300));
    }
    return this.http.delete<void>(`${ENDPOINT}/${id}`).pipe(tap(() => this._marcas.update((lista) => lista.filter((m) => m.id !== id))));
  }

  private dadosFicticios(): Marca[] {
    return [
      { id: 'mrc-001', nome: 'Descarpack', ativo: true, criadoEm: '2025-10-05T08:00:00Z' },
      { id: 'mrc-002', nome: 'BD', ativo: true, criadoEm: '2025-10-12T08:00:00Z' },
      { id: 'mrc-003', nome: 'Cremer', ativo: true, criadoEm: '2025-11-20T08:00:00Z' },
    ];
  }
}
