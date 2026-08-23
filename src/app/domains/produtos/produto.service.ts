import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, delay, map, of, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  Produto,
  ProdutoFormulario,
  ProdutoListaPaginada,
  VincularAnvisaResposta,
} from './produto.model';
import { MarcaService } from '../marcas/marca.service';

const ENDPOINT = `${environment.apiUrl}/produtos`;

@Injectable({ providedIn: 'root' })
export class ProdutoService {
  private readonly _produtos = signal<Produto[]>(this.dadosFicticios());
  readonly produtos = this._produtos.asReadonly();

  constructor(
    private http: HttpClient,
    private marcaService: MarcaService,
  ) {}

  listar(): Observable<Produto[]> {
    if (environment.mockAuth) {
      return of(this._produtos()).pipe(delay(400));
    }
    return this.http.get<ProdutoListaPaginada>(ENDPOINT).pipe(
      map((resposta) => resposta.items),
      tap((lista) => this._produtos.set(lista)),
    );
  }

  /** Busca uma página de produtos no backend, com filtro opcional por código/descrição. */
  listarPagina(page: number, perPage: number, q: string): Observable<ProdutoListaPaginada> {
    if (environment.mockAuth) {
      const termo = q.toLowerCase().trim();
      const filtrados = termo
        ? this._produtos().filter((p) => p.descricao.toLowerCase().includes(termo) || p.codigo.toLowerCase().includes(termo))
        : this._produtos();
      const inicio = (page - 1) * perPage;
      return of({
        items: filtrados.slice(inicio, inicio + perPage),
        total: filtrados.length,
        page,
        perPage,
        sort: 'descricao',
        sortType: 'asc',
      }).pipe(delay(400));
    }
    return this.http.get<ProdutoListaPaginada>(ENDPOINT, { params: { page, perPage, q: q.trim() } });
  }

  obterPorId(id: string): Observable<Produto | undefined> {
    if (environment.mockAuth) {
      return of(this._produtos().find((p) => p.id === id)).pipe(delay(300));
    }
    return this.http.get<Produto>(`${ENDPOINT}/${id}`);
  }

  /** Busca leve usada pelo domínio de pedidos pra localizar um produto por código/descrição. */
  buscar(termo: string): Observable<Produto[]> {
    return this.listarPagina(1, 15, termo).pipe(map((resposta) => resposta.items));
  }

  criar(dados: ProdutoFormulario): Observable<Produto> {
    if (environment.mockAuth) {
      const novo: Produto = {
        ...dados,
        id: 'prd-' + Math.random().toString(36).slice(2, 8),
        marcaNome: this.marcaService.marcas().find((m) => m.id === dados.marcaId)?.nome ?? '',
        criadoEm: new Date().toISOString(),
      };
      this._produtos.update((lista) => [novo, ...lista]);
      return of(novo).pipe(delay(400));
    }
    return this.http.post<Produto>(ENDPOINT, dados).pipe(tap((novo) => this._produtos.update((lista) => [novo, ...lista])));
  }

  atualizar(id: string, dados: ProdutoFormulario): Observable<Produto> {
    if (environment.mockAuth) {
      const existente = this._produtos().find((p) => p.id === id);
      const atualizado: Produto = {
        ...dados,
        id,
        marcaNome: this.marcaService.marcas().find((m) => m.id === dados.marcaId)?.nome ?? existente?.marcaNome ?? '',
        criadoEm: existente?.criadoEm ?? new Date().toISOString(),
      };
      this._produtos.update((lista) => lista.map((p) => (p.id === id ? atualizado : p)));
      return of(atualizado).pipe(delay(400));
    }
    return this.http.put<Produto>(`${ENDPOINT}/${id}`, dados).pipe(
      tap((atualizado) => this._produtos.update((lista) => lista.map((p) => (p.id === id ? atualizado : p)))),
    );
  }

  apagar(id: string): Observable<void> {
    if (environment.mockAuth) {
      this._produtos.update((lista) => lista.filter((p) => p.id !== id));
      return of(undefined).pipe(delay(300));
    }
    return this.http.delete<void>(`${ENDPOINT}/${id}`).pipe(tap(() => this._produtos.update((lista) => lista.filter((p) => p.id !== id))));
  }

  /**
   * Confere o código lido contra a tabela da CMED e, batendo com o registro
   * ANVISA do produto, vincula os EANs de lá como códigos de logística.
   *
   * Sem branch de mock: a operação é uma consulta a uma tabela de outro sistema
   * seguida de escrita condicionada: um mock em memória não reproduziria nem a
   * conferência nem a checagem de conflito, e daria a falsa impressão de que a
   * tela funciona.
   */
  vincularCodigosDaAnvisa(produtoId: string, codigoBarras: string): Observable<VincularAnvisaResposta> {
    return this.http.post<VincularAnvisaResposta>(
      `${ENDPOINT}/${produtoId}/codigos-barras/anvisa`,
      { codigoBarras },
    );
  }

  private dadosFicticios(): Produto[] {
    return [
      { id: 'prd-001', codigoBarraNotas: '7891234500012', codigosBarrasLogistica: ['7891234500012', '17891234500012'], dun14: '17891234500012', quantidadeMultiplaVenda: 100, registroAnvisa: '80149220015', codigo: 'MED-0012', descricao: 'Luva de Procedimento Látex P (cx c/100)', unidade: 'CX', marcaId: 'mrc-001', marcaNome: 'Descarpack', sistemaOrigemId: null, ativo: true, criadoEm: '2025-10-05T08:00:00Z' },
      { id: 'prd-002', codigoBarraNotas: '7891234500045', codigosBarrasLogistica: ['7891234500045'], dun14: '17891234500045', quantidadeMultiplaVenda: 1, registroAnvisa: '10033430289', codigo: 'MED-0045', descricao: 'Seringa Descartável 5ml c/ Agulha', unidade: 'UN', marcaId: 'mrc-002', marcaNome: 'BD', sistemaOrigemId: null, ativo: true, criadoEm: '2025-10-12T08:00:00Z' },
      { id: 'prd-003', codigoBarraNotas: '7891234501030', codigosBarrasLogistica: ['7891234501030'], dun14: '17891234501030', quantidadeMultiplaVenda: 1, registroAnvisa: null, codigo: 'MED-0103', descricao: 'Álcool Etílico 70% 1L', unidade: 'UN', marcaId: 'mrc-003', marcaNome: 'Cremer', sistemaOrigemId: null, ativo: true, criadoEm: '2025-11-20T08:00:00Z' },
      { id: 'prd-004', codigoBarraNotas: null, codigosBarrasLogistica: [], dun14: null, quantidadeMultiplaVenda: 1, registroAnvisa: '80102510036', codigo: 'MED-0210', descricao: 'Termômetro Digital Clínico', unidade: 'UN', marcaId: 'mrc-003', marcaNome: 'Cremer', sistemaOrigemId: null, ativo: false, criadoEm: '2026-01-08T08:00:00Z' },
    ];
  }
}
