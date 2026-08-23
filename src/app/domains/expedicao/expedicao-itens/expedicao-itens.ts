import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { ExpedicaoService } from '../expedicao.service';
import { ItemProcesso, Processo, TipoProcesso, itemEmAndamento, rotuloTipo } from '../expedicao.model';
import { IconComponent } from '../../../shared/ui/icon.component';

/**
 * Tela do coletor (800×480): só o número do pedido e a lista de produtos, com
 * um botão por linha. Enquanto um item estiver em andamento, os botões dos
 * outros ficam desabilitados — a mesma regra que o backend aplica, aqui só
 * para o operador não descobrir por erro.
 */
@Component({
  selector: 'app-expedicao-itens',
  standalone: true,
  imports: [CommonModule, RouterLink, IconComponent],
  templateUrl: './expedicao-itens.html',
})
export class ExpedicaoItens implements OnInit {
  private service = inject(ExpedicaoService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  processo = signal<Processo | null>(null);
  carregando = signal(true);
  erro = signal<string | null>(null);
  abrindoItem = signal<string | null>(null);

  pedidoId = '';
  tipo: TipoProcesso = 'separacao';
  processoId = '';

  readonly rotuloTipo = rotuloTipo;

  emAndamento = computed(() => itemEmAndamento(this.processo()));
  finalizados = computed(
    () => this.processo()?.itens.filter((item) => item.situacao === 'finalizado').length ?? 0,
  );

  ngOnInit(): void {
    const params = this.route.snapshot.paramMap;
    this.pedidoId = params.get('pedidoId') ?? '';
    this.tipo = (params.get('tipo') as TipoProcesso) ?? 'separacao';
    this.processoId = params.get('processoId') ?? '';

    this.service.obterProcesso(this.tipo, this.processoId).subscribe({
      next: (processo) => {
        this.processo.set(processo);
        this.carregando.set(false);
      },
      error: (resposta: HttpErrorResponse) => {
        this.erro.set(resposta.error?.detail ?? 'Não foi possível carregar os itens.');
        this.carregando.set(false);
      },
    });
  }

  /** Item já iniciado só navega; item pendente é iniciado no backend antes
   *  (é o `data_inicio` que começa a medir o tempo gasto nele). */
  abrirItem(item: ItemProcesso): void {
    if (item.situacao === 'finalizado' || this.bloqueado(item)) return;

    if (item.situacao === 'em_andamento') {
      this.navegarParaItem(item);
      return;
    }

    this.abrindoItem.set(item.pedidoItemId);
    this.erro.set(null);
    this.service.iniciarItem(this.tipo, this.processoId, item.pedidoItemId).subscribe({
      next: (processo) => {
        this.abrindoItem.set(null);
        this.processo.set(processo);
        this.navegarParaItem(item);
      },
      error: (resposta: HttpErrorResponse) => {
        this.abrindoItem.set(null);
        this.erro.set(resposta.error?.detail ?? 'Não foi possível iniciar este item.');
      },
    });
  }

  private navegarParaItem(item: ItemProcesso): void {
    this.router.navigate([
      '/expedicao',
      this.pedidoId,
      this.tipo,
      this.processoId,
      'itens',
      item.pedidoItemId,
    ]);
  }

  bloqueado(item: ItemProcesso): boolean {
    const atual = this.emAndamento();
    return !!atual && atual.pedidoItemId !== item.pedidoItemId && item.situacao !== 'finalizado';
  }

  corItem(item: ItemProcesso): string {
    if (item.situacao === 'finalizado') {
      return item.divergente
        ? 'border-amber-300 bg-amber-50 dark:bg-amber-900/20'
        : 'border-emerald-300 bg-emerald-50 dark:bg-emerald-900/20';
    }
    if (item.situacao === 'em_andamento') return 'border-brand-400 bg-brand-50 dark:bg-brand-900/20';
    return 'border-gray-200 dark:border-gray-800';
  }
}
