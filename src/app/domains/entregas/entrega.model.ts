/**
 * Acompanhamento de entrega: o que aconteceu com a nota depois do
 * faturamento.
 *
 * Substitui a tela em Streamlit que lia o Oracle do ERP direto e juntava o
 * resultado com uma tabela de interações. Aqui os dados chegam prontos da
 * nossa API — o ERP alimenta por POST.
 */

export type StatusEntrega =
  | 'aguardando_embarque'
  | 'com_ocorrencia'
  | 'em_transito'
  | 'entrega_realizada'
  | 'recusada_no_ato'
  | 'retida_fiscalizacao'
  | 'devolucao_parcial';

/** Calculado pelo backend a cada leitura — depende de que dia é hoje. */
export type StatusPrazo =
  | 'entregue'
  | 'em_atraso'
  | 'no_prazo'
  | 'sem_mapa'
  | 'prazo_nao_definido';

/** Rótulo e cor de cada status. Fica no model, e não espalhado nos dois
 *  componentes, para a lista e o detalhe nunca mostrarem cores diferentes
 *  para o mesmo status. */
export const STATUS_ENTREGA: { valor: StatusEntrega; rotulo: string; cor: string; marcador: string }[] = [
  { valor: 'aguardando_embarque', rotulo: 'Aguardando embarque', cor: 'text-gray-600 bg-gray-100', marcador: 'bg-gray-400' },
  { valor: 'em_transito', rotulo: 'Em trânsito', cor: 'text-sky-700 bg-sky-50', marcador: 'bg-sky-500' },
  { valor: 'entrega_realizada', rotulo: 'Entrega realizada', cor: 'text-emerald-700 bg-emerald-50', marcador: 'bg-emerald-500' },
  { valor: 'com_ocorrencia', rotulo: 'Com ocorrência', cor: 'text-amber-700 bg-amber-50', marcador: 'bg-amber-500' },
  { valor: 'recusada_no_ato', rotulo: 'Recusada no ato da entrega', cor: 'text-red-700 bg-red-50', marcador: 'bg-red-500' },
  { valor: 'retida_fiscalizacao', rotulo: 'Retida para fiscalização', cor: 'text-purple-700 bg-purple-50', marcador: 'bg-purple-500' },
  { valor: 'devolucao_parcial', rotulo: 'Devolução parcial', cor: 'text-orange-700 bg-orange-50', marcador: 'bg-orange-500' },
];

export const STATUS_PRAZO: Record<StatusPrazo, { rotulo: string; cor: string }> = {
  entregue: { rotulo: 'Entregue', cor: 'text-emerald-700 bg-emerald-50' },
  no_prazo: { rotulo: 'No prazo', cor: 'text-sky-700 bg-sky-50' },
  em_atraso: { rotulo: 'Em atraso', cor: 'text-red-700 bg-red-50' },
  sem_mapa: { rotulo: 'Sem mapa de carga', cor: 'text-gray-500 bg-gray-100' },
  prazo_nao_definido: { rotulo: 'Prazo não definido', cor: 'text-gray-500 bg-gray-100' },
};

/** O status com que a nota NASCE, antes de qualquer interação. */
export const STATUS_NASCIMENTO: StatusEntrega = 'aguardando_embarque';

/** As opções que a pessoa ESCOLHE ao lançar ou corrigir uma interação.
 *
 *  É `STATUS_ENTREGA` menos o de nascimento: ninguém "lança" um aguardando
 *  embarque — é o estado de quem ainda não lançou nada, e a nota já mostra
 *  "Sem interação" nesse caso. A recusa de verdade é do backend
 *  (`StatusInteracao` em entrega_contrato.py); esconder aqui é só não oferecer
 *  o que seria recusado. */
export const STATUS_INTERACAO = STATUS_ENTREGA.filter((s) => s.valor !== STATUS_NASCIMENTO);

/** O que o formulário de interação aceita — o mesmo `StatusInteracao` do
 *  contrato do backend, escrito como subtração para os dois não divergirem
 *  quando um status novo entrar na lista. */
export type StatusInteracao = Exclude<StatusEntrega, typeof STATUS_NASCIMENTO>;

/** O status pré-selecionado quando não dá para aproveitar o atual. */
export const STATUS_INTERACAO_PADRAO: StatusInteracao = 'em_transito';

/** Converte um status qualquer no que o formulário pode ter selecionado.
 *
 *  Existe por dois caminhos reais: a nota que ainda não tem interação está em
 *  `aguardando_embarque`, e o dialog pré-seleciona o status atual dela; e as
 *  interações legadas migradas do Streamlit podem ter esse status, e o botão
 *  de corrigir carrega o valor do evento. Nos dois casos o `p-select` ficaria
 *  em branco, com um valor que a lista não contém. */
export function paraStatusEscolhivel(status: string): StatusInteracao {
  return STATUS_INTERACAO.some((s) => s.valor === status)
    ? (status as StatusInteracao)
    : STATUS_INTERACAO_PADRAO;
}

export function rotuloStatus(status: string): string {
  return STATUS_ENTREGA.find((s) => s.valor === status)?.rotulo ?? status;
}

/** O rótulo do estado ATUAL da nota, que não é a mesma coisa que o rótulo de um
 *  evento da timeline.
 *
 *  Sem nenhuma interação, a nota mostra "Sem interação" — e não "Aguardando
 *  embarque", que afirmaria algo que ninguém registrou. A condição é a
 *  CONTAGEM de interações, não o valor do status: existem notas antigas,
 *  migradas do sistema em Streamlit, cuja última interação de verdade tem
 *  status `aguardando_embarque`. Nessas o rótulo continua sendo o do evento,
 *  porque alguém realmente o lançou.
 *
 *  Na timeline o rótulo continua vindo de `rotuloStatus`: lá cada card É um
 *  evento, e o desses casos legados é "Aguardando embarque" mesmo. */
export function rotuloStatusDaNota(status: string, qtdInteracoes: number): string {
  return qtdInteracoes === 0 ? 'Sem interação' : rotuloStatus(status);
}

export function corStatusDaNota(status: string, qtdInteracoes: number): string {
  return qtdInteracoes === 0 ? 'text-gray-500 bg-gray-100' : corStatus(status);
}

export function corStatus(status: string): string {
  return STATUS_ENTREGA.find((s) => s.valor === status)?.cor ?? 'text-gray-500 bg-gray-100';
}

export function marcadorStatus(status: string): string {
  return STATUS_ENTREGA.find((s) => s.valor === status)?.marcador ?? 'bg-gray-400';
}

/** Rótulo de cada tipo de nota. A classificação chega do ERP como slug
 *  (`devolucao_cliente`), que é o certo para filtrar e comparar — mas ninguém
 *  lê "devolucao_cliente" numa coluna de tabela.
 *
 *  O fallback devolve o próprio valor: o ERP pode criar um tipo novo antes de
 *  alguém mexer aqui, e mostrar o slug cru é melhor que mostrar célula vazia. */
export const TIPO_NOTA: Record<string, string> = {
  venda: 'Venda',
  bonificacao: 'Bonificação',
  devolucao_cliente: 'Devolução',
  complementar: 'Complementar',
  perda: 'Perda',
  outros: 'Outros',
};

export function rotuloTipoNota(tipo: string): string {
  return TIPO_NOTA[tipo] ?? tipo;
}

export interface InteracaoEntrega {
  id: string;
  status: StatusEntrega;
  observacao: string;
  usuarioId: string;
  usuarioNome: string;
  /** O instante do EVENTO — coluna própria no banco, não um campo `sync*`.
   *  É por ele que a timeline ordena e mostra "há quanto tempo". Editar a
   *  interação não altera esta data. */
  dataInteracao: string;
  editadoEm: string | null;
  editadoPorNome: string | null;
}

/** O que a listagem devolve — sem itens e sem a timeline. */
export interface EntregaNotaResumo {
  id: string;
  empresaId: string;
  /** Apelido da empresa emissora ("Matriz", "BSB"), caindo no nome fantasia
   *  quando não há apelido. É o que a coluna "Empresa" mostra: num galpão que
   *  atende várias filiais, saber de qual é a entrega é a primeira pergunta. */
  empresaApelido: string | null;
  numeroNota: string;
  serie: string;
  pedido: string;
  tipoNota: string;
  dataNota: string | null;
  situacao: string | null;
  valorTotal: number;
  clienteNome: string;
  clienteCidade: string | null;
  clienteUf: string | null;
  vendedorId: string | null;
  vendedorNome: string | null;
  transportadoraNome: string | null;
  termolabil: boolean;
  numeroMapa: string | null;
  dataMapa: string | null;
  prazoDias: number | null;
  dataPrevistaEntrega: string | null;
  statusAtual: StatusEntrega;
  statusPrazo: StatusPrazo;
  dataEntregaRealizada: string | null;
  qtdInteracoes: number;
}

export interface ItemEntregaNota {
  id: string;
  numeroItem: number;
  produtoCodigo: string;
  produtoDescricao: string;
  marcaNome: string | null;
  quantidade: number;
  precoUnitario: number;
  valorTotal: number;
  lote: string | null;
  validade: string | null;
  quantidadeDevolvida: number;
  observacao: string | null;
}

/** Uma nota que devolve a nota aberta na tela. Resumo curto de propósito: a
 *  seção responde "o que voltou desta entrega?", e quem quiser o resto clica e
 *  abre a nota de devolução, que é uma nota como outra qualquer nesta tela. */
export interface NotaDevolucao {
  id: string;
  numeroNota: string;
  serie: string;
  dataNota: string | null;
  tipoNota: string;
  situacao: string | null;
  valorTotal: number;
  chaveAcessoNota: string | null;
  statusAtual: StatusEntrega;
  qtdInteracoes: number;
}

export interface EntregaNota extends EntregaNotaResumo {
  clienteCodigo: string | null;
  /** Chave de acesso da NF-e desta nota, em snapshot vindo do ERP. Só no
   *  detalhe: 44 dígitos não cabem numa coluna da listagem, e quem precisa dela
   *  está olhando uma nota específica para cruzar com o fiscal. */
  chaveAcessoNota: string | null;
  /** Chave da nota que ESTA referencia — é o que amarra uma devolução ou uma
   *  complementar ao documento de origem. */
  chaveAcessoReferenciada: string | null;
  entregaId: string | null;
  motorista: string | null;
  placaVeiculo: string | null;
  sistemaOrigemId: string | null;
  itens: ItemEntregaNota[];
  interacoes: InteracaoEntrega[];
  /** As notas que DEVOLVEM esta, achadas pela chave: são aquelas cuja
   *  `chaveAcessoReferenciada` é igual à `chaveAcessoNota` desta. Vazio quando
   *  não houve devolução — e também quando esta nota ainda não tem chave. */
  notasDevolucao: NotaDevolucao[];
}

export interface EntregaListaPaginada {
  items: EntregaNotaResumo[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}

/** Os campos do painel de filtros, um por autocomplete.
 *
 *  A ordem aqui é a ordem em que eles aparecem na tela — é uma lista só, e não
 *  uma constante para a ordem e outra para os rótulos, porque duas listas
 *  paralelas divergem em silêncio no dia em que alguém adiciona um campo.
 *
 *  `chave` é o nome do query param que a API espera (camelCase) E o valor que
 *  vai em `?campo=` ao pedir as sugestões. É esse casamento que faz o valor
 *  escolhido no autocomplete ser aceito pelo filtro — uma chave só, os dois
 *  lados. */
export interface CampoFiltro {
  chave: keyof CamposDoPainel;
  rotulo: string;
}

/** Só os campos do painel — de fora ficam `q`, `statusPrazo` e o período, que
 *  não são autocompletes. Existe para o tipo de `CampoFiltro.chave` não
 *  aceitar 'dataInicio', que quebraria em tempo de execução. */
type CamposDoPainel = Omit<FiltrosEntrega, 'q' | 'statusPrazo' | 'dataInicio' | 'dataFim'>;

export const CAMPOS_FILTRO: CampoFiltro[] = [
  { chave: 'empresa', rotulo: 'Empresa' },
  { chave: 'tipoNota', rotulo: 'Tipo de nota' },
  { chave: 'pedido', rotulo: 'Pedido' },
  { chave: 'numeroNota', rotulo: 'Número da nota' },
  { chave: 'dataNota', rotulo: 'Data da nota' },
  { chave: 'cliente', rotulo: 'Cliente' },
  { chave: 'uf', rotulo: 'UF' },
  { chave: 'cidade', rotulo: 'Cidade' },
  { chave: 'situacao', rotulo: 'Situação' },
  { chave: 'vendedor', rotulo: 'Vendedor' },
  { chave: 'transportadora', rotulo: 'Transportadora' },
  { chave: 'status', rotulo: 'Status da entrega' },
  { chave: 'numeroMapa', rotulo: 'Mapa de carga' },
  { chave: 'dataMapa', rotulo: 'Data do mapa' },
  { chave: 'notaDevolvida', rotulo: 'Nota devolvida' },
  { chave: 'produto', rotulo: 'Produto' },
  { chave: 'marca', rotulo: 'Marca' },
  { chave: 'lote', rotulo: 'Lote' },
  { chave: 'quantidade', rotulo: 'Quantidade' },
];

/** As sugestões de UM campo do painel, vindas de `GET /entregas/opcoes-filtros`.
 *
 *  Um endpoint só para os 19 campos: `campo` diz qual, `termo` recorta. A tela
 *  não guarda mais o conjunto inteiro de valores — ele chegava a centenas por
 *  campo num mês real, e crescia com o período escolhido.
 *
 *  Os valores vêm sempre como string: o autocomplete é um campo de texto e o
 *  query param é texto. Quem converte de volta para data ou número é o backend,
 *  no contrato de entrada. */
export interface SugestoesFiltro {
  campo: string;
  valores: string[];
  /** Havia mais valores do que o teto do servidor — a tela pede para refinar
   *  em vez de deixar a pessoa achar que aquilo é tudo que existe. */
  truncado: boolean;
}

/** Todos resolvidos no servidor — filtrar no navegador recortaria só a página
 *  carregada, e o total do rodapé deixaria de bater.
 *
 *  Cada campo do painel é uma LISTA: vários valores no mesmo campo é OU
 *  (transportadora A ou B), campos diferentes é E. Lista vazia = não filtra.
 *
 *  `q`, `statusPrazo` e o período ficam de fora do painel de propósito: a
 *  busca é texto livre, `statusPrazo` são as abas (escolha exclusiva) e o
 *  período é o recorte que DEFINE quais valores o painel oferece. */
export interface FiltrosEntrega {
  q: string;
  statusPrazo: StatusPrazo | '';
  /** Período pela DATA DA NOTA. */
  dataInicio: string;
  dataFim: string;
  empresa: string[];
  tipoNota: string[];
  pedido: string[];
  numeroNota: string[];
  dataNota: string[];
  cliente: string[];
  uf: string[];
  cidade: string[];
  situacao: string[];
  vendedor: string[];
  transportadora: string[];
  status: string[];
  numeroMapa: string[];
  dataMapa: string[];
  /** O NÚMERO da nota que esta devolve, extraído das 9 posições a partir da
   *  26ª da chave referenciada — que é onde o layout da NF-e guarda o número
   *  do documento. Ninguém procura pela chave de 44 dígitos; procura pelo
   *  número. Quem extrai é o backend. */
  notaDevolvida: string[];
  produto: string[];
  marca: string[];
  lote: string[];
  /** String, e não number: o valor vem do autocomplete como texto e volta como
   *  query param como texto. Quem converte para decimal é o backend. */
  quantidade: string[];
}

export const FILTROS_ENTREGA_VAZIOS: FiltrosEntrega = {
  q: '',
  statusPrazo: '',
  dataInicio: '',
  dataFim: '',
  empresa: [],
  tipoNota: [],
  pedido: [],
  numeroNota: [],
  dataNota: [],
  cliente: [],
  uf: [],
  cidade: [],
  situacao: [],
  vendedor: [],
  transportadora: [],
  status: [],
  numeroMapa: [],
  dataMapa: [],
  notaDevolvida: [],
  produto: [],
  marca: [],
  lote: [],
  quantidade: [],
};

/** Limpa o painel inteiro, PRESERVANDO o período.
 *
 *  A data fica de fora porque ela não é um filtro como os outros: é o recorte
 *  que define quais valores existem para escolher. Zerar o período junto
 *  levaria a tela para o padrão e recarregaria opções de outro intervalo — o
 *  contrário do que quem clica em "Limpar filtros" espera, que é continuar
 *  olhando o mesmo período sem nenhum recorte por cima. */
export function limparMantendoPeriodo(filtros: FiltrosEntrega): FiltrosEntrega {
  return {
    ...FILTROS_ENTREGA_VAZIOS,
    dataInicio: filtros.dataInicio,
    dataFim: filtros.dataFim,
  };
}

/** Se há algo a limpar. A aba (`statusPrazo`) conta, o período não — ele nunca
 *  é limpo, então oferecer o botão por causa dele seria oferecer um clique que
 *  não muda nada. */
export function temFiltroAplicado(filtros: FiltrosEntrega): boolean {
  if (filtros.q.trim() || filtros.statusPrazo) return true;
  return CAMPOS_FILTRO.some((campo) => filtros[campo.chave].length > 0);
}


// ---------------------------------------------------------------------------
// Persistência da escolha de filtros, POR USUÁRIO
//
// Quem monta um recorte de doze campos e dá F5 não quer montá-lo de novo. O
// que fica guardado é a ESCOLHA (quais valores), nunca as opções nem as notas
// — dado de negócio se busca na API a cada carga, senão a tela mostraria
// entrega que já mudou de status.
//
// A chave leva o id do usuário porque o navegador do galpão é compartilhado:
// sem isso, o operador do turno da noite abriria a tela com o recorte do
// turno da tarde e acharia que sumiu nota.
// ---------------------------------------------------------------------------

const PREFIXO_FILTROS = 'ellotec.entregas.filtros';

/** "2026-08-28" a partir de uma data, no formato que `<input type="date">` lê.
 *
 *  Montada dos componentes LOCAIS da data, e não com `toISOString()`: aquele
 *  converte para UTC, e a partir das 21h de Brasília ele devolveria o dia
 *  seguinte — a tela abriria mostrando um período que ainda não começou. */
function paraInputDate(data: Date): string {
  const mes = String(data.getMonth() + 1).padStart(2, '0');
  const dia = String(data.getDate()).padStart(2, '0');
  return `${data.getFullYear()}-${mes}-${dia}`;
}

/** O período padrão da tela: do dia 1º até hoje.
 *
 *  É o recorte que responde "o que é deste mês?" sem ninguém digitar nada, e é
 *  o mesmo padrão da listagem da expedição. Sem ele a tela abriria pedindo a
 *  base inteira — centenas de milhares de notas para descobrir o que aconteceu
 *  esta semana. */
export function periodoDoMesAtual(): { dataInicio: string; dataFim: string } {
  const hoje = new Date();
  return {
    dataInicio: paraInputDate(new Date(hoje.getFullYear(), hoje.getMonth(), 1)),
    dataFim: paraInputDate(hoje),
  };
}

export function chaveFiltrosSalvos(usuarioId: string | null): string {
  return `${PREFIXO_FILTROS}.${usuarioId ?? 'anonimo'}`;
}

/** Lê o recorte salvo, ou os filtros vazios quando não há nada guardado.
 *
 *  Toda leitura passa por `FILTROS_ENTREGA_VAZIOS` como base: o que estiver
 *  gravado de uma versão anterior da tela (um campo que não existe mais, um
 *  campo novo que ainda não estava lá) não quebra nem falta. Sem isso, subir
 *  uma versão com um filtro novo deixaria `undefined` num campo que a tela
 *  espera array, e o `for` do service estouraria na primeira carga. */
export function lerFiltrosSalvos(usuarioId: string | null): FiltrosEntrega {
  // O mês atual entra na BASE, não por cima do que foi salvo: quem nunca mexeu
  // no período abre no mês corrente, e quem escolheu outro intervalo continua
  // nele depois do F5. É a diferença entre um padrão e uma imposição.
  const padrao = periodoDoMesAtual();
  const base: FiltrosEntrega = { ...FILTROS_ENTREGA_VAZIOS, ...padrao };
  try {
    const bruto = localStorage.getItem(chaveFiltrosSalvos(usuarioId));
    if (!bruto) return base;
    const salvo = JSON.parse(bruto) as Partial<FiltrosEntrega>;
    return {
      ...base,
      ...salvo,
      // Data vazia NÃO sobrescreve o padrão. Sem esta linha, um recorte salvo
      // antes de o padrão existir (ou de alguém ter apagado os campos na tela)
      // ressuscitaria `''` a cada carga e a data nunca mais apareceria — o
      // usuário não tem como sair disso, porque limpar filtros preserva o
      // período. Campo de data em branco é ausência de escolha, não escolha.
      dataInicio: salvo.dataInicio || padrao.dataInicio,
      dataFim: salvo.dataFim || padrao.dataFim,
    };
  } catch {
    // localStorage indisponível (janela anônima, site data bloqueado) ou JSON
    // corrompido. Abrir no mês atual é sempre melhor que não abrir.
    return base;
  }
}

export function salvarFiltros(usuarioId: string | null, filtros: FiltrosEntrega): void {
  try {
    localStorage.setItem(chaveFiltrosSalvos(usuarioId), JSON.stringify(filtros));
  } catch {
    // Não conseguir guardar a preferência não pode impedir de usar a tela.
  }
}

export interface InteracaoFormulario {
  status: StatusEntrega;
  observacao: string;
}
