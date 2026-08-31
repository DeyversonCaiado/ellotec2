import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { CotacaoFiltroOpcoes, CotacaoFiltros, CotacaoListaPaginada } from './cotacao.model';

const ENDPOINT = `${environment.apiUrl}/cotacoes`;

@Injectable({ providedIn: 'root' })
export class CotacaoService {
  private http = inject(HttpClient);

  /**
   * Uma página de itens de cotação.
   *
   * TODOS os filtros vão à API e recortam a base inteira — nunca a página já
   * carregada. Com centenas de milhares de itens no período, filtrar depois de
   * paginar responderia "não achei" para um item que existe na página 7, e
   * mostraria um total que não bate com as linhas na tela.
   */
  listar(
    filtros: CotacaoFiltros,
    page: number,
    perPage: number,
    sort: string,
    sortType: string,
  ): Observable<CotacaoListaPaginada> {
    const params: Record<string, string | number> = { page, perPage, sort, sortType, ...this.filtrosComuns(filtros) };
    return this.http.get<CotacaoListaPaginada>(ENDPOINT, { params });
  }

  /**
   * Baixa TODAS as linhas do filtro em CSV, sem paginação.
   *
   * O backend responde em streaming e nunca monta o arquivo na memória dele.
   * Aqui chega como blob porque a chamada precisa do token no header — um
   * link direto não carregaria o `Authorization` que o interceptor injeta.
   */
  exportar(filtros: CotacaoFiltros, sort: string, sortType: string): Observable<Blob> {
    const params: Record<string, string | number> = { sort, sortType, ...this.filtrosComuns(filtros) };
    return this.http.get(`${ENDPOINT}/exportar`, { params, responseType: 'blob' });
  }

  /** Os filtros que listagem e exportação mandam igual — é o que garante que o
   *  CSV traz exatamente o que está na tela. */
  private filtrosComuns(filtros: CotacaoFiltros): Record<string, string | number> {
    const params: Record<string, string | number> = {};
    // Com o número da cotação, o período não vai: o backend o ignoraria de
    // qualquer forma, e mandá-lo só confundiria quem lê a chamada na rede.
    if (filtros.cotacao) {
      params['cotacao'] = filtros.cotacao;
    } else {
      params['dataInicio'] = filtros.dataInicio;
      params['dataFim'] = filtros.dataFim;
    }
    if (filtros.q) params['q'] = filtros.q;
    if (filtros.hospital) params['hospital'] = filtros.hospital;
    if (filtros.cidade) params['cidade'] = filtros.cidade;
    if (filtros.estado) params['estado'] = filtros.estado;
    if (filtros.empresaId) params['empresaId'] = filtros.empresaId;
    if (filtros.situacao !== 'todas') params['situacao'] = filtros.situacao;
    return params;
  }

  /** Estados e empresas para os selects. Vêm de consulta própria, não da
   *  página carregada — senão o select ofereceria só o que apareceu nela. */
  opcoesDeFiltro(): Observable<CotacaoFiltroOpcoes> {
    return this.http.get<CotacaoFiltroOpcoes>(`${ENDPOINT}/opcoes-filtro`);
  }
}
