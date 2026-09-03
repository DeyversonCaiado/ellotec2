import { Component, computed, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../shared/ui/icon.component';
import { FinalizacaoSistemaOrigem } from './expedicao.model';

/**
 * Os quatro números de embarque que o ERP pede para fechar o pedido: volumes,
 * espécie da embalagem, peso líquido e peso bruto.
 *
 * Abre quando a conferência termina, e não antes: só depois de embalar é que
 * alguém sabe o peso bruto. Mora aqui no domínio, ao lado de
 * senha-gerente.component.ts, pelo mesmo motivo dele — duas telas da expedição
 * precisam, e nenhuma outra parte do sistema precisa.
 *
 * A tela é do coletor (320×453): um campo por linha, alvo de toque grande,
 * teclado numérico em três dos quatro campos. O componente só COLETA — quem
 * valida e quem fala com o ERP é o backend, sempre.
 *
 * Os três campos numéricos são input type="number", o que já impede o operador
 * de digitar letra. A conversão para o formato que o ERP guarda acontece do
 * lado de lá: VOLUME_PEDIDO é VARCHAR2(10) e recebe texto de dígitos, montado
 * em _volume_para_o_erp no backend — nunca um número deixado para o Oracle
 * converter, que usaria o separador decimal do NLS da sessão e gravaria 4,0.
 */
@Component({
  selector: 'app-finalizar-pedido',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  template: `
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
      <div
        class="w-full max-w-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 my-auto"
      >
        <div class="flex items-start gap-3 mb-4">
          <div
            class="size-9 shrink-0 rounded-full bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 flex items-center justify-center"
          >
            <app-icon name="check" class="size-4" />
          </div>
          <div>
            <h2 class="font-semibold text-gray-800 dark:text-gray-100">Finalizar pedido</h2>
            <p class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              Informe os dados de embarque para fechar o pedido
              {{ pedidoNumero() }} no sistema de origem.
            </p>
          </div>
        </div>

        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5"
          >Volumes</label
        >
        <!-- Contagem de volumes: inteiro, sempre. Os 247 mil pedidos com
             VOLUME_PEDIDO preenchido no ERP são todos de dígitos, nenhum com
             fração. O step=1 mantém as setas do campo andando de um em um, e o
             Math.trunc na saída derruba a fração se ela aparecer de outra forma
             (colar, ou a seta num campo já fracionado). -->
        <input
          type="number"
          inputmode="numeric"
          min="1"
          step="1"
          [ngModel]="volume()"
          (ngModelChange)="volume.set($event)"
          class="py-3 px-3.5 block w-full border border-gray-300 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 rounded-lg text-base focus:border-brand-500 focus:ring-brand-500"
        />
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
          Quantidade de volumes — número inteiro.
        </p>

        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5 mt-3"
          >Espécie</label
        >
        <!-- Digitado, não selecionado: a lista de espécies do ERP não é fechada
             e um select desatualizado travaria o embarque. Hoje o ERP tem CX,
             CAIXA e CAIXAS gravados, o que já não cabia em 2 caracteres. Os 10
             (tamanho de ESPECIE_PEDIDO) e a maiúscula são garantidos aqui e de
             novo no backend. -->
        <input
          type="text"
          maxlength="10"
          autocapitalize="characters"
          autocomplete="off"
          placeholder="CX"
          [ngModel]="especie()"
          (ngModelChange)="aoDigitarEspecie($event)"
          class="py-3 px-3.5 block w-full uppercase border border-gray-300 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 rounded-lg text-base focus:border-brand-500 focus:ring-brand-500"
        />
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
          Tipo da embalagem, com até 10 caracteres — CX, CAIXA, FD, SC.
        </p>

        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5 mt-3"
          >Peso líquido (kg)</label
        >
        <input
          type="number"
          inputmode="decimal"
          min="0"
          step="0.001"
          [ngModel]="pesoLiquido()"
          (ngModelChange)="pesoLiquido.set($event)"
          class="py-3 px-3.5 block w-full border border-gray-300 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 rounded-lg text-base focus:border-brand-500 focus:ring-brand-500"
        />

        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1.5 mt-3"
          >Peso bruto (kg)</label
        >
        <input
          type="number"
          inputmode="decimal"
          min="0"
          step="0.001"
          [ngModel]="pesoBruto()"
          (ngModelChange)="pesoBruto.set($event)"
          (keyup.enter)="confirmar()"
          class="py-3 px-3.5 block w-full border border-gray-300 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 rounded-lg text-base focus:border-brand-500 focus:ring-brand-500"
        />

        @if (erro()) {
          <p class="text-sm text-red-600 mt-3">{{ erro() }}</p>
        }

        <div class="flex items-center gap-2 mt-5">
          <button
            type="button"
            (click)="cancelar.emit()"
            [disabled]="ocupado()"
            class="flex-1 text-sm font-semibold border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 rounded-lg px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
          >
            Agora não
          </button>
          <button
            type="button"
            (click)="confirmar()"
            [disabled]="!preenchido() || ocupado()"
            class="flex-1 text-sm font-semibold bg-brand-600 text-white rounded-lg px-4 py-3 hover:bg-brand-700 disabled:opacity-40"
          >
            {{ ocupado() ? 'Finalizando…' : 'Finalizar pedido' }}
          </button>
        </div>

        <p class="text-xs text-gray-500 dark:text-gray-400 mt-3">
          A conferência já está registrada. Se algo der errado agora, nada do que
          foi bipado se perde — dá para tentar de novo pela tela do pedido.
        </p>
      </div>
    </div>
  `,
})
export class FinalizarPedidoComponent {
  pedidoNumero = input('');
  erro = input<string | null>(null);
  ocupado = input(false);

  confirmado = output<FinalizacaoSistemaOrigem>();
  cancelar = output<void>();

  // `null` e não 0 como inicial: com 0 o campo já nasce preenchido com um valor
  // que o backend recusa, e o operador teria que apagar antes de digitar.
  //
  // Nulo é também o que um campo `type="number"` entrega quando o conteúdo não
  // é número válido para o navegador — daí o `preenchido()` abaixo tratar nulo
  // como "não pode enviar", nunca como zero.
  volume = signal<number | null>(null);
  especie = signal('');
  pesoLiquido = signal<number | null>(null);
  pesoBruto = signal<number | null>(null);

  /** A mesma exigência do backend, repetida aqui só para o botão não oferecer
   *  o que vai voltar como 422. A barreira continua sendo o backend. */
  preenchido = computed(
    () =>
      (this.volume() ?? 0) >= 1 &&
      this.especie().trim().length > 0 &&
      (this.pesoLiquido() ?? 0) > 0 &&
      (this.pesoBruto() ?? 0) > 0,
  );

  /** 10 é o tamanho de `ESPECIE_PEDIDO` no ERP (`VARCHAR2(10)`). O `slice`
   *  existe além do `maxlength` do input porque colar texto no coletor passa
   *  por caminhos que o atributo não cobre em todo navegador. */
  aoDigitarEspecie(valor: string): void {
    this.especie.set((valor ?? '').toUpperCase().slice(0, 10));
  }

  confirmar(): void {
    if (!this.preenchido() || this.ocupado()) return;
    this.confirmado.emit({
      // Volumes é contagem — fração não existe aqui. O backend é que converte
      // para o texto de dígitos que o ERP guarda.
      volume: Math.trunc(this.volume()!),
      especie: this.especie().trim().toUpperCase(),
      pesoLiquido: this.pesoLiquido()!,
      pesoBruto: this.pesoBruto()!,
    });
  }
}
