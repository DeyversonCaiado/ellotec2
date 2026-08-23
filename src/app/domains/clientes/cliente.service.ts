import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, delay, map, of, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { Cliente, ClienteFormulario, ClienteListaPaginada } from './cliente.model';

const ENDPOINT = `${environment.apiUrl}/clientes`;

@Injectable({ providedIn: 'root' })
export class ClienteService {
  private readonly _clientes = signal<Cliente[]>(this.dadosFicticios());
  readonly clientes = this._clientes.asReadonly();

  constructor(private http: HttpClient) {}

  listar(): Observable<Cliente[]> {
    if (environment.mockAuth) {
      return of(this._clientes()).pipe(delay(400));
    }
    return this.http.get<ClienteListaPaginada>(ENDPOINT).pipe(
      map((resposta) => resposta.items),
      tap((lista) => this._clientes.set(lista)),
    );
  }

  /** Busca uma página de clientes no backend, com filtro opcional por razão social/fantasia/CPF-CNPJ. */
  listarPagina(page: number, perPage: number, q: string): Observable<ClienteListaPaginada> {
    if (environment.mockAuth) {
      const termo = q.toLowerCase().trim();
      const filtrados = termo
        ? this._clientes().filter(
            (c) =>
              c.razaoSocial.toLowerCase().includes(termo) ||
              c.nomeFantasia.toLowerCase().includes(termo) ||
              c.cpfCnpj.includes(termo),
          )
        : this._clientes();
      const inicio = (page - 1) * perPage;
      return of({
        items: filtrados.slice(inicio, inicio + perPage),
        total: filtrados.length,
        page,
        perPage,
        sort: 'nome_fantasia',
        sortType: 'asc',
      }).pipe(delay(400));
    }
    return this.http.get<ClienteListaPaginada>(ENDPOINT, { params: { page, perPage, q: q.trim() } });
  }

  obterPorId(id: string): Observable<Cliente | undefined> {
    if (environment.mockAuth) {
      return of(this._clientes().find((c) => c.id === id)).pipe(delay(300));
    }
    return this.http.get<Cliente>(`${ENDPOINT}/${id}`);
  }

  /** Busca leve usada pelo domínio de pedidos pra localizar um cliente por nome/CPF/CNPJ. */
  buscar(termo: string): Observable<Cliente[]> {
    return this.listarPagina(1, 15, termo).pipe(map((resposta) => resposta.items));
  }

  criar(dados: ClienteFormulario): Observable<Cliente> {
    if (environment.mockAuth) {
      const novo: Cliente = {
        ...dados,
        id: 'cli-' + Math.random().toString(36).slice(2, 8),
        cidadeNome: '',
        cidadeUf: '',
        criadoEm: new Date().toISOString(),
      };
      this._clientes.update((lista) => [novo, ...lista]);
      return of(novo).pipe(delay(400));
    }
    return this.http.post<Cliente>(ENDPOINT, dados).pipe(tap((novo) => this._clientes.update((lista) => [novo, ...lista])));
  }

  atualizar(id: string, dados: ClienteFormulario): Observable<Cliente> {
    if (environment.mockAuth) {
      const existente = this._clientes().find((c) => c.id === id);
      const atualizado: Cliente = {
        ...dados,
        id,
        cidadeNome: existente?.cidadeNome ?? '',
        cidadeUf: existente?.cidadeUf ?? '',
        criadoEm: existente?.criadoEm ?? new Date().toISOString(),
      };
      this._clientes.update((lista) => lista.map((c) => (c.id === id ? atualizado : c)));
      return of(atualizado).pipe(delay(400));
    }
    return this.http.put<Cliente>(`${ENDPOINT}/${id}`, dados).pipe(
      tap((atualizado) => this._clientes.update((lista) => lista.map((c) => (c.id === id ? atualizado : c)))),
    );
  }

  apagar(id: string): Observable<void> {
    if (environment.mockAuth) {
      this._clientes.update((lista) => lista.filter((c) => c.id !== id));
      return of(undefined).pipe(delay(300));
    }
    return this.http.delete<void>(`${ENDPOINT}/${id}`).pipe(tap(() => this._clientes.update((lista) => lista.filter((c) => c.id !== id))));
  }

  private dadosFicticios(): Cliente[] {
    return [
      { id: 'cli-001', codigo: 'CLI001', razaoSocial: 'Distribuidora Saúde Total Ltda', nomeFantasia: 'Saúde Total', cpfCnpj: '12.345.678/0001-90', email: 'compras@saudetotal.com.br', telefone: '(62) 3201-4455', celular: null, logradouro: null, numero: null, complemento: null, bairro: null, cep: null, cidadeId: 'cid-001', cidadeNome: 'Goiânia', cidadeUf: 'GO', ativo: true, criadoEm: '2025-11-02T10:00:00Z' },
      { id: 'cli-002', codigo: 'CLI002', razaoSocial: 'Hospital Vida Plena S.A.', nomeFantasia: 'Vida Plena', cpfCnpj: '23.456.789/0001-11', email: 'suprimentos@vidaplena.com.br', telefone: '(62) 3322-7788', celular: null, logradouro: null, numero: null, complemento: null, bairro: null, cep: null, cidadeId: 'cid-002', cidadeNome: 'Anápolis', cidadeUf: 'GO', ativo: true, criadoEm: '2025-12-15T09:30:00Z' },
      { id: 'cli-003', codigo: 'CLI003', razaoSocial: 'Farmácia Popular Center Oeste', nomeFantasia: 'Popular Center Oeste', cpfCnpj: '34.567.890/0001-22', email: 'contato@popularco.com.br', telefone: '(64) 3411-2200', celular: null, logradouro: null, numero: null, complemento: null, bairro: null, cep: null, cidadeId: 'cid-003', cidadeNome: 'Rio Verde', cidadeUf: 'GO', ativo: false, criadoEm: '2026-01-20T11:45:00Z' },
    ];
  }
}
