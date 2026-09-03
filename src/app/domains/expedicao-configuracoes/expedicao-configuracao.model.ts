/** Os parâmetros do processo de expedição — um registro só, para o galpão
 * inteiro. Não tem `id` de propósito: a tela é um painel de parâmetros, não uma
 * listagem, e a linha existir ou não no banco é detalhe do backend. */
export interface ExpedicaoConfiguracao {
  /** "Permite conferir pedido com divergência de estoque e lote".
   * Desmarcado (padrão) é a trava ligada: pedido cujo lote não tem endereçado o
   * suficiente para o que foi vendido não entra em separação nem conferência. */
  permiteConferirComDivergencia: boolean;

  /** "Permite conferir pedido com endereço fora do múltiplo de venda".
   * Parâmetro separado do de cima porque é outro problema do galpão: aqui o
   * saldo existe, mas está quebrado numa prateleira (7 unidades soltas num
   * produto vendido em caixa de 12). */
  permiteConferirForaDoMultiploDeVenda: boolean;
}

/** O payload de gravação é o estado inteiro do painel — a tela manda todos os
 * parâmetros, não um campo por vez. */
export type ExpedicaoConfiguracaoPayload = ExpedicaoConfiguracao;
