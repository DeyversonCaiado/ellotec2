import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { ExpedicaoService } from '../expedicao.service';
import {
  CredencialGerente,
  FinalizacaoSistemaOrigem,
  PedidoExpedicaoDetalhe,
  SituacaoProcesso,
  TipoProcesso,
  numeroExibicao,
  rotuloTipo,
} from '../expedicao.model';
import { SenhaGerenteComponent } from '../senha-gerente.component';
import { FinalizarPedidoComponent } from '../finalizar-pedido.component';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PermissaoDirective } from '../../../core/permissions/permissao.directive';
import { AuthService } from '../../../core/auth/auth.service';

@Component({
  selector: 'app-expedicao-pedido',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    IconComponent,
    PermissaoDirective,
    SenhaGerenteComponent,
    FinalizarPedidoComponent,
  ],
  templateUrl: './expedicao-pedido.html',
})
export class ExpedicaoPedido implements OnInit {
  private service = inject(ExpedicaoService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private auth = inject(AuthService);

  pedido = signal<PedidoExpedicaoDetalhe | null>(null);
  carregando = signal(true);
  erro = signal<string | null>(null);
  abrindo = signal(false);

  /** Qual processo o gerente está resetando — null quando o modal está fechado. */
  resetando = signal<TipoProcesso | null>(null);
  erroReset = signal<string | null>(null);
  resetOcupado = signal(false);

  /** Qual etapa está sendo iniciada/finalizada em nome do operador. Um sinal
   *  por ação, e não um booleano só: os dois botões convivem na mesma caixa e
   *  travar os dois juntos esconderia qual deles está rodando. */
  delegandoInicio = signal<TipoProcesso | null>(null);
  delegandoFim = signal<TipoProcesso | null>(null);

  /** Exceção de emergência: quem tem esta chave inicia e finaliza a etapa pela
   *  execução delegada mesmo com o endereçamento inconsistente, para destravar
   *  o faturamento. O botão do rodapé — o do operador — continua escondido com
   *  a mesma mensagem de sempre: a exceção é do gerente, não do galpão. */
  podeLiberarEnderecamento = computed(
    () => !!this.auth.usuario()?.permissoes.has('expedicao.enderecamento.liberar'),
  );

  /** O endereçamento está inconsistente E quem está na tela pode atravessar. É
   *  isso que faz o botão delegado aparecer em vermelho, avisando que o clique
   *  vai passar por cima de um bloqueio. */
  liberandoEnderecamento = computed(
    () => !!this.pedido()?.bloqueioEnderecamento && this.podeLiberarEnderecamento(),
  );

  readonly numeroExibicao = numeroExibicao;
  readonly rotuloTipo = rotuloTipo;

  // ---------------------------------------------------------------------
  // Finalizar o pedido no ERP, da tela do pedido
  //
  // O caminho normal é o modal que abre sozinho no fim da conferência
  // (`expedicao-itens`). Aqui é o caminho de VOLTA: se o Oracle estava fora
  // do ar naquela hora, o pedido fica conferido aqui e aberto lá, e sem este
  // botão não haveria como tentar de novo sem resetar a conferência inteira.
  // ---------------------------------------------------------------------

  modalFinalizar = signal(false);
  finalizandoPedido = signal(false);
  erroFinalizar = signal<string | null>(null);

  precisaFinalizarOrigem = computed(() => {
    const pedido = this.pedido();
    return (
      !!pedido &&
      pedido.conferencia.status === 'finalizada' &&
      !pedido.conferencia.finalizadoOrigemEm &&
      !!this.auth.usuario()?.permissoes.has('expedicao.finalizar_origem')
    );
  });

  abrirModalFinalizar(): void {
    this.erroFinalizar.set(null);
    this.modalFinalizar.set(true);
  }

  fecharModalFinalizar(): void {
    if (this.finalizandoPedido()) return;
    this.modalFinalizar.set(false);
  }

  finalizarPedido(dados: FinalizacaoSistemaOrigem): void {
    const pedido = this.pedido();
    if (!pedido || this.finalizandoPedido()) return;

    this.finalizandoPedido.set(true);
    this.erroFinalizar.set(null);
    this.service.finalizarPedido(pedido.pedidoId, dados).subscribe({
      next: () => {
        this.finalizandoPedido.set(false);
        this.modalFinalizar.set(false);
        this.carregar();
      },
      error: (resposta: HttpErrorResponse) => {
        this.finalizandoPedido.set(false);
        // Dentro do modal e com o que foi digitado preservado — o caso comum é
        // tentar de novo, e redigitar os quatro números seria trabalho à toa.
        this.erroFinalizar.set(
          resposta.error?.detail ?? 'Não foi possível finalizar o pedido no sistema de origem.',
        );
      },
    });
  }

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

  /** Responsável designado pela etapa — nulo = ninguém. É ele que decide se os
   *  botões de execução delegada aparecem: delegar é executar NO NOME de
   *  alguém, e sem atribuição não há em nome de quem. */
  atribuicao(tipo: TipoProcesso) {
    const pedido = this.pedido();
    if (!pedido) return null;
    return tipo === 'separacao' ? pedido.atribuicaoSeparacao : pedido.atribuicaoConferencia;
  }

  /** Nome de quem responde pela etapa. Cai no genérico quando o processo já
   *  está em andamento e a atribuição foi removida no meio do caminho — o
   *  botão de finalizar continua fazendo sentido, e um rótulo vazio não. */
  rotuloOperadorAtribuido(tipo: TipoProcesso): string {
    const designado = this.atribuicao(tipo);
    if (designado) return designado.usuarioNome;
    const situacao = tipo === 'separacao' ? this.pedido()?.separacao : this.pedido()?.conferencia;
    return situacao?.usuarioNome ?? 'quem foi designado';
  }

  /** O rótulo do botão muda com o que vai ser gravado.
   *
   *  Com responsável, é "Iniciar em nome de Fulano" — o gerente precisa ver por
   *  quem está assinando. Sem responsável, quem vai ficar creditado é ele
   *  mesmo, então prometer "em nome de" seria mentira. */
  rotuloBotaoDelegado(tipo: TipoProcesso): string {
    const designado = this.atribuicao(tipo);
    return designado
      ? `Iniciar em nome de ${designado.usuarioNome}`
      : `Iniciar ${this.rotuloTipo(tipo).toLowerCase()}`;
  }

  /** A conferência só abre depois da separação fechar — a mesma regra do
   *  backend, repetida aqui só para o botão não oferecer o que vai dar 409. */
  podeIniciarDelegado(tipo: TipoProcesso, situacao: SituacaoProcesso): boolean {
    const pedido = this.pedido();
    if (!pedido) return false;
    // `statusPermiteIniciar` e não `podeIniciar`: as duas barreiras são
    // olhadas separadamente aqui porque só uma delas é atravessável. Status do
    // ERP não se resolve do galpão; endereçamento errado se resolve — e é por
    // isso que existe uma permissão para seguir assim mesmo.
    if (!pedido.statusPermiteIniciar) return false;
    if (pedido.bloqueioEnderecamento && !this.podeLiberarEnderecamento()) return false;
    if (situacao.status !== 'nao_iniciada') return false;
    // Sem responsável atribuído o botão continua aparecendo: quem clica vira o
    // operador da etapa (ver `_operador_da_etapa` no backend).
    return tipo === 'separacao' || pedido.separacao.status === 'finalizada';
  }

  iniciarDelegado(tipo: TipoProcesso): void {
    const pedido = this.pedido();
    if (!pedido || this.delegandoInicio()) return;

    this.delegandoInicio.set(tipo);
    this.erro.set(null);
    this.service.iniciarDelegado(tipo, pedido.pedidoId).subscribe({
      next: () => {
        this.delegandoInicio.set(null);
        this.carregar();
      },
      error: (resposta: HttpErrorResponse) => {
        this.delegandoInicio.set(null);
        this.erro.set(resposta.error?.detail ?? 'Não foi possível iniciar a etapa.');
      },
    });
  }

  finalizarDelegado(tipo: TipoProcesso): void {
    const pedido = this.pedido();
    if (!pedido || this.delegandoFim()) return;

    this.delegandoFim.set(tipo);
    this.erro.set(null);
    this.service.finalizarDelegado(tipo, pedido.pedidoId).subscribe({
      next: () => {
        this.delegandoFim.set(null);
        this.carregar();
      },
      error: (resposta: HttpErrorResponse) => {
        this.delegandoFim.set(null);
        this.erro.set(resposta.error?.detail ?? 'Não foi possível finalizar a etapa.');
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
