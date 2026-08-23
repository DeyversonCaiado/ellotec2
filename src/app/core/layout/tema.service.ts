import { Injectable, signal, effect } from '@angular/core';

export type Tema = 'claro' | 'escuro';

const STORAGE_KEY ='ellotec_erp_tema';

/**
 * Controla o tema claro/escuro da aplicação. A classe 'dark' é aplicada
 * no <html> (padrão darkMode: 'class' do Tailwind), e a preferência fica
 * salva em localStorage. Sem dor nenhuma em trocar isso por preferência
 * do sistema operacional no futuro — hoje a única necessidade é o toggle
 * manual no topbar.
 */
@Injectable({ providedIn: 'root' })
export class TemaService {
  private readonly _tema = signal<Tema>(this.lerTemaPersistido());
  readonly tema = this._tema.asReadonly();

  constructor() {
    effect(() => {
      const ehEscuro = this._tema() === 'escuro';
      document.documentElement.classList.toggle('dark', ehEscuro);
      localStorage.setItem(STORAGE_KEY, this._tema());
    });
  }

  alternar(): void {
    this._tema.update((atual) => (atual === 'claro' ? 'escuro' : 'claro'));
  }

  private lerTemaPersistido(): Tema {
    const salvo = localStorage.getItem(STORAGE_KEY);
    if (salvo === 'claro' || salvo === 'escuro') return salvo;
    const prefereEscuro = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
    return prefereEscuro ? 'escuro' : 'claro';
  }
}
