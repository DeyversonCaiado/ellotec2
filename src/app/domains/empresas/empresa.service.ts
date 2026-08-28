import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, delay, map, of, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { Empresa, EmpresaFormulario, EmpresaListaPaginada } from './empresa.model';

const ENDPOINT = `${environment.apiUrl}/empresas`;

@Injectable({ providedIn: 'root' })
export class EmpresaService {
  private readonly _empresas = signal<Empresa[]>(this.dadosFicticios());
  readonly empresas = this._empresas.asReadonly();

  constructor(private http: HttpClient) {}

  listar(): Observable<Empresa[]> {
    if (environment.mockAuth) {
      return of(this._empresas()).pipe(delay(400));
    }
    return this.http.get<EmpresaListaPaginada>(ENDPOINT).pipe(
      map((resposta) => resposta.items),
      tap((lista) => this._empresas.set(lista)),
    );
  }

  /** Busca uma página de empresas no backend, com filtro opcional por razão social/fantasia/CNPJ. */
  listarPagina(page: number, perPage: number, q: string): Observable<EmpresaListaPaginada> {
    if (environment.mockAuth) {
      const termo = q.toLowerCase().trim();
      const filtradas = termo
        ? this._empresas().filter(
            (e) =>
              e.razaoSocial.toLowerCase().includes(termo) ||
              e.nomeFantasia.toLowerCase().includes(termo) ||
              e.cnpj.includes(termo),
          )
        : this._empresas();
      const inicio = (page - 1) * perPage;
      return of({
        items: filtradas.slice(inicio, inicio + perPage),
        total: filtradas.length,
        page,
        perPage,
        sort: 'razao_social',
        sortType: 'asc',
      }).pipe(delay(400));
    }
    return this.http.get<EmpresaListaPaginada>(ENDPOINT, { params: { page, perPage, q: q.trim() } });
  }

  /** Busca leve usada pelo domínio de pedidos pra localizar uma empresa por nome/CNPJ. */
  buscar(termo: string): Observable<Empresa[]> {
    return this.listarPagina(1, 15, termo).pipe(map((resposta) => resposta.items));
  }

  obterPorId(id: string): Observable<Empresa | undefined> {
    if (environment.mockAuth) {
      return of(this._empresas().find((e) => e.id === id)).pipe(delay(300));
    }
    return this.http.get<Empresa>(`${ENDPOINT}/${id}`);
  }

  criar(dados: EmpresaFormulario): Observable<Empresa> {
    if (environment.mockAuth) {
      const nova: Empresa = { ...dados, id: 'emp-' + Math.random().toString(36).slice(2, 8), criadoEm: new Date().toISOString() };
      this._empresas.update((lista) => [nova, ...lista]);
      return of(nova).pipe(delay(400));
    }
    return this.http.post<Empresa>(ENDPOINT, dados).pipe(tap((nova) => this._empresas.update((lista) => [nova, ...lista])));
  }

  atualizar(id: string, dados: EmpresaFormulario): Observable<Empresa> {
    if (environment.mockAuth) {
      const atualizada: Empresa = { ...dados, id, criadoEm: this._empresas().find((e) => e.id === id)?.criadoEm ?? new Date().toISOString() };
      this._empresas.update((lista) => lista.map((e) => (e.id === id ? atualizada : e)));
      return of(atualizada).pipe(delay(400));
    }
    return this.http.put<Empresa>(`${ENDPOINT}/${id}`, dados).pipe(
      tap((atualizada) => this._empresas.update((lista) => lista.map((e) => (e.id === id ? atualizada : e)))),
    );
  }

  apagar(id: string): Observable<void> {
    if (environment.mockAuth) {
      this._empresas.update((lista) => lista.filter((e) => e.id !== id));
      return of(undefined).pipe(delay(300));
    }
    return this.http.delete<void>(`${ENDPOINT}/${id}`).pipe(tap(() => this._empresas.update((lista) => lista.filter((e) => e.id !== id))));
  }

  private dadosFicticios(): Empresa[] {
    return [
      { id: 'emp-001', codigo: 'MATRIZ', razaoSocial: 'Ellotec Matriz Ltda', nomeFantasia: 'Ellotec', apelido: 'MTZ', cnpj: '00.000.000/0001-00', ativo: true, criadoEm: '2025-10-01T08:00:00Z' },
    ];
  }
}
