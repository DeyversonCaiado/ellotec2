import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime } from 'rxjs';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AutoCompleteModule } from 'primeng/autocomplete';
import { EntregaService } from '../entrega.service';
import {
  CAMPOS_FILTRO,
  CampoFiltro,
  EntregaNotaResumo,
  FILTROS_ENTREGA_VAZIOS,
  FiltrosEntrega,
  STATUS_PRAZO,
  StatusPrazo,
  corStatusDaNota,
  lerFiltrosSalvos,
  limparMantendoPeriodo,
  rotuloStatusDaNota,
  rotuloTipoNota,
  salvarFiltros,
  temFiltroAplicado,
} from '../entrega.model';
import { AuthService } from '../../../core/auth/auth.service';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

/** Mesmo tamanho de página dos outros domínios (ver produto-list.ts). */
const POR_PAGINA = 20;

@Component({
  selector: 'app-entrega-list',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    AutoCompleteModule,
    IconComponent,
    PageHeaderComponent,
  ],
  templateUrl: './entrega-list.html',
})
export class EntregaList implements OnInit {
  private service = inject(EntregaService);
  private auth = inject(AuthService);

  notas = signal<EntregaNotaResumo[]>([]);
  carregando = signal(true);
  filtros = signal<FiltrosEntrega>({ ...FILTROS_ENTREGA_VAZIOS });

  /** O que cada autocomplete está mostrando agora. Vem do servidor a cada
   *  busca — a tela não guarda mais o conjunto inteiro de valores, que chegava
   *  a centenas por campo num mês real. */
  sugestoes = signal<Record<string, string[]>>({});

  /** Campos cuja última busca bateu no teto do servidor. A tela avisa para
   *  refinar, em vez de deixar a pessoa achar que aquilo é tudo que existe. */
  truncados = signal<Record<string, boolean>>({});

  /** O painel de filtros é longo (18 campos): fica recolhido por padrão, e a
   *  tela abre mostrando a lista, que é o que se veio ver. */
  painelAberto = signal(false);

  pagina = signal(1);
  total = signal(0);
  readonly porPagina = POR_PAGINA;
  totalPaginas = computed(() => Math.max(1, Math.ceil(this.total() / POR_PAGINA)));

  readonly campos: CampoFiltro[] = CAMPOS_FILTRO;
  readonly rotuloStatusDaNota = rotuloStatusDaNota;
  readonly corStatusDaNota = corStatusDaNota;
  readonly rotuloTipoNota = rotuloTipoNota;

  /** Quantos campos do painel têm valor escolhido — o número no botão que abre
   *  o painel. Com ele recolhido, é a única pista de que há recorte aplicado. */
  quantidadeFiltrosAtivos = computed(() => {
    const filtros = this.filtros();
    return this.campos.filter((campo) => filtros[campo.chave].length > 0).length;
  });

  temFiltroAtivo = computed(() => temFiltroAplicado(this.filtros()));

  /** As abas de prazo são o filtro que a operação mais usa: quem abre esta
   *  tela quer saber o que está atrasado, não navegar por status de nota. */
  readonly abasPrazo: { valor: StatusPrazo | ''; rotulo: string }[] = [
    { valor: '', rotulo: 'Todas' },
    { valor: 'em_atraso', rotulo: 'Em atraso' },
    { valor: 'no_prazo', rotulo: 'No prazo' },
    { valor: 'sem_mapa', rotulo: 'Sem mapa' },
    { valor: 'entregue', rotulo: 'Entregues' },
  ];

  // A busca vai para o servidor, então cada tecla dispararia um request.
  private readonly busca$ = new Subject<void>();

  constructor() {
    this.busca$.pipe(debounceTime(400), takeUntilDestroyed()).subscribe(() => this.carregar(1));
  }

  ngOnInit(): void {
    // O recorte montado antes do F5 volta como estava. Ler ANTES de carregar
    // evita a piscada de "lista sem filtro" seguida da lista filtrada.
    this.filtros.set(lerFiltrosSalvos(this.usuarioId()));
    this.carregar(1);
  }

  private usuarioId(): string | null {
    return this.auth.usuario()?.id ?? null;
  }

  rotuloPrazo(status: StatusPrazo): string {
    return STATUS_PRAZO[status]?.rotulo ?? status;
  }

  corPrazo(status: StatusPrazo): string {
    return STATUS_PRAZO[status]?.cor ?? 'text-gray-500 bg-gray-100';
  }

  // -------------------------------------------------------------------
  // Painel de filtros
  // -------------------------------------------------------------------

  valoresDoCampo(campo: CampoFiltro): string[] {
    return this.filtros()[campo.chave];
  }

  sugestoesDoCampo(campo: CampoFiltro): string[] {
    return this.sugestoes()[campo.chave] ?? [];
  }

  campoTruncado(campo: CampoFiltro): boolean {
    return this.truncados()[campo.chave] ?? false;
  }

  /** `completeMethod` do autocomplete: pede ao servidor as sugestões daquele
   *  campo, recortadas pelo termo digitado.
   *
   *  Vai ao servidor a cada busca, e não uma vez só na carga da tela: baixar
   *  todos os valores de todos os campos antecipadamente dava centenas de
   *  itens por campo num mês real, e crescia com o período. O `[delay]` do
   *  PrimeNG já segura as teclas — não é um request por letra. */
  buscarSugestoes(campo: CampoFiltro, termo: string): void {
    const { dataInicio, dataFim } = this.filtros();
    this.service.buscarSugestoes(campo.chave, termo ?? '', dataInicio, dataFim).subscribe({
      next: (resposta) => {
        this.sugestoes.update((atual) => ({ ...atual, [campo.chave]: resposta.valores }));
        this.truncados.update((atual) => ({ ...atual, [campo.chave]: resposta.truncado }));
      },
      // Lista vazia é o comportamento certo do autocomplete quando a busca
      // falha: sugerir o resultado velho de outro termo seria pior.
      error: () => this.sugestoes.update((atual) => ({ ...atual, [campo.chave]: [] })),
    });
  }

  /** Um campo do painel mudou. Recarrega da página 1: a página 7 do recorte
   *  anterior não existe no novo. */
  aoMudarCampo(campo: CampoFiltro, valores: string[]): void {
    this.atualizarFiltros((atual) => ({ ...atual, [campo.chave]: valores ?? [] }));
  }

  aplicarAba(valor: StatusPrazo | ''): void {
    if (this.filtros().statusPrazo === valor) return;
    this.atualizarFiltros((atual) => ({ ...atual, statusPrazo: valor }));
  }

  /** O período é o recorte que DEFINE quais valores o painel oferece. Não há
   *  nada a recarregar aqui: a busca de sugestões manda o período junto, então
   *  a próxima digitação já sai do intervalo novo. */
  aplicarPeriodo(campo: 'dataInicio' | 'dataFim', valor: string): void {
    if (this.filtros()[campo] === valor) return;
    this.atualizarFiltros((atual) => ({ ...atual, [campo]: valor }));
    // As sugestões em memória são do período anterior — descartar é mais
    // honesto que oferecer valores que a listagem não traz mais.
    this.sugestoes.set({});
  }

  onBuscaChange(valor: string): void {
    this.filtros.update((atual) => ({ ...atual, q: valor }));
    this.persistir();
    this.busca$.next();
  }

  /** Limpa o painel inteiro de uma vez, PRESERVANDO o período — ver
   *  `limparMantendoPeriodo` no model para o porquê. As opções não são
   *  recarregadas: o período não mudou, então elas continuam válidas. */
  limparFiltros(): void {
    this.atualizarFiltros(limparMantendoPeriodo);
  }

  private atualizarFiltros(mudanca: (atual: FiltrosEntrega) => FiltrosEntrega): void {
    this.filtros.update(mudanca);
    this.persistir();
    this.carregar(1);
  }

  private persistir(): void {
    salvarFiltros(this.usuarioId(), this.filtros());
  }

  // -------------------------------------------------------------------
  // Carga
  // -------------------------------------------------------------------

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

  irParaPagina(pagina: number): void {
    if (pagina < 1 || pagina > this.totalPaginas() || pagina === this.pagina()) return;
    this.carregar(pagina);
  }
}
