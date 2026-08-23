import { Component, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../shared/ui/icon.component';
import { CredencialGerente } from './expedicao.model';

/**
 * Override de gerente: usado tanto para resetar um processo quanto para
 * finalizar um item com quantidade abaixo da pedida. Fica aqui, no domínio,
 * porque duas telas de expedição precisam dele e nenhuma outra parte do
 * sistema precisa — se um dia outro domínio precisar, aí sim vai pra
 * `shared/ui/`.
 *
 * O componente só coleta a credencial. Quem valida é o backend, sempre.
 */
@Component({
  selector: 'app-senha-gerente',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  template: `
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div class="w-full max-w-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <div class="flex items-start gap-3 mb-4">
          <div class="size-9 shrink-0 rounded-full bg-amber-50 dark:bg-amber-900/30 text-amber-600 flex items-center justify-center">
            <app-icon name="lock" class="size-4" />
          </div>
          <div>
            <h2 class="font-semibold text-gray-800 dark:text-gray-100">{{ titulo() }}</h2>
            <p class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{{ descricao() }}</p>
          </div>
        </div>

        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5">Usuário do gerente</label>
        <input
          type="text"
          autocomplete="off"
          [ngModel]="usuario()"
          (ngModelChange)="usuario.set($event)"
          class="py-3 px-3.5 block w-full border border-gray-300 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 rounded-lg text-base focus:border-brand-500 focus:ring-brand-500"
        />

        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5 mt-3">Senha</label>
        <input
          type="password"
          autocomplete="off"
          [ngModel]="senha()"
          (ngModelChange)="senha.set($event)"
          (keyup.enter)="confirmar()"
          class="py-3 px-3.5 block w-full border border-gray-300 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 rounded-lg text-base focus:border-brand-500 focus:ring-brand-500"
        />

        @if (erro()) {
          <p class="text-sm text-red-600 mt-2">{{ erro() }}</p>
        }

        <div class="flex items-center gap-2 mt-5">
          <button
            type="button"
            (click)="cancelar.emit()"
            class="flex-1 text-sm font-semibold border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 rounded-lg px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Cancelar
          </button>
          <button
            type="button"
            (click)="confirmar()"
            [disabled]="!usuario().trim() || !senha() || ocupado()"
            class="flex-1 text-sm font-semibold bg-brand-600 text-white rounded-lg px-4 py-3 hover:bg-brand-700 disabled:opacity-40"
          >
            {{ rotuloConfirmar() }}
          </button>
        </div>
      </div>
    </div>
  `,
})
export class SenhaGerenteComponent {
  titulo = input('Autorização de gerente');
  descricao = input('Esta ação precisa da senha de um usuário com cargo Gerente.');
  rotuloConfirmar = input('Confirmar');
  erro = input<string | null>(null);
  ocupado = input(false);

  confirmado = output<CredencialGerente>();
  cancelar = output<void>();

  usuario = signal('');
  senha = signal('');

  confirmar(): void {
    if (!this.usuario().trim() || !this.senha()) return;
    this.confirmado.emit({ usuarioGerente: this.usuario().trim(), senha: this.senha() });
  }
}
