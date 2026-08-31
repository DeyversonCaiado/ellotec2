import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CotacaoService } from '../cotacao.service';
import {
  CotacaoEmpresa,
  CotacaoFiltros,
  CotacaoItem,
  JANELA_MAXIMA_DIAS,
  SituacaoResposta,
} from '../cotacao.model';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

const POR_PAGINA = 50;

/** Período inicial: os últimos 3 dias. Curto de propósito — é o recorte que
 *  responde rápido e o que interessa no dia a dia (o que está vencendo agora).
 *  Quem precisa de histórico amplia o filtro. */
const DIAS_INICIAIS = 3;

function paraIso(data: Date): string {
  return data.toISOString().slice(0, 10);
}

@Component({
  selector: 'app-cotacao-list',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PageHeaderComponent],
  templateUrl: './cotacao-list.html',
})
export class CotacaoList implements OnInit {
  private service = inject(CotacaoService);

  itens = signal<CotacaoItem[]>([]);
  estados = signal<string[]>([]);
  empresas = signal<CotacaoEmpresa[]>([]);
  total = signal(0);
  pagina = signal(1);
  carregando = signal(true);
  erro = signal('');

  filtros = signal<CotacaoFiltros>(this.filtrosIniciais());

  exportando = signal(false);

  totalPaginas = computed(() => Math.max(1, Math.ceil(this.total() / POR_PAGINA)));

  /** Buscando por número de cotação: o período não se aplica, e a tela mostra
   *  isso desabilitando as datas em vez de deixar o usuário achar que elas
   *  ainda valem. */
  buscandoPorCotacao = computed(() => this.filtros().cotacao.trim().length > 0);

  /** O intervalo de linhas que a página mostra ("1–50 de 219.824"). Com
   *  centenas de milhares de itens, saber só o número da página não ajuda a
   *  ter noção de onde se está. */
  primeiroDaPagina = computed(() =>
    this.total() === 0 ? 0 : (this.pagina() - 1) * POR_PAGINA + 1,
  );
  ultimoDaPagina = computed(() => Math.min(this.pagina() * POR_PAGINA, this.total()));

  private filtrosIniciais(): CotacaoFiltros {
    const hoje = new Date();
    const inicio = new Date();
    inicio.setDate(hoje.getDate() - DIAS_INICIAIS);
    return {
      dataInicio: paraIso(inicio),
      dataFim: paraIso(hoje),
      cotacao: '',
      q: '',
      hospital: '',
      cidade: '',
      estado: '',
      empresaId: '',
      situacao: 'todas',
    };
  }

  ngOnInit(): void {
    this.service.opcoesDeFiltro().subscribe({
      next: (opcoes) => {
        this.estados.set(opcoes.estados);
        this.empresas.set(opcoes.empresas);
      },
      // Sem as opções a tela ainda funciona (os selects ficam vazios), então
      // isso não vira erro de tela — a listagem é que importa.
      error: () => undefined,
    });
    this.buscar(1);
  }

  /** Atualiza um filtro e volta para a página 1. Manter a página seria mostrar
   *  a página 7 de um resultado que agora tem 2. */
  atualizarFiltro<K extends keyof CotacaoFiltros>(campo: K, valor: CotacaoFiltros[K]): void {
    this.filtros.update((atuais) => ({ ...atuais, [campo]: valor }));
    this.buscar(1);
  }

  onSituacaoChange(valor: string): void {
    this.atualizarFiltro('situacao', valor as SituacaoResposta);
  }

  limparFiltros(): void {
    this.filtros.set(this.filtrosIniciais());
    this.buscar(1);
  }

  irParaPagina(pagina: number): void {
    if (pagina < 1 || pagina > this.totalPaginas() || pagina === this.pagina()) return;
    this.buscar(pagina);
  }


  /**
   * Baixa o CSV com TODAS as linhas do filtro atual (não só a página).
   *
   * O arquivo chega como blob porque a chamada precisa do token no header —
   * um link direto não carregaria o `Authorization` do interceptor. O
   * `URL.createObjectURL` + clique num link é o jeito padrão de entregar isso
   * ao navegador; o `revokeObjectURL` no fim libera a memória do blob.
   */
  exportar(): void {
    if (this.exportando() || this.periodoInvalido() || this.total() === 0) return;
    this.exportando.set(true);
    this.service.exportar(this.filtros(), 'dataVencimento', 'desc').subscribe({
      next: (arquivo) => {
        const url = URL.createObjectURL(arquivo);
        const link = document.createElement('a');
        link.href = url;
        link.download = `cotacoes-${new Date().toISOString().slice(0, 10)}.csv`;
        link.click();
        URL.revokeObjectURL(url);
        this.exportando.set(false);
      },
      error: (falha) => {
        // Com `responseType: 'blob'`, o Angular entrega o corpo do ERRO
        // também como Blob — `falha.error.detail` seria undefined. Por isso o
        // JSON é lido do blob antes de virar mensagem. Vale a pena porque o
        // backend responde 504 com "reduza o período", que é acionável.
        this.exportando.set(false);
        const padrao = 'Não foi possível gerar o CSV. Tente um período menor.';
        const corpo = falha?.error;
        if (corpo instanceof Blob) {
          corpo
            .text()
            .then((texto) => this.erro.set(JSON.parse(texto)?.detail ?? padrao))
            .catch(() => this.erro.set(padrao));
          return;
        }
        this.erro.set(corpo?.detail ?? padrao);
      },
    });
  }

  /** Item ainda não cotado por nós. É o que o comercial procura na tela. */
  naoRespondido(item: CotacaoItem): boolean {
    return !item.quantidadeRespondida;
  }

  private periodoInvalido(): string {
    // Número da cotação dispensa a data — mesma regra do backend.
    if (this.buscandoPorCotacao()) return '';
    const { dataInicio, dataFim } = this.filtros();
    if (!dataInicio || !dataFim) return 'Informe o período de vencimento.';
    const inicio = new Date(dataInicio + 'T00:00:00');
    const fim = new Date(dataFim + 'T00:00:00');
    if (fim < inicio) return 'A data final não pode ser anterior à data inicial.';
    const dias = Math.round((fim.getTime() - inicio.getTime()) / 86_400_000);
    if (dias > JANELA_MAXIMA_DIAS) return `O período não pode passar de ${JANELA_MAXIMA_DIAS} dias.`;
    return '';
  }

  private buscar(pagina: number): void {
    const problema = this.periodoInvalido();
    if (problema) {
      // Avisa antes de ir à API. A barreira de verdade continua no backend —
      // isto é só para não gastar uma chamada que já se sabe que falha.
      this.erro.set(problema);
      this.itens.set([]);
      this.total.set(0);
      this.carregando.set(false);
      return;
    }
    this.erro.set('');
    this.carregando.set(true);
    this.service.listar(this.filtros(), pagina, POR_PAGINA, 'dataVencimento', 'desc').subscribe({
      next: (resposta) => {
        this.itens.set(resposta.items);
        this.total.set(resposta.total);
        this.pagina.set(resposta.page);
        this.carregando.set(false);
      },
      error: (falha) => {
        this.erro.set(falha?.error?.detail ?? 'Não foi possível consultar as cotações.');
        this.itens.set([]);
        this.carregando.set(false);
      },
    });
  }
}
