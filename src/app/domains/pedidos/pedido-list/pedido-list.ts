import { Component, OnInit, computed, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime } from 'rxjs';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { PedidoService } from '../pedido.service';
import { Pedido, calcularTotalPedido, numeroExibicaoPedido } from '../pedido.model';
import { UsuarioService } from '../../usuarios/usuario.service';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';
import { PermissaoDirective } from '../../../core/permissions/permissao.directive';

/** Mesmo tamanho de página dos outros domínios (ver produto-list.ts). */
const POR_PAGINA = 20;

@Component({
  selector: 'app-pedido-list',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, IconComponent, PageHeaderComponent, PermissaoDirective],
  templateUrl: './pedido-list.html',
})
export class PedidoList implements OnInit {
  pedidos = signal<Pedido[]>([]);
  carregando = signal(true);
  termoBusca = signal('');

  pagina = signal(1);
  total = signal(0);
  readonly porPagina = POR_PAGINA;
  totalPaginas = computed(() => Math.max(1, Math.ceil(this.total() / POR_PAGINA)));

  // A busca vai para o servidor, então cada tecla dispararia um request — daí
  // o debounce. Mesmo desenho da listagem de expedição.
  private readonly busca$ = new Subject<void>();

  readonly calcularTotal = calcularTotalPedido;
  readonly numeroExibicao = numeroExibicaoPedido;

  // Rótulo/cor só existem para as chaves conhecidas de fábrica — o catálogo
  // pedido_status no backend é administrável e hoje já tem chaves de
  // integração externa (ex: "OK", "FEC", "PCP") que não estão aqui. Pra
  // essas, cai no fallback: mostra a própria chave, com uma cor neutra, em
  // vez de ficar em branco.
  private readonly rotuloStatus: Record<string, string> = {
    rascunho: 'Rascunho',
    enviado: 'Enviado',
    aprovado: 'Aprovado',
    recusado: 'Recusado',
  };

  private readonly corStatus: Record<string, string> = {
    rascunho: 'text-gray-500 bg-gray-100',
    enviado: 'text-amber-700 bg-amber-50',
    aprovado: 'text-emerald-700 bg-emerald-50',
    recusado: 'text-red-700 bg-red-50',
  };

  rotuloDoStatus(status: string): string {
    return this.rotuloStatus[status] ?? status;
  }

  corDoStatus(status: string): string {
    return this.corStatus[status] ?? 'text-gray-500 bg-gray-100';
  }

  // id -> nome do vendedor, pra listagem não precisar de outro request por
  // linha. Carregado uma vez junto com os pedidos.
  private nomesVendedores = new Map<string, string>();

  constructor(
    private service: PedidoService,
    private usuarioService: UsuarioService,
  ) {
    this.busca$.pipe(debounceTime(400), takeUntilDestroyed()).subscribe(() => this.carregar(1));
  }

  ngOnInit(): void {
    this.carregar(1);
    this.usuarioService.listarVendedores().subscribe((lista) => {
      this.nomesVendedores = new Map(lista.map((u) => [u.id, u.nome]));
    });
  }

  private carregar(pagina: number): void {
    this.carregando.set(true);
    this.service.listarPagina(pagina, POR_PAGINA, this.termoBusca()).subscribe({
      next: (resposta) => {
        this.pedidos.set(resposta.items);
        this.total.set(resposta.total);
        this.pagina.set(resposta.page);
        this.carregando.set(false);
      },
      error: () => this.carregando.set(false),
    });
  }

  /** Digitar não dispara request por tecla — o debounce está no construtor. */
  onBuscaChange(valor: string): void {
    this.termoBusca.set(valor);
    this.busca$.next();
  }

  irParaPagina(pagina: number): void {
    if (pagina < 1 || pagina > this.totalPaginas() || pagina === this.pagina()) return;
    this.carregar(pagina);
  }

  nomeDoVendedor(pedido: Pedido): string {
    if (!pedido.vendedorId) return '—';
    return this.nomesVendedores.get(pedido.vendedorId) ?? '—';
  }

  /** A filtragem agora é do servidor (ver `listarPagina`): filtrar de novo aqui
   *  esconderia linhas da página e faria o total do rodapé não bater. */
  get pedidosFiltrados(): Pedido[] {
    return this.pedidos();
  }

  apagar(pedido: Pedido): void {
    if (!confirm(`Apagar o orçamento "${pedido.numero}"? Essa ação não pode ser desfeita.`)) return;
    this.service.apagar(pedido.id).subscribe(() => {
      // Recarrega em vez de tirar da lista em memória: com paginação, remover
      // uma linha deixaria a página com 19 itens e o total desatualizado.
      this.carregar(this.pagina());
    });
  }
}
