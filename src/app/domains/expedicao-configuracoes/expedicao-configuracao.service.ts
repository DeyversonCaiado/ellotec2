import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  ExpedicaoConfiguracao,
  ExpedicaoConfiguracaoPayload,
} from './expedicao-configuracao.model';

const ENDPOINT = `${environment.apiUrl}/expedicao-configuracoes`;

/**
 * Sem o branch `if (environment.mockAuth)` dos services de cadastro: um mock em
 * memória de configuração daria a impressão de que o parâmetro foi salvo
 * enquanto o galpão inteiro continua rodando com o valor antigo. Backend fora
 * do ar, a tela mostra erro — que é a informação correta.
 *
 * Não há `id` nas URLs porque a configuração é uma só.
 */
@Injectable({ providedIn: 'root' })
export class ExpedicaoConfiguracaoService {
  private http = inject(HttpClient);

  obter(): Observable<ExpedicaoConfiguracao> {
    return this.http.get<ExpedicaoConfiguracao>(ENDPOINT);
  }

  salvar(dados: ExpedicaoConfiguracaoPayload): Observable<ExpedicaoConfiguracao> {
    return this.http.put<ExpedicaoConfiguracao>(ENDPOINT, dados);
  }
}
