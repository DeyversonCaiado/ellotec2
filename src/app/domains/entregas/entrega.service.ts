import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  CAMPOS_FILTRO,
  EntregaListaPaginada,
  EntregaNota,
  FiltrosEntrega,
  InteracaoFormulario,
  SugestoesFiltro,
} from './entrega.model';

const ENDPOINT = `${environment.apiUrl}/entregas`;

/**
 * Sem branch de `mockAuth` e sem dados fictícios: entrega não se digita, chega
 * pela integração. Inventar notas em memória daria a impressão de que a tela
 * funciona sem o ERP alimentando a API.
 *
 * As três rotas de interação devolvem a NOTA INTEIRA, não só a interação —
 * registrar um evento muda o `statusAtual` e o `statusPrazo` da nota, e a tela
 * precisa dos dois atualizados sem fazer um segundo request.
 */
@Injectable({ providedIn: 'root' })
export class EntregaService {
  constructor(private http: HttpClient) {}

  listarPagina(
    page: number,
    perPage: number,
    filtros: FiltrosEntrega,
  ): Observable<EntregaListaPaginada> {
    // Só o que está preenchido vira query param: mandar `status=''` faria o
    // backend filtrar por status vazio e devolver lista vazia.
    let params = new HttpParams().set('page', page).set('perPage', perPage);
    if (filtros.q.trim()) params = params.set('q', filtros.q.trim());
    if (filtros.statusPrazo) params = params.set('statusPrazo', filtros.statusPrazo);
    if (filtros.dataInicio) params = params.set('dataInicio', filtros.dataInicio);
    if (filtros.dataFim) params = params.set('dataFim', filtros.dataFim);

    // Cada valor escolhido vira uma repetição do mesmo parâmetro
    // (`?uf=GO&uf=DF`) — `append`, não `set`. É a forma padrão de lista em
    // query string, e é o que o FastAPI lê como `list[str]`.
    for (const campo of CAMPOS_FILTRO) {
      for (const valor of filtros[campo.chave]) {
        params = params.append(campo.chave, String(valor));
      }
    }

    return this.http.get<EntregaListaPaginada>(ENDPOINT, { params });
  }

  /** As sugestões de UM campo do painel, recortadas pelo que a pessoa digitou.
   *
   *  Um endpoint só para os 19 campos — `campo` diz qual. Antes a tela baixava
   *  todos os valores de todos os campos a cada troca de período: num mês real
   *  isso deu ~600 pedidos e centenas de números de nota numa resposta só.
   *
   *  Só o período vai junto: as sugestões NÃO consideram os filtros já
   *  escolhidos, de propósito. Se considerassem, escolher uma transportadora
   *  encolheria a lista de cidades e trocar de ideia exigiria limpar tudo. */
  buscarSugestoes(
    campo: string,
    termo: string,
    dataInicio: string,
    dataFim: string,
  ): Observable<SugestoesFiltro> {
    let params = new HttpParams().set('campo', campo);
    if (termo) params = params.set('termo', termo);
    if (dataInicio) params = params.set('dataInicio', dataInicio);
    if (dataFim) params = params.set('dataFim', dataFim);
    return this.http.get<SugestoesFiltro>(`${ENDPOINT}/opcoes-filtros`, { params });
  }

  obterPorId(id: string): Observable<EntregaNota> {
    return this.http.get<EntregaNota>(`${ENDPOINT}/${id}`);
  }

  registrarInteracao(notaId: string, dados: InteracaoFormulario): Observable<EntregaNota> {
    return this.http.post<EntregaNota>(`${ENDPOINT}/${notaId}/interacoes`, dados);
  }

  /** Corrigir o texto de uma interação é legítimo — quem lança digita errado.
   *  O backend registra quem editou e NÃO reordena a linha do tempo. */
  atualizarInteracao(
    notaId: string,
    interacaoId: string,
    dados: InteracaoFormulario,
  ): Observable<EntregaNota> {
    return this.http.put<EntregaNota>(
      `${ENDPOINT}/${notaId}/interacoes/${interacaoId}`,
      dados,
    );
  }

  apagarInteracao(notaId: string, interacaoId: string): Observable<EntregaNota> {
    return this.http.delete<EntregaNota>(`${ENDPOINT}/${notaId}/interacoes/${interacaoId}`);
  }
}
