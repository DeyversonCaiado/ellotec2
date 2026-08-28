import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  EnderecoEstoque,
  EnderecoFormulario,
  EnderecoListaPaginada,
  VinculoListaPaginada,
} from './enderecamento.model';

const ENDPOINT = `${environment.apiUrl}/enderecamento`;

@Injectable({ providedIn: 'root' })
export class EnderecamentoService {
  private http = inject(HttpClient);

  /** Busca e filtro por empresa resolvem NO SERVIDOR, sobre a base inteira —
   *  nunca sobre a página já carregada. */
  listarPagina(
    page: number,
    perPage: number,
    q: string,
    empresaId: string,
  ): Observable<EnderecoListaPaginada> {
    const params: Record<string, string | number> = { page, perPage };
    if (q.trim()) params['q'] = q.trim();
    if (empresaId) params['empresaId'] = empresaId;
    return this.http.get<EnderecoListaPaginada>(`${ENDPOINT}/enderecos`, { params });
  }

  obterPorId(id: string): Observable<EnderecoEstoque> {
    return this.http.get<EnderecoEstoque>(`${ENDPOINT}/enderecos/${id}`);
  }

  criar(dados: EnderecoFormulario): Observable<EnderecoEstoque> {
    return this.http.post<EnderecoEstoque>(`${ENDPOINT}/enderecos`, dados);
  }

  atualizar(id: string, dados: EnderecoFormulario): Observable<EnderecoEstoque> {
    return this.http.put<EnderecoEstoque>(`${ENDPOINT}/enderecos/${id}`, dados);
  }

  apagar(id: string): Observable<void> {
    return this.http.delete<void>(`${ENDPOINT}/enderecos/${id}`);
  }

  /** A consulta "onde está este produto".
   *
   *  O mesmo `q` casa com endereço, lote, código do produto, descrição e
   *  qualquer código de barras dele — quem decide isso é o backend, que
   *  pergunta aos domínios donos de cada coisa. A tela manda o texto e pronto:
   *  reimplementar aqui qual campo casa com o quê seria duplicar regra. */
  listarVinculos(
    page: number,
    perPage: number,
    q: string,
    empresaId: string,
  ): Observable<VinculoListaPaginada> {
    const params: Record<string, string | number> = { page, perPage };
    if (q.trim()) params['q'] = q.trim();
    if (empresaId) params['empresaId'] = empresaId;
    return this.http.get<VinculoListaPaginada>(`${ENDPOINT}/vinculos`, { params });
  }

  /** Os lotes guardados num endereço específico — usado ao abrir um endereço
   *  da aba de cadastro. */
  listarVinculosDoEndereco(
    estoqueEnderecosId: string,
    page: number,
    perPage: number,
  ): Observable<VinculoListaPaginada> {
    return this.http.get<VinculoListaPaginada>(`${ENDPOINT}/vinculos`, {
      params: { page, perPage, estoqueEnderecosId },
    });
  }
}
