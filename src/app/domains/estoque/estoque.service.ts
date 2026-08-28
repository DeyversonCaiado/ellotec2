import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { LoteListaPaginada, SaldoListaPaginada } from './estoque.model';

const ENDPOINT = `${environment.apiUrl}/estoque`;

@Injectable({ providedIn: 'root' })
export class EstoqueService {
  private http = inject(HttpClient);

  /** Saldo total por produto. O filtro por empresa vai à API e recorta a base
   *  inteira — nunca a página já carregada. */
  listarSaldos(
    page: number,
    perPage: number,
    empresaId: string,
  ): Observable<SaldoListaPaginada> {
    const params: Record<string, string | number> = { page, perPage };
    if (empresaId) params['empresaId'] = empresaId;
    return this.http.get<SaldoListaPaginada>(`${ENDPOINT}/saldos`, { params });
  }

  /** Saldo aberto por lote, ordenado por vencimento (o mais próximo primeiro)
   *  — é a ordem em que o galpão precisa ver a mercadoria. */
  listarLotes(page: number, perPage: number, empresaId: string): Observable<LoteListaPaginada> {
    const params: Record<string, string | number> = { page, perPage };
    if (empresaId) params['empresaId'] = empresaId;
    return this.http.get<LoteListaPaginada>(`${ENDPOINT}/lotes`, { params });
  }
}
