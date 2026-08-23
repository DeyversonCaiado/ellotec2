import { Injectable } from '@angular/core';

const STORAGE_DEVICE_ID_KEY = 'ellotec_erp_device_id';

/**
 * Gera um UUID único para este navegador/dispositivo na primeira vez que é
 * chamado, e persiste em localStorage para reusar em todas as sessões
 * subsequentes. É a âncora estável que o backend usa para identificar o
 * dispositivo — não muda com atualização de browser, troca de rede ou
 * nova aba, só se o usuário limpar os dados do navegador.
 *
 * Enviado em todo request via authInterceptor no header X-Device-Id.
 * Sem ele, o backend retorna 400 no login e 401 nos endpoints autenticados.
 */
@Injectable({ providedIn: 'root' })
export class DispositivoService {
  private readonly _deviceId: string;

  constructor() {
    const salvo = localStorage.getItem(STORAGE_DEVICE_ID_KEY);
    if (salvo) {
      this._deviceId = salvo;
    } else {
      const novo = this.gerarUUID();
      localStorage.setItem(STORAGE_DEVICE_ID_KEY, novo);
      this._deviceId = novo;
    }
  }

  get deviceId(): string {
    return this._deviceId;
  }

  private gerarUUID(): string {
    // crypto.randomUUID() disponível em browsers modernos e em localhost
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
    // Fallback para ambientes sem crypto.randomUUID
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }
}
