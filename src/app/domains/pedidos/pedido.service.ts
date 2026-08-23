import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, delay, of, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { Pedido, PedidoFormulario, PedidoListaPaginada, PedidoStatusCatalogo } from './pedido.model';

const ENDPOINT = `${environment.apiUrl}/pedidos`;

@Injectable({ providedIn: 'root' })
export class PedidoService {
  private readonly _pedidos = signal<Pedido[]>(this.dadosFicticios());
  readonly pedidos = this._pedidos.asReadonly();

  constructor(private http: HttpClient) {}

  /** Uma página de pedidos. A busca vai para o SERVIDOR: filtrar a página
   *  carregada daria 3 linhas de 20 e um total que não corresponde ao que se vê. */
  listarPagina(
    page: number,
    perPage: number,
    q = '',
    sort = 'data_pedido',
    sortType = 'desc',
  ): Observable<PedidoListaPaginada> {
    if (environment.mockAuth) {
      const items = this._pedidos();
      return of({
        items,
        total: items.length,
        page: 1,
        perPage,
        sort,
        sortType,
      }).pipe(delay(400));
    }
    return this.http
      .get<PedidoListaPaginada>(ENDPOINT, {
        params: { page, perPage, sort, sortType, q: q.trim() },
      })
      .pipe(tap((pagina) => this._pedidos.set(pagina.items)));
  }

  listarStatus(): Observable<PedidoStatusCatalogo[]> {
    if (environment.mockAuth) {
      return of(this.statusFicticios()).pipe(delay(200));
    }
    return this.http.get<PedidoStatusCatalogo[]>(`${ENDPOINT}/status`);
  }

  obterPorId(id: string): Observable<Pedido | undefined> {
    if (environment.mockAuth) {
      return of(this._pedidos().find((o) => o.id === id)).pipe(delay(300));
    }
    return this.http.get<Pedido>(`${ENDPOINT}/${id}`);
  }

  criar(dados: PedidoFormulario): Observable<Pedido> {
    if (environment.mockAuth) {
      const proximoNumero = this._pedidos().length + 1;
      const novo: Pedido = {
        ...dados,
        id: 'orc-' + Math.random().toString(36).slice(2, 8),
        numero: 'PED-' + String(proximoNumero).padStart(5, '0'),
        cliente: { id: dados.clienteId, nomeFantasia: dados.clienteNomeFantasia, cnpj: dados.clienteCnpj },
        empresaId: dados.empresaId,
        status: this.statusFicticios().find((s) => s.id === dados.statusId)?.chave ?? 'rascunho',
        sistemaOrigemId: null,
        criadoEm: new Date().toISOString(),
      };
      this._pedidos.update((lista) => [novo, ...lista]);
      return of(novo).pipe(delay(400));
    }
    return this.http.post<Pedido>(ENDPOINT, dados).pipe(tap((novo) => this._pedidos.update((lista) => [novo, ...lista])));
  }

  atualizar(id: string, dados: PedidoFormulario): Observable<Pedido> {
    if (environment.mockAuth) {
      const existente = this._pedidos().find((o) => o.id === id);
      const atualizado: Pedido = {
        ...dados,
        id,
        numero: existente?.numero ?? 'PED-00000',
        cliente: { id: dados.clienteId, nomeFantasia: dados.clienteNomeFantasia, cnpj: dados.clienteCnpj },
        empresaId: dados.empresaId,
        status: this.statusFicticios().find((s) => s.id === dados.statusId)?.chave ?? existente?.status ?? 'rascunho',
        sistemaOrigemId: existente?.sistemaOrigemId ?? null,
        criadoEm: existente?.criadoEm ?? new Date().toISOString(),
      };
      this._pedidos.update((lista) => lista.map((o) => (o.id === id ? atualizado : o)));
      return of(atualizado).pipe(delay(400));
    }
    return this.http.put<Pedido>(`${ENDPOINT}/${id}`, dados).pipe(
      tap((atualizado) => this._pedidos.update((lista) => lista.map((o) => (o.id === id ? atualizado : o)))),
    );
  }

  apagar(id: string): Observable<void> {
    if (environment.mockAuth) {
      this._pedidos.update((lista) => lista.filter((o) => o.id !== id));
      return of(undefined).pipe(delay(300));
    }
    return this.http.delete<void>(`${ENDPOINT}/${id}`).pipe(tap(() => this._pedidos.update((lista) => lista.filter((o) => o.id !== id))));
  }

  private statusFicticios(): PedidoStatusCatalogo[] {
    return [
      { id: 'sts-001', chave: 'rascunho' },
      { id: 'sts-002', chave: 'enviado' },
      { id: 'sts-003', chave: 'aprovado' },
      { id: 'sts-004', chave: 'recusado' },
    ];
  }

  private dadosFicticios(): Pedido[] {
    return [
      {
        id: 'ped-001',
        numero: 'PED-00001',
        dataPedido: '2026-04-02',
        clienteId: 'cli-001',
        cliente: { id: 'cli-1', nomeFantasia: 'Saúde Total', cnpj: '12.345.678/0001-90' },
        empresaId: 'emp-001',
        vendedorId: 'usr-002',
        sistemaOrigemId: null,
        itens: [
          { produtoId: 'prd-001', produtoCodigo: 'MED-0012', produtoDescricao: 'Luva de Procedimento Látex P (cx c/100)', quantidade: 20, precoUnitario: 32.9 },
          { produtoId: 'prd-003', produtoCodigo: 'MED-0103', produtoDescricao: 'Álcool Etílico 70% 1L', quantidade: 50, precoUnitario: 9.4 },
        ],
        status: 'enviado',
        statusId: 'sts-002',
        observacoes: 'Entrega prevista para a próxima semana.',
        criadoEm: '2026-04-02T13:20:00Z',
      },
      {
        id: 'ped-002',
        numero: 'PED-00002',
        dataPedido: '2026-05-14',
        clienteId: 'cli-002',
        cliente: { id: 'cli-2', nomeFantasia: 'Vida Plena', cnpj: '23.456.789/0001-11' },
        empresaId: 'emp-001',
        vendedorId: null,
        sistemaOrigemId: 'ext-000234',
        itens: [
          { produtoId: 'prd-002', produtoCodigo: 'MED-0045', produtoDescricao: 'Seringa Descartável 5ml c/ Agulha', quantidade: 3000, precoUnitario: 0.85 },
        ],
        status: 'aprovado',
        statusId: 'sts-003',
        observacoes: '',
        criadoEm: '2026-05-14T09:50:00Z',
      },
    ];
  }
}
