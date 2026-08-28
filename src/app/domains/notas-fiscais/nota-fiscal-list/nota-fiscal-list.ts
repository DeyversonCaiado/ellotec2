import { Component, OnInit, computed, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime } from 'rxjs';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { NotaFiscalService } from '../nota-fiscal.service';
import {
  FILTROS_VAZIOS,
  FiltrosNotaFiscal,
  NotaFiscalResumo,
  TipoOperacao,
} from '../nota-fiscal.model';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';
import { PermissaoDirective } from '../../../core/permissions/permissao.directive';

/** Mesmo tamanho de página dos outros domínios (ver produto-list.ts). */
const POR_PAGINA = 20;

@Component({
  selector: 'app-nota-fiscal-list',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, IconComponent, PageHeaderComponent, PermissaoDirective],
  templateUrl: './nota-fiscal-list.html',
})
export class NotaFiscalList implements OnInit {
  notas = signal<NotaFiscalResumo[]>([]);
  carregando = signal(true);
  filtros = signal<FiltrosNotaFiscal>({ ...FILTROS_VAZIOS });

  pagina = signal(1);
  total = signal(0);
  readonly porPagina = POR_PAGINA;
  totalPaginas = computed(() => Math.max(1, Math.ceil(this.total() / POR_PAGINA)));

  /** As três opções da aba. Entrada e saída são o mesmo documento visto dos
   *  dois lados, então são filtro desta tela e não itens de menu separados. */
  readonly abas: { valor: TipoOperacao | ''; rotulo: string }[] = [
    { valor: '', rotulo: 'Todas' },
    { valor: 'entrada', rotulo: 'Entradas' },
    { valor: 'saida', rotulo: 'Saídas' },
  ];

  // A busca vai para o servidor, então cada tecla dispararia um request — daí
  // o debounce. Mesmo desenho da listagem de pedidos.
  private readonly busca$ = new Subject<void>();

  private readonly rotuloStatus: Record<string, string> = {
    autorizada: 'Autorizada',
    cancelada: 'Cancelada',
    denegada: 'Denegada',
    rejeitada: 'Rejeitada',
  };

  private readonly corStatus: Record<string, string> = {
    autorizada: 'text-emerald-700 bg-emerald-50',
    cancelada: 'text-red-700 bg-red-50',
    denegada: 'text-red-700 bg-red-50',
    rejeitada: 'text-amber-700 bg-amber-50',
  };

  constructor(private service: NotaFiscalService) {
    this.busca$.pipe(debounceTime(400), takeUntilDestroyed()).subscribe(() => this.carregar(1));
  }

  ngOnInit(): void {
    this.carregar(1);
  }

  rotuloDoStatus(status: string): string {
    return this.rotuloStatus[status] ?? status;
  }

  corDoStatus(status: string): string {
    return this.corStatus[status] ?? 'text-gray-500 bg-gray-100';
  }

  /** Na ENTRADA quem interessa é o emitente (o fornecedor); na SAÍDA, o
   *  destinatário (o cliente). A outra ponta é sempre a própria empresa, e
   *  repetir o nome dela em toda linha não informa nada. */
  contraparte(nota: NotaFiscalResumo): { nome: string; documento: string; papel: string } {
    return nota.tipoOperacao === 'entrada'
      ? { nome: nota.emitenteRazaoSocial, documento: nota.emitenteCnpjCpf, papel: 'Fornecedor' }
      : { nome: nota.destinatarioRazaoSocial, documento: nota.destinatarioCnpjCpf, papel: 'Cliente' };
  }

  private carregar(pagina: number): void {
    this.carregando.set(true);
    this.service.listarPagina(pagina, POR_PAGINA, this.filtros()).subscribe({
      next: (resposta) => {
        this.notas.set(resposta.items);
        this.total.set(resposta.total);
        this.pagina.set(resposta.page);
        this.carregando.set(false);
      },
      error: () => this.carregando.set(false),
    });
  }

  /** Digitar não dispara request por tecla — o debounce está no construtor. */
  onBuscaChange(valor: string): void {
    this.filtros.update((atual) => ({ ...atual, q: valor }));
    this.busca$.next();
  }

  /** Troca de aba e período recarregam na hora: são um clique, não uma
   *  sequência de teclas, então não há o que debouncar. Sempre voltando para a
   *  página 1 — a página 7 do filtro anterior não existe no novo. */
  selecionarAba(valor: TipoOperacao | ''): void {
    if (this.filtros().tipoOperacao === valor) return;
    this.filtros.update((atual) => ({ ...atual, tipoOperacao: valor }));
    this.carregar(1);
  }

  onPeriodoChange(campo: 'dataInicio' | 'dataFim', valor: string): void {
    this.filtros.update((atual) => ({ ...atual, [campo]: valor }));
    this.carregar(1);
  }

  limparFiltros(): void {
    this.filtros.set({ ...FILTROS_VAZIOS });
    this.carregar(1);
  }

  temFiltroAtivo(): boolean {
    const { q, tipoOperacao, dataInicio, dataFim } = this.filtros();
    return !!(q || tipoOperacao || dataInicio || dataFim);
  }

  irParaPagina(pagina: number): void {
    if (pagina < 1 || pagina > this.totalPaginas() || pagina === this.pagina()) return;
    this.carregar(pagina);
  }

  apagar(nota: NotaFiscalResumo): void {
    if (!confirm(`Apagar a nota ${nota.numero}/${nota.serie}? Essa ação não pode ser desfeita.`)) return;
    this.service.apagar(nota.id).subscribe(() => {
      // Recarrega em vez de tirar da lista em memória: com paginação, remover
      // uma linha deixaria a página com 19 itens e o total desatualizado.
      this.carregar(this.pagina());
    });
  }
}
