import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { ExpedicaoService } from '../expedicao.service';
import {
  CredencialGerente,
  PedidoExpedicaoDetalhe,
  SituacaoProcesso,
  TipoProcesso,
  numeroExibicao,
  rotuloTipo,
} from '../expedicao.model';
import { SenhaGerenteComponent } from '../senha-gerente.component';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PermissaoDirective } from '../../../core/permissions/permissao.directive';

@Component({
  selector: 'app-expedicao-pedido',
  standalone: true,
  imports: [CommonModule, RouterLink, IconComponent, PermissaoDirective, SenhaGerenteComponent],
  templateUrl: './expedicao-pedido.html',
})
export class ExpedicaoPedido implements OnInit {
  private service = inject(ExpedicaoService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  pedido = signal<PedidoExpedicaoDetalhe | null>(null);
  carregando = signal(true);
  erro = signal<string | null>(null);
  abrindo = signal(false);

  /** Qual processo o gerente está resetando — null quando o modal está fechado. */
  resetando = signal<TipoProcesso | null>(null);
  erroReset = signal<string | null>(null);
  resetOcupado = signal(false);

  readonly numeroExibicao = numeroExibicao;
  readonly rotuloTipo = rotuloTipo;

  ngOnInit(): void {
    this.carregar();
  }

  private carregar(): void {
    const id = this.route.snapshot.paramMap.get('pedidoId');
    if (!id) return;

    this.carregando.set(true);
    this.service.obterPedido(id).subscribe({
      next: (pedido) => {
        this.pedido.set(pedido);
        this.carregando.set(false);
      },
      error: () => {
        this.erro.set('Não foi possível carregar este pedido.');
        this.carregando.set(false);
      },
    });
  }

  rotuloSituacao(situacao: SituacaoProcesso): string {
    if (situacao.status === 'nao_iniciada') return 'Não iniciada';
    if (situacao.status === 'finalizada') {
      return situacao.temDivergencia ? 'Finalizada com falta' : 'Finalizada';
    }
    return `Em andamento — ${situacao.itensFinalizados} de ${situacao.itensTotal}`;
  }

  corItem(situacao: string): string {
    if (situacao === 'finalizado') return 'text-emerald-700 bg-emerald-50 dark:bg-emerald-900/30';
    if (situacao === 'em_andamento') return 'text-brand-700 bg-brand-50 dark:bg-brand-900/30';
    return 'text-gray-500 bg-gray-100 dark:bg-gray-800';
  }

  rotuloItem(situacao: string): string {
    if (situacao === 'finalizado') return 'OK';
    if (situacao === 'em_andamento') return 'Em andamento';
    return 'Pendente';
  }

  /** Rótulo do botão do rodapé: "Iniciar" quando nada foi aberto ainda,
   *  "Continuar" quando já existe processo em andamento. */
  rotuloAcao(): string {
    const pedido = this.pedido();
    if (!pedido || !pedido.proximaEtapa) return '';
    const situacao = pedido.proximaEtapa === 'separacao' ? pedido.separacao : pedido.conferencia;
    const verbo = situacao.status === 'em_andamento' ? 'Continuar' : 'Iniciar';
    return `${verbo} ${rotuloTipo(pedido.proximaEtapa).toLowerCase()}`;
  }

  abrirProcesso(): void {
    const pedido = this.pedido();
    if (!pedido?.proximaEtapa) return;

    this.abrindo.set(true);
    this.erro.set(null);
    const tipo = pedido.proximaEtapa;
    this.service.iniciarProcesso(tipo, pedido.pedidoId).subscribe({
      next: (processo) => {
        this.abrindo.set(false);
        this.router.navigate(['/expedicao', pedido.pedidoId, tipo, processo.id]);
      },
      error: (resposta: HttpErrorResponse) => {
        this.abrindo.set(false);
        this.erro.set(resposta.error?.detail ?? 'Não foi possível abrir o processo.');
      },
    });
  }

  pedirSenhaParaResetar(tipo: TipoProcesso): void {
    this.erroReset.set(null);
    this.resetando.set(tipo);
  }

  confirmarReset(credencial: CredencialGerente): void {
    const tipo = this.resetando();
    const pedido = this.pedido();
    if (!tipo || !pedido) return;

    const processoId = tipo === 'separacao' ? pedido.separacao.id : pedido.conferencia.id;
    if (!processoId) return;

    this.resetOcupado.set(true);
    this.service.resetar(tipo, processoId, credencial).subscribe({
      next: () => {
        this.resetOcupado.set(false);
        this.resetando.set(null);
        this.carregar();
      },
      error: (resposta: HttpErrorResponse) => {
        this.resetOcupado.set(false);
        this.erroReset.set(resposta.error?.detail ?? 'Não foi possível resetar.');
      },
    });
  }
}
