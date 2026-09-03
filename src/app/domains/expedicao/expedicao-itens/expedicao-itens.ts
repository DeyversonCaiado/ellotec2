import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { ExpedicaoService } from '../expedicao.service';
import {
  FinalizacaoSistemaOrigem,
  ItemProcesso,
  Processo,
  TipoProcesso,
  itemEmAndamento,
  rotuloTipo,
} from '../expedicao.model';
import { FinalizarPedidoComponent } from '../finalizar-pedido.component';
import { IconComponent } from '../../../shared/ui/icon.component';
import { AuthService } from '../../../core/auth/auth.service';

/**
 * Tela do coletor (800×480): só o número do pedido e a lista de produtos, com
 * um botão por linha. Enquanto um item estiver em andamento, os botões dos
 * outros ficam desabilitados — a mesma regra que o backend aplica, aqui só
 * para o operador não descobrir por erro.
 */
@Component({
  selector: 'app-expedicao-itens',
  standalone: true,
  imports: [CommonModule, RouterLink, IconComponent, FinalizarPedidoComponent],
  templateUrl: './expedicao-itens.html',
})
export class ExpedicaoItens implements OnInit {
  private service = inject(ExpedicaoService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private auth = inject(AuthService);

  processo = signal<Processo | null>(null);
  carregando = signal(true);
  erro = signal<string | null>(null);
  abrindoItem = signal<string | null>(null);

  pedidoId = '';
  tipo: TipoProcesso = 'separacao';
  processoId = '';

  readonly rotuloTipo = rotuloTipo;

  emAndamento = computed(() => itemEmAndamento(this.processo()));

  // ---------------------------------------------------------------------
  // Finalizar o pedido no ERP
  //
  // A conferência fechar aqui não fecha o pedido lá: o ERP pede volumes,
  // espécie e os dois pesos, que só existem depois de a mercadoria estar
  // embalada. Por isso o modal abre sozinho quando a última leitura fecha a
  // conferência — é o momento em que o operador tem a caixa na mão — mas
  // continua sendo um passo que dá para adiar, porque a balança pode estar
  // ocupada e o trabalho já registrado não se perde.
  // ---------------------------------------------------------------------

  modalFinalizar = signal(false);
  finalizandoPedido = signal(false);
  erroFinalizar = signal<string | null>(null);

  podeFinalizarOrigem = computed(
    () => !!this.auth.usuario()?.permissoes.has('expedicao.finalizar_origem'),
  );

  /** Conferência fechada aqui e pedido ainda aberto no ERP. É o que decide
   *  tanto a abertura automática do modal quanto o botão do rodapé. */
  precisaFinalizarOrigem = computed(() => {
    const proc = this.processo();
    return (
      !!proc &&
      proc.tipo === 'conferencia' &&
      proc.status === 'finalizada' &&
      !proc.finalizadoOrigemEm &&
      this.podeFinalizarOrigem()
    );
  });
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
        // Aberto de uma vez: quem acabou de bipar o último item volta para cá,
        // e obrigá-lo a achar o botão seria um passo a mais no meio do fluxo.
        if (this.precisaFinalizarOrigem()) this.modalFinalizar.set(true);
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

  abrirModalFinalizar(): void {
    this.erroFinalizar.set(null);
    this.modalFinalizar.set(true);
  }

  fecharModalFinalizar(): void {
    if (this.finalizandoPedido()) return;
    this.modalFinalizar.set(false);
  }

  finalizarPedido(dados: FinalizacaoSistemaOrigem): void {
    if (this.finalizandoPedido()) return;

    this.finalizandoPedido.set(true);
    this.erroFinalizar.set(null);
    this.service.finalizarPedido(this.pedidoId, dados).subscribe({
      next: (processo) => {
        this.finalizandoPedido.set(false);
        this.modalFinalizar.set(false);
        this.processo.set(processo);
      },
      error: (resposta: HttpErrorResponse) => {
        this.finalizandoPedido.set(false);
        // O erro fica DENTRO do modal, com o que foi digitado preservado: o
        // caso comum é "o Oracle caiu, tenta de novo", e apagar os quatro
        // números faria o operador redigitar à toa.
        this.erroFinalizar.set(
          resposta.error?.detail ?? 'Não foi possível finalizar o pedido no sistema de origem.',
        );
      },
    });
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

