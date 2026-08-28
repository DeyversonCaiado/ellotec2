import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  FiltrosNotaFiscal,
  NotaFiscal,
  NotaFiscalListaPaginada,
  NotaFiscalXml,
} from './nota-fiscal.model';

const ENDPOINT = `${environment.apiUrl}/notas-fiscais`;

/**
 * Sem branch de `mockAuth` e sem `dadosFicticios()`, ao contrário dos outros
 * services do projeto: nota fiscal não se digita, se recebe. Inventar notas em
 * memória daria a falsa impressão de que a tela funciona sem a integração — e
 * um documento fiscal falso é exatamente o tipo de dado que não deve existir
 * nem em desenvolvimento.
 *
 * Também não guarda signal de lista: a tela é sempre paginada e filtrada no
 * servidor, então um cache local só teria a última página vista.
 */
@Injectable({ providedIn: 'root' })
export class NotaFiscalService {
  constructor(private http: HttpClient) {}

  listarPagina(
    page: number,
    perPage: number,
    filtros: FiltrosNotaFiscal,
  ): Observable<NotaFiscalListaPaginada> {
    // Só os filtros preenchidos viram query param. Mandar `tipoOperacao=''`
    // faria o backend recusar com 422, porque lá o campo tem pattern fechado.
    const params: Record<string, string | number> = { page, perPage };
    if (filtros.q.trim()) params['q'] = filtros.q.trim();
    if (filtros.tipoOperacao) params['tipoOperacao'] = filtros.tipoOperacao;
    if (filtros.dataInicio) params['dataInicio'] = filtros.dataInicio;
    if (filtros.dataFim) params['dataFim'] = filtros.dataFim;

    return this.http.get<NotaFiscalListaPaginada>(ENDPOINT, { params });
  }

  obterPorId(id: string): Observable<NotaFiscal> {
    return this.http.get<NotaFiscal>(`${ENDPOINT}/${id}`);
  }

  /** Rota separada de propósito: o XML tem dezenas de KB e nenhuma tela exibe
   *  o conteúdo. Só quem vai baixar o arquivo pede por ele. */
  obterXml(id: string): Observable<NotaFiscalXml> {
    return this.http.get<NotaFiscalXml>(`${ENDPOINT}/${id}/xml`);
  }

  apagar(id: string): Observable<void> {
    return this.http.delete<void>(`${ENDPOINT}/${id}`);
  }
}
