import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IconComponent } from '../../../shared/ui/icon.component';

/**
 * A tela do domínio Sistema de Origem — hoje, deliberadamente vazia.
 *
 * O domínio existe para reunir tudo que o ELLOTEC MANDA o ERP (GESTCOM) fazer.
 * A primeira função dele, finalizar o pedido depois da conferência, é usada de
 * dentro da expedição, no modal que abre quando a conferência termina — não
 * tem tela própria e não deveria ter, porque quem está na hora de finalizar é
 * o operador do galpão, no fluxo dele.
 *
 * Esta página existe para o domínio ter lugar no menu, rota e chave de
 * permissão desde o começo. As próximas funções do ERP entram aqui, e não
 * espalhadas por outros domínios.
 */
@Component({
  selector: 'app-sistema-origem-page',
  standalone: true,
  imports: [CommonModule, IconComponent],
  templateUrl: './sistema-origem-page.html',
})
export class SistemaOrigemPage {}
