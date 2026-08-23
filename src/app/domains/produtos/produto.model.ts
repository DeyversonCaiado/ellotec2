export interface Produto {
  id: string;
  codigo: string;
  descricao: string;
  unidade: string;
  /** O código que vem do ERP e sai impresso na nota. É um só, porque no ERP
   *  (fat_produtos.CODIGO_BARRA) é um só. */
  codigoBarraNotas: string | null;
  /** Os códigos que o coletor lê no galpão — caixa de fabricante, de
   *  distribuidor, reembalagem. Cadastrados só aqui, sem par no ERP. A lista
   *  inteira vai e volta a cada gravação: é o cadastro final do produto. */
  codigosBarrasLogistica: string[];
  /** DUN-14 (GTIN-14) da caixa fechada. Último que a bipagem tenta, quando a
   *  leitura não bate com o código da nota nem com os de logística. */
  dun14: string | null;
  /** Unidades por embalagem de venda. Cada leitura no coletor vale essa
   *  quantidade — 1 significa produto vendido na unidade. */
  quantidadeMultiplaVenda: number;
  /** Registro do produto na ANVISA. Texto, não número: tem zeros à esquerda que
   *  fazem parte dele, e há produto isento ou em renovação, cujo campo o ERP
   *  preenche com texto livre. Nulo em item que não é produto de saúde. */
  registroAnvisa: string | null;
  marcaId: string;
  marcaNome: string;
  sistemaOrigemId: string | null;
  ativo: boolean;
  criadoEm: string;
}

export type ProdutoFormulario = Omit<Produto, 'id' | 'criadoEm' | 'marcaNome'>;

/** Formato de resposta do GET /produtos (paginado). */
export interface ProdutoListaPaginada {
  items: Produto[];
  total: number;
  page: number;
  perPage: number;
  sort: string;
  sortType: string;
}

/** Um código da CMED que já pertence a outro produto — o que impede o vínculo. */
export interface ConflitoCodigoBarras {
  codigo: string;
  produtoId: string;
  produtoCodigo: string;
  produtoDescricao: string;
}

/**
 * Resultado de "verificar ANVISA". Vem sempre com HTTP 200, inclusive quando
 * nada foi vinculado: não vincular não é erro de requisição, é uma resposta de
 * negócio que a tela precisa mostrar por extenso.
 */
export interface VincularAnvisaResposta {
  situacao:
    | 'vinculado'
    | 'sem_registro'
    | 'registro_nao_encontrado'
    | 'codigo_nao_confere'
    | 'conflito';
  mensagem: string;
  codigosVinculados: string[];
  conflitos: ConflitoCodigoBarras[];
}
