import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  CredencialGerente,
  FiltrosPedidoExpedicao,
  Operador,
  PedidoExpedicaoDetalhe,
  PedidoExpedicaoListaPaginada,
  Processo,
  TipoProcesso,
} from './expedicao.model';

const ENDPOINT = `${environment.apiUrl}/expedicao`;

/**
 * Diferente dos outros services do projeto, este não tem o branch
 * `if (environment.mockAuth)`: separação e conferência são uma máquina de
 * estados com trava de usuário, de item em andamento e de senha de gerente —
 * um mock em memória não reproduziria nada disso e só daria a falsa impressão
 * de que a tela funciona. Se o backend estiver fora, a tela mostra erro, que é
 * a informação correta.
 */
@Injectable({ providedIn: 'root' })
export class ExpedicaoService {
  private http = inject(HttpClient);

  /**
   * Página de pedidos. O período é pela data do pedido e o backend cai no mês
   * atual quando não vem nada — mesmo padrão de `listarPagina` em produtos.
   *
   * Todo filtro de `FiltrosPedidoExpedicao` viaja na query string e é resolvido
   * na consulta paginada. Empresa, operador e situação já foram aplicados no
   * cliente, sobre a página carregada: o resultado era um total que não batia
   * com as linhas da tela, e pedido que existia na página 7 não era encontrado.
   */
  listarPedidos(filtros: FiltrosPedidoExpedicao): Observable<PedidoExpedicaoListaPaginada> {
    // O filtro de status vira ?statusPedido=A&statusPedido=B — um array em
    // HttpParams já é serializado assim, e é o formato que o FastAPI lê como
    // `list[str]`. Lista vazia não vai na query: ausente = todos os status.
    let params = new HttpParams()
      .set('page', filtros.page)
      .set('perPage', filtros.perPage)
      .set('dataInicio', filtros.dataInicio)
      .set('dataFim', filtros.dataFim)
      .set('q', filtros.q.trim())
      .set('sort', filtros.sort)
      .set('sortType', filtros.sortType);
    for (const chave of filtros.statusPedido) {
      params = params.append('statusPedido', chave);
    }
    // Vazio não vai na query: ausente é o que o backend lê como "sem filtro".
    // Mandar `empresaId=` faria ele procurar uma empresa de id vazio.
    if (filtros.empresaId) params = params.set('empresaId', filtros.empresaId);
    if (filtros.operadorId) params = params.set('operadorId', filtros.operadorId);
    if (filtros.situacao !== 'todos') params = params.set('situacao', filtros.situacao);

    return this.http.get<PedidoExpedicaoListaPaginada>(`${ENDPOINT}/pedidos`, { params });
  }

  /** Chaves de status do ERP para o filtro da listagem.
   *
   *  Vem da expedição e não de `GET /pedidos/status` porque aquele endpoint
   *  exige `pedidos.acessar`, que o operador de galpão não tem — o 403 fazia
   *  o interceptor derrubar a tela inteira de volta para o início. */
  listarStatusPedido(): Observable<string[]> {
    return this.http.get<string[]>(`${ENDPOINT}/status-pedido`);
  }

  /** Quem pode ser responsável por essa etapa. Sai do backend já filtrado por
   *  permissão: não se atribui separação a quem não pode separar. */
  listarOperadores(tipo: TipoProcesso): Observable<Operador[]> {
    return this.http.get<Operador[]>(`${ENDPOINT}/operadores/${tipo}`);
  }

  /** Quem pode executar qualquer etapa — a lista do FILTRO por operador.
   *
   *  Diferente de `listarOperadores`, que recebe uma etapa: o filtro pergunta
   *  "onde esta pessoa está envolvida?" e a resposta pode ser qualquer uma das
   *  duas. E diferente da lista que a tela montava sozinha a partir da página
   *  carregada, que escondia justamente quem ainda não pegou nenhum pedido. */
  listarOperadoresDoFiltro(): Observable<Operador[]> {
    return this.http.get<Operador[]>(`${ENDPOINT}/operadores`);
  }

  /** Empresas do cadastro (matriz e filiais) para o filtro da listagem.
   *
   *  Vem da expedição e não de `GET /empresas` pelo mesmo motivo do catálogo de
   *  status acima: aquele endpoint exige `empresas.acessar`, chave que o
   *  operador de galpão não tem. */
  listarEmpresas(): Observable<{ id: string; nome: string }[]> {
    return this.http.get<{ id: string; nome: string }[]>(`${ENDPOINT}/empresas`);
  }

  /** Define o responsável por uma etapa em vários pedidos de uma vez.
   *  `usuarioId: null` remove — "sem responsável" é um valor do campo, não uma
   *  operação separada (mesmo endpoint, mesma permissão). */
  atribuir(pedidoIds: string[], tipo: TipoProcesso, usuarioId: string | null): Observable<void> {
    return this.http.post<void>(`${ENDPOINT}/atribuicoes`, { pedidoIds, tipo, usuarioId });
  }

  obterPedido(pedidoId: string): Observable<PedidoExpedicaoDetalhe> {
    return this.http.get<PedidoExpedicaoDetalhe>(`${ENDPOINT}/pedidos/${pedidoId}`);
  }

  obterProcesso(tipo: TipoProcesso, processoId: string): Observable<Processo> {
    return this.http.get<Processo>(`${ENDPOINT}/${tipo}/${processoId}`);
  }

  /** Inicia ou continua — o backend devolve o processo em andamento se já existir. */
  iniciarProcesso(tipo: TipoProcesso, pedidoId: string): Observable<Processo> {
    return this.http.post<Processo>(`${ENDPOINT}/${tipo}/pedidos/${pedidoId}/iniciar`, {});
  }

  /** Abre a etapa NO NOME do operador atribuído, com todos os itens iniciados.
   *
   *  Pelo pedido e não pelo id do processo: quem clica está na tela do pedido e
   *  ainda não existe processo nenhum. Sem body — o operador não vai no payload,
   *  sai da atribuição viva no backend, que é a fonte da verdade de quem é o
   *  responsável (deixar a tela escolher criaria um segundo jeito de atribuir). */
  iniciarDelegado(tipo: TipoProcesso, pedidoId: string): Observable<Processo> {
    return this.http.post<Processo>(
      `${ENDPOINT}/${tipo}/pedidos/${pedidoId}/iniciar-delegado`,
      {},
    );
  }

  /** Fecha a etapa inteira no nome do operador, completando os itens abertos
   *  com a quantidade pedida. Sem senha de gerente: quem está logado JÁ é o
   *  gerente, e a permissão `expedicao.delegar` foi checada no endpoint. */
  finalizarDelegado(tipo: TipoProcesso, pedidoId: string): Observable<Processo> {
    return this.http.post<Processo>(
      `${ENDPOINT}/${tipo}/pedidos/${pedidoId}/finalizar-delegado`,
      {},
    );
  }

  iniciarItem(tipo: TipoProcesso, processoId: string, pedidoItemId: string): Observable<Processo> {
    return this.http.post<Processo>(
      `${ENDPOINT}/${tipo}/${processoId}/itens/${pedidoItemId}/iniciar`,
      {},
    );
  }

  bipar(
    tipo: TipoProcesso,
    processoId: string,
    pedidoItemId: string,
    codigoBarras: string,
    multiplicador: number,
  ): Observable<Processo> {
    return this.http.post<Processo>(
      `${ENDPOINT}/${tipo}/${processoId}/itens/${pedidoItemId}/bipar`,
      { codigoBarras, multiplicador },
    );
  }

  /** `credencial` só é necessária quando a quantidade está abaixo da pedida —
   *  o backend recusa com 401 se faltar. */
  finalizarItem(
    tipo: TipoProcesso,
    processoId: string,
    pedidoItemId: string,
    credencial?: CredencialGerente,
  ): Observable<Processo> {
    return this.http.post<Processo>(
      `${ENDPOINT}/${tipo}/${processoId}/itens/${pedidoItemId}/finalizar`,
      credencial ?? {},
    );
  }

  resetar(tipo: TipoProcesso, processoId: string, credencial: CredencialGerente): Observable<void> {
    return this.http.post<void>(`${ENDPOINT}/${tipo}/${processoId}/resetar`, credencial);
  }
}
