import {
  Component,
  OnInit,
  WritableSignal,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subject, debounceTime } from 'rxjs';
import { AccordionModule } from 'primeng/accordion';
import { SelectModule } from 'primeng/select';
import { MultiSelectModule } from 'primeng/multiselect';
import { ExpedicaoService } from '../expedicao.service';
import {
  Atribuicao,
  ColunaOrdenavel,
  Duracao,
  FiltroSituacao,
  Operador,
  PedidoExpedicaoLista,
  SituacaoProcesso,
  TipoProcesso,
  duracaoEntre,
  inicioDaEtapa,
  numeroExibicao,
  rotuloTipo,
} from '../expedicao.model';
import { AuthService } from '../../../core/auth/auth.service';
import { IconComponent } from '../../../shared/ui/icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

/**
 * Cada chave responde a uma pergunta que alguém faz de verdade no galpão —
 * por isso não é um filtro genérico por status de cada etapa, que obrigaria o
 * usuário a combinar dois campos pra chegar na mesma resposta:
 *
 * - operador: "o que ninguém pegou ainda?" (nao_iniciados)
 * - coordenador: "quem está com o quê?" (em_separacao / em_conferencia),
 *   "o que já pode conferir?" (aguardando_conferencia), "o que fechou com
 *   falta?" (divergentes)
 */
// `FiltroSituacao` mora em expedicao.model.ts desde que o recorte passou a ser
// feito pelo servidor: o valor viaja na query string, então é contrato de API e
// não detalhe desta tela. Reexportado para quem já importava daqui.
export type { FiltroSituacao } from '../expedicao.model';

/**
 * As preferências desta tela, persistidas em localStorage — mesmo prefixo das
 * outras preferências do app (ver tema.service.ts).
 *
 * **Os filtros avançados inteiros são preferência, não pergunta do momento.**
 * Quem trabalha no galpão olha sempre o mesmo recorte — o status do ERP que
 * interessa (normalmente só PED), a filial em que está, e muitas vezes só os
 * pedidos dele — e remarcar isso toda manhã é trabalho repetido. Os filtros que
 * ficam FORA daqui são os de cima: as abas de situação, o período e a busca
 * digitada, que são de fato a pergunta daquele minuto.
 *
 * **Cada chave termina no id do usuário logado.** O desktop do coordenador e o
 * coletor do galpão são máquinas compartilhadas: sem o sufixo, o "somente os
 * meus" de quem saiu vira o filtro de quem entrou, e a lista aparece curta sem
 * motivo aparente. Ver `chaveDaPreferencia`.
 */
const STORAGE_PREFIXO = 'ellotec_erp_expedicao';
const PREF_AVANCADOS_ABERTOS = 'filtros_avancados';
const PREF_STATUS_PEDIDO = 'status_pedido';
const PREF_EMPRESA = 'empresa';
const PREF_OPERADOR = 'operador';
const PREF_SOMENTE_MEUS = 'somente_meus';
const PREF_POR_PAGINA = 'por_pagina';

/** Opções de itens por página. O teto é 100 porque é o que o backend aceita
 *  (ver `per_page = min(...)` em expedicao_router.py) — pedir mais devolveria
 *  100 mesmo assim, e a tela mentiria sobre o que está mostrando. */
const OPCOES_POR_PAGINA = [20, 50, 100];

/** Começa em 50, e não nos 20 dos outros domínios: quem distribui trabalho
 *  seleciona vários pedidos de uma vez, e a seleção não sobrevive à troca de
 *  página — com 20 por página, atribuir o dia inteiro vira dezenas de idas e
 *  vindas. */
const POR_PAGINA_PADRAO = 50;

/** yyyy-MM-dd, formato que o <input type="date"> lê e que a API espera. */
function paraCampoData(data: Date): string {
  return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, '0')}-${String(data.getDate()).padStart(2, '0')}`;
}

function primeiroDiaDoMes(): string {
  const agora = new Date();
  return paraCampoData(new Date(agora.getFullYear(), agora.getMonth(), 1));
}

function hoje(): string {
  return paraCampoData(new Date());
}

/**
 * Rótulo legível para uma chave do catálogo `pedido_status`.
 *
 * As chaves do ERP (PED, OK, CAN…) ficam como estão de propósito: é assim que
 * as pessoas do galpão se referem a elas, e traduzir criaria um segundo
 * vocabulário para a mesma coisa. Só as etapas que nós mesmos cadastramos
 * (ver STATUS_DA_EXPEDICAO em pedido_publico.py) ganham rótulo, porque foram
 * escritas em snake_case e ninguém fala "em_conferencia".
 */
const ROTULOS_STATUS_PEDIDO: Record<string, string> = {
  em_separacao: 'Em separação',
  separado: 'Separado',
  em_conferencia: 'Em conferência',
  conferido: 'Conferido',
};

function rotuloStatusPedido(chave: string): string {
  return ROTULOS_STATUS_PEDIDO[chave] ?? chave;
}

interface OpcaoFiltro {
  chave: FiltroSituacao;
  rotulo: string;
}

const OPCOES: OpcaoFiltro[] = [
  { chave: 'todos', rotulo: 'Todos' },
  { chave: 'nao_iniciados', rotulo: 'Não iniciados' },
  { chave: 'em_separacao', rotulo: 'Em separação' },
  { chave: 'aguardando_conferencia', rotulo: 'Aguardando conferência' },
  { chave: 'em_conferencia', rotulo: 'Em conferência' },
  { chave: 'concluidos', rotulo: 'Concluídos' },
  { chave: 'divergentes', rotulo: 'Com divergência' },
];

// A tradução de cada situação para uma condição de banco mora no backend
// (`_recorte_da_situacao` em expedicao_service.py), e é a única que existe.
// Havia uma cópia aqui, aplicada sobre a página carregada — duas verdades para
// a mesma pergunta, que divergiam em silêncio.

@Component({
  selector: 'app-expedicao-list',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    SelectModule,
    MultiSelectModule,
    AccordionModule,
    IconComponent,
    PageHeaderComponent,
  ],
  templateUrl: './expedicao-list.html',
})
export class ExpedicaoList implements OnInit {
  private service = inject(ExpedicaoService);
  private auth = inject(AuthService);

  pedidos = signal<PedidoExpedicaoLista[]>([]);
  carregando = signal(true);
  erro = signal<string | null>(null);

  termoBusca = signal('');
  situacao = signal<FiltroSituacao>('todos');

  // Os quatro filtros avançados nascem do que ficou salvo da última sessão
  // DESTE usuário. Ver o bloco de preferências no topo do arquivo.
  operadorId = signal(this.lerTexto(PREF_OPERADOR));
  empresaId = signal(this.lerTexto(PREF_EMPRESA));
  somenteMeus = signal(this.lerBooleano(PREF_SOMENTE_MEUS));

  /** Chaves do catálogo pedido_status marcadas no multiselect. Vazio = todos.
   *  Vai para o servidor junto com a página (ver carregar): filtrar status na
   *  página já carregada devolveria 3 linhas de 20 e um total que não bate. */
  statusPedido = signal<string[]>(this.lerLista(PREF_STATUS_PEDIDO));

  /**
   * Pedidos marcados no checkbox da primeira coluna. Set, não array: marcar e
   * desmarcar é a operação mais frequente da tela, e `has`/`delete` são O(1).
   *
   * Só existe no desktop. Abaixo de 800px a grid vira card e o alvo é o
   * coletor de 320px — distribuir trabalho é tarefa de coordenador sentado,
   * não de quem está com o leitor na mão.
   */
  selecionados = signal<Set<string>>(new Set());

  /** Diálogo de atribuir aberto (null = fechado). Guarda a etapa escolhida. */
  atribuindo = signal<TipoProcesso | null>(null);
  /** Nome diferente de `operadores` (o do filtro, tirado da página carregada):
   *  este vem do backend filtrado por quem PODE executar a etapa. */
  operadoresDisponiveis = signal<Operador[]>([]);
  operadorEscolhido = signal<string | null>(null);
  atribuindoOcupado = signal(false);
  erroAtribuicao = signal<string | null>(null);

  /** Só quem distribui trabalho vê o checkbox e o botão. A trava real é do
   *  backend (`expedicao.atribuir` no endpoint) — isto aqui é só UX. */
  podeAtribuir = computed(() => !!this.auth.usuario()?.permissoes.has('expedicao.atribuir'));

  /** Catálogo vindo de GET /expedicao/status-pedido — todas as chaves possíveis, não só
   *  as que aparecem na página atual. Por isso não sai da lista carregada,
   *  diferente de `empresas` e `operadores` logo abaixo. */
  statusDisponiveis = signal<{ chave: string; rotulo: string }[]>([]);

  // Período pela data do pedido — a data que aparece na tela. Começa no mês
  // atual: é o recorte que responde "o que é deste mês?" sem digitar nada.
  dataInicio = signal(primeiroDiaDoMes());
  dataFim = signal(hoje());

  // Busca e período vão para o servidor, então mudança neles recarrega a
  // página 1. Sem debounce a busca dispararia um request por tecla.
  private readonly busca$ = new Subject<void>();

  pagina = signal(1);
  total = signal(0);
  /** Quantos pedidos há em cada situação NO PERÍODO — vem pronto do servidor.
   *
   *  Já existiu uma contagem aqui, feita sobre a página carregada, e ela mentia:
   *  com o filtro no servidor mostrava "Em separação (50)" numa fila de 900.
   *  Esta vem de `contagensPorSituacao`, calculada em cima do período inteiro. */
  contagens = signal<Record<FiltroSituacao, number> | null>(null);
  /** Ordenação atual. Vai para o SERVIDOR: ordenar a página carregada
   *  reordenaria 50 linhas de 1.200 e pareceria que funcionou. */
  sort = signal<ColunaOrdenavel>('sync_updated_at');
  sortType = signal<'asc' | 'desc'>('desc');

  porPagina = signal(this.lerPorPagina());
  readonly opcoesPorPagina = OPCOES_POR_PAGINA;
  totalPaginas = computed(() => Math.max(1, Math.ceil(this.total() / this.porPagina())));

  /** Se os filtros avançados abrem junto com a tela. É preferência de uso, não
   *  estado de filtro: quem trabalha sempre com o mesmo recorte deixa aberto,
   *  quem usa só a busca deixa fechado — e não quer reabrir todo dia. */
  avancadosAbertos = signal(this.lerBooleano(PREF_AVANCADOS_ABERTOS));

  readonly opcoes = OPCOES;
  readonly numeroExibicao = numeroExibicao;
  readonly rotuloTipo = rotuloTipo;

  constructor() {
    // Um effect por preferência, e não um que grave tudo junto: assim cada
    // gravação só acontece quando aquele signal muda. `limparFiltros` não
    // precisa apagar nada à mão — ele zera os signals e estes effects gravam o
    // estado zerado, que é o que a pessoa acabou de pedir.
    effect(() => this.gravar(PREF_AVANCADOS_ABERTOS, this.avancadosAbertos()));
    effect(() => this.gravar(PREF_STATUS_PEDIDO, this.statusPedido()));
    effect(() => this.gravar(PREF_EMPRESA, this.empresaId()));
    effect(() => this.gravar(PREF_OPERADOR, this.operadorId()));
    effect(() => this.gravar(PREF_SOMENTE_MEUS, this.somenteMeus()));
    effect(() => this.gravar(PREF_POR_PAGINA, this.porPagina()));
    this.busca$
      .pipe(debounceTime(400), takeUntilDestroyed())
      .subscribe(() => this.carregar(1));
  }

  /**
   * Empresas e operadores do filtro vêm do CADASTRO, carregados uma vez no
   * `ngOnInit` — não da página de pedidos que está na tela.
   *
   * Já saíram da página carregada, e o resultado era um filtro que só oferecia
   * o que já dava para ver: a matriz sumia da lista quando nenhum pedido dela
   * caía naquela página, e o operador que ainda não tinha pegado pedido nenhum
   * não aparecia — justamente quem se quer procurar. Filtro tem que oferecer o
   * universo, não a amostra.
   *
   * Os dois endpoints são da própria expedição (`/expedicao/empresas`,
   * `/expedicao/operadores`) e não dos domínios donos: aqueles exigem
   * `empresas.acessar` e `usuarios.acessar`, chaves que o operador de galpão
   * não tem, e o 403 derrubaria a tela inteira (ver `listarStatusPedido`).
   */
  empresas = signal<{ id: string; nome: string }[]>([]);
  operadores = signal<Operador[]>([]);

  /**
   * TODOS os filtros são resolvidos no servidor, na mesma consulta paginada —
   * inclusive situação, empresa e operador, que antes recortavam a página já
   * carregada. Por isso não existe mais uma lista "filtrada" derivada: o que o
   * servidor devolve JÁ é o recorte, e o `total` embaixo descreve o filtro
   * inteiro, não as linhas visíveis.
   *
   * O que quebrava antes: com 50 por página e o filtro no cliente, um pedido em
   * separação que estava na página 7 simplesmente não era encontrado, e a tela
   * mostrava "3 de 1.240" — três linhas sobreviventes de um total que ignorava
   * o filtro.
   */

  temFiltroAtivo = computed(
    () =>
      this.situacao() !== 'todos' ||
      !!this.operadorId() ||
      !!this.empresaId() ||
      this.somenteMeus() ||
      this.statusPedido().length > 0 ||
      !!this.termoBusca(),
  );

  /** Quantos filtros avançados estão valendo — o cabeçalho do accordion diz
   *  isso porque, fechado, ele esconde a razão de a lista estar curta. */
  avancadosAtivos = computed(
    () =>
      (this.operadorId() ? 1 : 0) +
      (this.empresaId() ? 1 : 0) +
      (this.somenteMeus() ? 1 : 0) +
      (this.statusPedido().length > 0 ? 1 : 0),
  );

  ngOnInit(): void {
    this.carregar(1);
    this.service.listarStatusPedido().subscribe({
      next: (chaves) =>
        this.statusDisponiveis.set(
          chaves
            .map((chave) => ({ chave, rotulo: rotuloStatusPedido(chave) }))
            .sort((a, b) => a.rotulo.localeCompare(b.rotulo)),
        ),
      // Sem catálogo o multiselect fica vazio, mas a lista continua servindo:
      // é um filtro a menos, não uma tela quebrada.
      error: () => this.statusDisponiveis.set([]),
    });
    // Mesma tolerância do catálogo de status: se o request falhar, o filtro
    // fica vazio e a lista continua servindo.
    this.service.listarEmpresas().subscribe({
      next: (lista) => {
        this.empresas.set(lista);
        this.descartarSeSumiu(this.empresaId, lista.map((empresa) => empresa.id));
      },
      error: () => this.empresas.set([]),
    });
    this.service.listarOperadoresDoFiltro().subscribe({
      next: (lista) => {
        this.operadores.set(lista);
        this.descartarSeSumiu(this.operadorId, lista.map((operador) => operador.id));
      },
      error: () => this.operadores.set([]),
    });
  }

  /**
   * Joga fora um filtro salvo que aponta para algo que não existe mais — o
   * operador que saiu da empresa, a filial que foi desativada.
   *
   * Sem isto, o filtro continuaria viajando para o servidor e devolvendo lista
   * vazia, enquanto o `<select>` mostraria em branco (nenhuma `<option>` casa
   * com o valor). O usuário veria "nenhum pedido encontrado" sem nada marcado
   * na tela explicando por quê — e o único jeito de sair seria limpar filtros
   * às cegas.
   *
   * Só recarrega quando de fato descartou: o caso normal é o filtro continuar
   * válido, e um request a mais em toda abertura da tela sairia caro à toa.
   */
  private descartarSeSumiu(filtro: WritableSignal<string>, idsValidos: string[]): void {
    if (filtro() && !idsValidos.includes(filtro())) {
      filtro.set('');
      this.carregar(1);
    }
  }

  /** Mudar o tamanho da página volta para a primeira: manter o número da
   *  página atual apontaria para um offset que não existe mais. */
  /**
   * Clicar no cabeçalho ordena. Clicar de novo na MESMA coluna inverte — é o
   * comportamento que todo mundo espera de grid, e evita um segundo controle
   * só para escolher a direção.
   *
   * Volta para a página 1: manter a página atual mostraria um pedaço do meio
   * de uma ordenação nova, que não quer dizer nada.
   */
  ordenarPor(coluna: ColunaOrdenavel): void {
    if (this.sort() === coluna) {
      this.sortType.set(this.sortType() === 'asc' ? 'desc' : 'asc');
    } else {
      this.sort.set(coluna);
      // Data começa da mais recente; texto começa de A. É o que a pessoa quer
      // ver primeiro em cada caso.
      this.sortType.set(coluna === 'cliente_nome_fantasia' || coluna === 'numero' ? 'asc' : 'desc');
    }
    this.carregar(1);
  }

  /**
   * Seta do cabeçalho. Coluna ordenável que NÃO é a ativa mostra '⇅' apagado —
   * é o que avisa que dá para clicar ali. Sem isso, ordenável e não-ordenável
   * ficam idênticas, e a pessoa só descobre clicando em tudo.
   */
  setaDe(coluna: ColunaOrdenavel): string {
    if (this.sort() !== coluna) return '⇅';
    return this.sortType() === 'asc' ? '▲' : '▼';
  }

  /** Ativa em cor de marca; ordenável inativa fica discreta, como convite. */
  corSeta(coluna: ColunaOrdenavel): string {
    return this.sort() === coluna
      ? 'text-brand-600 dark:text-brand-400'
      : 'text-gray-300 dark:text-gray-600';
  }

  onPorPaginaChange(valor: number): void {
    this.porPagina.set(Number(valor));
    this.carregar(1);
  }

  // -------------------------------------------------------------------------
  // Mudança de filtro = ida ao servidor, na página 1
  //
  // Todos recarregam, e todos voltam para a primeira página: continuar na
  // página 7 depois de trocar o filtro apontaria para um offset que não existe
  // mais no novo recorte. Nenhum passa pelo debounce — são cliques, não
  // digitação (só a busca digitada tem debounce, ver `onBuscaChange`).
  // -------------------------------------------------------------------------

  onStatusPedidoChange(chaves: string[]): void {
    this.statusPedido.set(chaves);
    this.carregar(1);
  }

  /** O número da aba. Nulo antes da primeira resposta — aí o botão sai sem
   *  contagem em vez de piscar um zero que não é verdade. */
  contagem(situacao: FiltroSituacao): number | null {
    return this.contagens()?.[situacao] ?? null;
  }

  /** As mesmas opções, com a contagem no rótulo — o `p-select` do coletor não
   *  tem onde pendurar um badge, então o número entra no texto. */
  opcoesComContagem = computed(() => {
    const contagens = this.contagens();
    return this.opcoes.map((opcao) => ({
      chave: opcao.chave,
      rotulo: contagens ? `${opcao.rotulo} (${contagens[opcao.chave]})` : opcao.rotulo,
    }));
  });

  onSituacaoChange(situacao: FiltroSituacao): void {
    this.situacao.set(situacao);
    this.carregar(1);
  }

  onEmpresaChange(empresaId: string): void {
    this.empresaId.set(empresaId);
    this.carregar(1);
  }

  onOperadorChange(operadorId: string): void {
    this.operadorId.set(operadorId);
    this.carregar(1);
  }

  /** "Somente os meus" é o filtro por operador apontando para mim — por isso
   *  ele zera a escolha manual em vez de conviver com ela (o select fica
   *  desabilitado no template enquanto isto estiver marcado). */
  onSomenteMeusChange(marcado: boolean): void {
    this.somenteMeus.set(marcado);
    if (marcado) this.operadorId.set('');
    this.carregar(1);
  }

  private carregar(pagina: number): void {
    this.carregando.set(true);
    this.erro.set(null);
    this.service
      .listarPedidos({
        page: pagina,
        perPage: this.porPagina(),
        dataInicio: this.dataInicio(),
        dataFim: this.dataFim(),
        q: this.termoBusca(),
        statusPedido: this.statusPedido(),
        empresaId: this.empresaId(),
        // "Somente os meus" é o filtro por operador com o meu id — um conceito,
        // um parâmetro. Ver `onSomenteMeusChange`.
        operadorId: this.somenteMeus()
          ? (this.auth.usuario()?.id ?? '')
          : this.operadorId(),
        situacao: this.situacao(),
        sort: this.sort(),
        sortType: this.sortType(),
      })
      .subscribe({
        next: (resposta) => {
          this.pedidos.set(resposta.items);
          // A seleção não sobrevive à troca de página: marcar 5 pedidos, mudar
          // de página e atribuir sem enxergar o que estava marcado é receita
          // de atribuição errada.
          this.selecionados.set(new Set());
          this.total.set(resposta.total);
          this.contagens.set(resposta.contagensPorSituacao);
          this.pagina.set(resposta.page);
          this.carregando.set(false);
        },
        error: () => {
          this.erro.set('Não foi possível carregar os pedidos da expedição.');
          this.carregando.set(false);
        },
      });
  }

  /** Digitar não dispara request por tecla — o debounce está no construtor. */
  onBuscaChange(valor: string): void {
    this.termoBusca.set(valor);
    this.busca$.next();
  }

  /** Trocar o período recarrega na hora: é um clique no calendário, não digitação. */
  onPeriodoChange(): void {
    this.carregar(1);
  }

  irParaPagina(pagina: number): void {
    if (pagina < 1 || pagina > this.totalPaginas() || pagina === this.pagina()) return;
    this.carregar(pagina);
  }

  limparFiltros(): void {
    this.situacao.set('todos');
    this.operadorId.set('');
    this.empresaId.set('');
    this.somenteMeus.set(false);
    this.statusPedido.set([]);
    this.termoBusca.set('');
    this.dataInicio.set(primeiroDiaDoMes());
    this.dataFim.set(hoje());
    this.carregar(1);
  }

  // ---------------------------------------------------------------------
  // Preferências da tela (localStorage, por usuário)
  //
  // Toda leitura é blindada: preferência corrompida, de um formato antigo ou
  // de um navegador que bloqueia storage vira o padrão da tela, nunca um erro
  // que impede a listagem de abrir. Filtro salvo não vale o risco de a
  // expedição não carregar.
  // ---------------------------------------------------------------------

  /** `<prefixo>_<preferência>_<id do usuário>`.
   *
   *  Sem usuário logado (a tela não abre assim, mas o signal é inicializado
   *  antes de qualquer garantia disso) cai em `anonimo`, um balde à parte que
   *  não se mistura com o de ninguém. */
  private chaveDaPreferencia(nome: string): string {
    return `${STORAGE_PREFIXO}_${nome}_${this.auth.usuario()?.id ?? 'anonimo'}`;
  }

  private gravar(nome: string, valor: unknown): void {
    try {
      localStorage.setItem(this.chaveDaPreferencia(nome), JSON.stringify(valor));
    } catch {
      // Storage cheio ou bloqueado pelo navegador. A tela continua funcionando
      // com o filtro em memória — ele só não sobrevive ao próximo F5.
    }
  }

  private ler(nome: string): unknown {
    try {
      const salvo = localStorage.getItem(this.chaveDaPreferencia(nome));
      return salvo === null ? undefined : JSON.parse(salvo);
    } catch {
      return undefined;
    }
  }

  private lerTexto(nome: string): string {
    const valor = this.ler(nome);
    return typeof valor === 'string' ? valor : '';
  }

  private lerBooleano(nome: string): boolean {
    return this.ler(nome) === true;
  }

  private lerLista(nome: string): string[] {
    const valor = this.ler(nome);
    return Array.isArray(valor) ? valor.filter((item) => typeof item === 'string') : [];
  }

  private lerPorPagina(): number {
    const valor = this.ler(PREF_POR_PAGINA);
    return typeof valor === 'number' && OPCOES_POR_PAGINA.includes(valor)
      ? valor
      : POR_PAGINA_PADRAO;
  }

  // ---------------------------------------------------------------------
  // Seleção e atribuição
  // ---------------------------------------------------------------------

  estaSelecionado(pedidoId: string): boolean {
    return this.selecionados().has(pedidoId);
  }

  alternarSelecao(pedidoId: string): void {
    const proximo = new Set(this.selecionados());
    if (!proximo.delete(pedidoId)) proximo.add(pedidoId);
    this.selecionados.set(proximo);
  }

  /** O checkbox do cabeçalho marca/desmarca o que está visível agora — não a
   *  fila inteira, que nem está carregada. */
  todosSelecionados = computed(() => {
    const visiveis = this.pedidos();
    return visiveis.length > 0 && visiveis.every((pedido) => this.estaSelecionado(pedido.pedidoId));
  });

  alternarTodos(): void {
    this.selecionados.set(
      this.todosSelecionados() ? new Set() : new Set(this.pedidos().map((p) => p.pedidoId)),
    );
  }

  limparSelecao(): void {
    this.selecionados.set(new Set());
  }

  abrirAtribuicao(tipo: TipoProcesso): void {
    this.atribuindo.set(tipo);
    this.operadorEscolhido.set(null);
    this.erroAtribuicao.set(null);
    this.operadoresDisponiveis.set([]);
    this.service.listarOperadores(tipo).subscribe({
      next: (lista) => this.operadoresDisponiveis.set(lista),
      error: () => this.erroAtribuicao.set('Não foi possível carregar os operadores.'),
    });
  }

  /** `usuarioId` nulo remove o responsável — "Sem responsável" é uma opção da
   *  lista, não um segundo botão. */
  confirmarAtribuicao(): void {
    const tipo = this.atribuindo();
    if (!tipo) return;
    this.atribuindoOcupado.set(true);
    this.erroAtribuicao.set(null);
    this.service.atribuir([...this.selecionados()], tipo, this.operadorEscolhido()).subscribe({
      next: () => {
        this.atribuindoOcupado.set(false);
        this.atribuindo.set(null);
        this.selecionados.set(new Set());
        this.carregar(this.pagina());
      },
      error: (falha) => {
        this.atribuindoOcupado.set(false);
        // O 409 do backend traz o motivo pronto (processo em andamento) — é
        // mais útil que uma mensagem genérica escrita aqui.
        this.erroAtribuicao.set(falha?.error?.detail ?? 'Não foi possível atribuir os pedidos.');
      },
    });
  }

  /** Tirar o responsável de UM pedido, direto na linha: é o caso comum
   *  (corrigir um engano) e não deveria exigir selecionar e abrir diálogo. */
  removerAtribuicao(pedidoId: string, tipo: TipoProcesso): void {
    this.service.atribuir([pedidoId], tipo, null).subscribe({
      next: () => this.carregar(this.pagina()),
      error: (falha) => this.erro.set(falha?.error?.detail ?? 'Não foi possível remover a atribuição.'),
    });
  }

  /** O responsável da etapa vigente — o mesmo critério de `etapaAtual`. */
  atribuicaoAtual(pedido: PedidoExpedicaoLista): Atribuicao | null {
    return this.etapaAtual(pedido).tipo === 'conferencia'
      ? pedido.atribuicaoConferencia
      : pedido.atribuicaoSeparacao;
  }

  /**
   * A etapa de que se fala agora. Enquanto a separação não fecha, é dela — o
   * pedido não pode ser conferido antes disso (regra de `iniciar_processo` no
   * backend). Depois, passa a ser a conferência, inclusive quando as duas já
   * fecharam: o último estado do pedido é o da conferência.
   *
   * A situação devolvida junto carrega quem está no processo e quantos itens
   * já saíram, então a coluna única não perde nada em relação às duas.
   */
  etapaAtual(pedido: PedidoExpedicaoLista): { tipo: TipoProcesso; situacao: SituacaoProcesso } {
    return pedido.separacao.status === 'finalizada'
      ? { tipo: 'conferencia', situacao: pedido.conferencia }
      : { tipo: 'separacao', situacao: pedido.separacao };
  }

  // ---------------------------------------------------------------------
  // Tempos: o relógio do galpão
  // ---------------------------------------------------------------------

  /**
   * Ciclo do pedido: da liberação no ERP até a conferência fechar — ou até
   * agora, se ainda não fechou. É o indicador que responde "quanto tempo o
   * pedido levou aqui dentro depois de liberado".
   */
  tempoCiclo(pedido: PedidoExpedicaoLista): Duracao | null {
    return duracaoEntre(pedido.liberadoEm, pedido.conferencia.dataFim);
  }

  /** Quando a etapa começou a contar: primeiro bipe, ou a abertura quando a
   *  etapa foi delegada e ninguém bipou. Ver `inicioDaEtapa`. */
  inicioEtapa(situacao: SituacaoProcesso): string | null {
    return inicioDaEtapa(situacao);
  }

  /** Tempo de uma etapa: do início até o fim (ou até agora). */
  tempoEtapa(situacao: SituacaoProcesso): Duracao | null {
    return duracaoEntre(inicioDaEtapa(situacao), situacao.dataFim);
  }

  /**
   * Status do ERP que fala mais alto que a etapa do galpão.
   *
   * Faturado e embarque acontecem DEPOIS que o pedido sai daqui — quando o ERP
   * carimba um dos dois, discutir "3 de 8 conferidos" é conversa velha, mesmo
   * que a etapa não tenha sido fechada no sistema. Por isso o badge substitui o
   * da situação em vez de conviver com ele.
   *
   * Chaves do catálogo `pedido_status`, as mesmas que chegam em
   * `pedido.statusPedido`.
   */
  private readonly STATUS_QUE_SUBSTITUI_A_ETAPA: Record<string, { rotulo: string; cor: string }> = {
    FAT: { rotulo: 'Faturado', cor: 'text-violet-700 bg-violet-50 dark:bg-violet-900/30' },
    EMB: { rotulo: 'Embarque', cor: 'text-sky-700 bg-sky-50 dark:bg-sky-900/30' },
  };

  /** O badge que ocupa o lugar do da etapa, ou null quando a etapa é que vale. */
  badgeStatusPedido(pedido: PedidoExpedicaoLista): { rotulo: string; cor: string } | null {
    return this.STATUS_QUE_SUBSTITUI_A_ETAPA[pedido.statusPedido] ?? null;
  }

  rotuloSituacao(situacao: SituacaoProcesso): string {
    if (situacao.status === 'nao_iniciada') return 'Não iniciada';
    if (situacao.status === 'finalizada') {
      return situacao.temDivergencia ? 'Finalizada c/ falta' : 'Finalizada';
    }
    return `${situacao.itensFinalizados} de ${situacao.itensTotal}`;
  }

  corSituacao(situacao: SituacaoProcesso): string {
    if (situacao.status === 'nao_iniciada') return 'text-gray-500 bg-gray-100 dark:bg-gray-800';
    if (situacao.status === 'finalizada') {
      return situacao.temDivergencia
        ? 'text-amber-700 bg-amber-50 dark:bg-amber-900/30'
        : 'text-emerald-700 bg-emerald-50 dark:bg-emerald-900/30';
    }
    return 'text-brand-700 bg-brand-50 dark:bg-brand-900/30';
  }
}
