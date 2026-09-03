import type {
  NoArvorePermissao,
  PermissaoKey,
} from '../permissions/permission.model';

/**
 * FONTE ÚNICA da estrutura de módulos da aplicação.
 *
 * Antes existiam duas listas paralelas que precisavam ser editadas juntas e
 * divergiam em silêncio: `MENU_PRINCIPAL` (menu lateral) e `ARVORE_PERMISSOES`
 * (checkboxes do formulário de usuário). Agora as duas são DERIVADAS de
 * `ESTRUTURA_APP`, mais abaixo neste arquivo — adicionar um módulo novo é
 * editar um lugar só.
 *
 * A hierarquia tem 4 níveis:
 *
 *   seção ("Aplicações")        → só no menu, cabeçalho fixo, não colapsa
 *     grupo ("Cadastros")       → acordeão no menu, nó-pai na árvore
 *       módulo ("Produtos")     → item clicável no menu, nó na árvore
 *         ação ("Incluir")      → só na árvore, é a permissão em si
 *
 * O import de `PermissaoKey` é `import type` de propósito: o tipo é apagado na
 * compilação, então este arquivo não cria dependência de runtime com
 * `permission.model.ts`. A direção é sempre navegacao → permissions.
 */

/** Uma ação nomeada de um módulo. Vira uma folha na árvore de permissões. */
export interface AcaoModulo {
  label: string;
  chave: PermissaoKey;
}

/** Um módulo do sistema — tipicamente uma tela com rota própria. */
export interface ModuloApp {
  rotulo: string;
  icone: string; // nome lógico, resolvido em `app-icon`
  rota?: string; // ausente = item decorativo, não navega
  badge?: string;
  novo?: boolean;
  /**
   * Ações que o módulo expõe na matriz de permissões. Por convenção a
   * PRIMEIRA é a de acesso (`dominio.acessar`) — é ela que o menu usa para
   * decidir se o item aparece. Ausente/vazio = módulo sem permissão própria
   * (ex: Início), sempre visível e fora da árvore de permissões.
   */
  acoes?: AcaoModulo[];
}

/**
 * Agrupamento dentro de uma seção ("Cadastros", "WMS", ...).
 *
 * Grupo COM título vira um acordeão no menu (cabeçalho clicável que abre e
 * fecha) e um nó-pai na árvore de permissões. Grupo SEM título tem os módulos
 * soltos direto sob o cabeçalho da seção — é o caso do Início, que não é
 * módulo de negócio nem tem permissão própria.
 */
export interface GrupoApp {
  titulo?: string;
  modulos: ModuloApp[];
}

/**
 * Seção do menu ("Dashboards", "Aplicações"). É só apresentação: cabeçalho
 * fixo, sem clique, e não aparece na árvore de permissões — quem agrupa
 * permissão é o grupo, não a seção.
 */
export interface SecaoApp {
  titulo: string;
  subtitulo?: string;
  grupos: GrupoApp[];
}

export const ESTRUTURA_APP: SecaoApp[] = [
  {
    titulo: 'Dashboards',
    subtitulo: 'Visão geral do negócio',
    grupos: [{ modulos: [{ rotulo: 'Início', icone: 'layout', rota: '/' }] }],
  },
  {
    titulo: 'Aplicações',
    subtitulo: 'Módulos de gestão',
    grupos: [
      {
        titulo: 'Cadastros',
        modulos: [
          {
            rotulo: 'Produtos',
            icone: 'box',
            rota: '/produtos',
            acoes: [
              { label: 'Acessar listagem', chave: 'produtos.acessar' },
              { label: 'Incluir', chave: 'produtos.gravar.incluir' },
              { label: 'Editar', chave: 'produtos.gravar.editar' },
              { label: 'Apagar', chave: 'produtos.apagar' },
              { label: 'Vincular códigos de barras da ANVISA', chave: 'produtos.codigo_barras.vincular_anvisa' },
            ],
          },
          {
            rotulo: 'Clientes',
            icone: 'contacts',
            rota: '/clientes',
            acoes: [
              { label: 'Acessar listagem', chave: 'clientes.acessar' },
              { label: 'Incluir', chave: 'clientes.gravar.incluir' },
              { label: 'Editar', chave: 'clientes.gravar.editar' },
              { label: 'Apagar', chave: 'clientes.apagar' },
            ],
          },
          {
            rotulo: 'Marcas',
            icone: 'box',
            rota: '/marcas',
            acoes: [
              { label: 'Acessar listagem', chave: 'marcas.acessar' },
              { label: 'Incluir', chave: 'marcas.gravar.incluir' },
              { label: 'Editar', chave: 'marcas.gravar.editar' },
              { label: 'Apagar', chave: 'marcas.apagar' },
            ],
          },
          {
            rotulo: 'Cidades',
            icone: 'contacts',
            rota: '/cidades',
            acoes: [
              { label: 'Acessar listagem', chave: 'cidades.acessar' },
              { label: 'Incluir', chave: 'cidades.gravar.incluir' },
              { label: 'Editar', chave: 'cidades.gravar.editar' },
              { label: 'Apagar', chave: 'cidades.apagar' },
            ],
          },
          {
            rotulo: 'Empresas',
            icone: 'contacts',
            rota: '/empresas',
            acoes: [
              { label: 'Acessar listagem', chave: 'empresas.acessar' },
              { label: 'Incluir', chave: 'empresas.gravar.incluir' },
              { label: 'Editar', chave: 'empresas.gravar.editar' },
              { label: 'Apagar', chave: 'empresas.apagar' },
            ],
          },
        ],
      },
      {
        titulo: 'Vendas',
        modulos: [
          {
            rotulo: 'Pedidos',
            icone: 'file-text',
            rota: '/pedidos',
            acoes: [
              { label: 'Acessar listagem', chave: 'pedidos.acessar' },
              { label: 'Incluir', chave: 'pedidos.gravar.incluir' },
              { label: 'Editar', chave: 'pedidos.gravar.editar' },
              { label: 'Apagar', chave: 'pedidos.apagar' },
            ],
          },
        ],
      },
      {
        titulo: 'Fiscal',
        modulos: [
          {
            // Um item só, e não "Notas Entradas" + "Notas Saídas": entrada e
            // saída são o mesmo documento visto dos dois lados, guardado na
            // mesma tabela e distinguido por `tipo_operacao`. A separação é
            // uma aba dentro da tela, espelhando o modelo de dados em vez de
            // inventar uma divisão que o banco não faz.
            rotulo: 'Notas Fiscais',
            icone: 'file-text',
            rota: '/notas-fiscais',
            acoes: [
              { label: 'Acessar listagem', chave: 'notas_fiscais.acessar' },
              { label: 'Incluir', chave: 'notas_fiscais.gravar.incluir' },
              { label: 'Editar', chave: 'notas_fiscais.gravar.editar' },
              { label: 'Apagar', chave: 'notas_fiscais.apagar' },
            ],
          },
        ],
      },
      {
        titulo: 'WMS',
        modulos: [
          {
            // O acompanhamento pós-faturamento: onde a nota está, quanto tempo
            // falta para vencer o prazo e o histórico de interações. Substitui
            // a tela em Streamlit que lia o Oracle do ERP direto.
            rotulo: 'Gestão de Entregas',
            icone: 'truck',
            rota: '/entregas',
            acoes: [
              { label: 'Acessar listagem', chave: 'entregas.acessar' },
              // Sem esta, o vendedor enxerga só as notas em que ele é o
              // vendedor — é o `visualiza_vendas_proprias` do sistema antigo.
              { label: 'Ver entregas de todos os vendedores', chave: 'entregas.ver_todas' },
              { label: 'Registrar e corrigir interação', chave: 'entregas.interacao.registrar' },
              { label: 'Remover interação', chave: 'entregas.interacao.apagar' },
            ],
          },
          {
            // Consulta do saldo, por produto e por lote. Só `acessar` aparece
            // aqui: quem grava estoque é a integração do ERP, e a chave de
            // gravação fica fora da árvore pelo mesmo motivo de
            // `entregas.integrar` — não é permissão de gente, é de integração.
            rotulo: 'Estoque',
            icone: 'box',
            rota: '/estoque',
            acoes: [{ label: 'Consultar saldo e lotes', chave: 'estoque.acessar' }],
          },
          {
            // Os lugares do galpão. Cadastro que uma PESSOA mexe (montou uma
            // prateleira nova, mudou a etiqueta), então tem as quatro ações.
            rotulo: 'Endereçamento',
            icone: 'scrumboard',
            rota: '/enderecamento',
            acoes: [
              { label: 'Acessar listagem', chave: 'enderecamento.acessar' },
              { label: 'Incluir', chave: 'enderecamento.gravar.incluir' },
              { label: 'Editar', chave: 'enderecamento.gravar.editar' },
              { label: 'Apagar', chave: 'enderecamento.apagar' },
            ],
          },
          {
            rotulo: 'Expedição',
            icone: 'truck',
            rota: '/expedicao',
            acoes: [
              { label: 'Acessar listagem', chave: 'expedicao.acessar' },
              { label: 'Executar separação', chave: 'expedicao.separacao.executar' },
              { label: 'Executar conferência', chave: 'expedicao.conferencia.executar' },
              { label: 'Resetar separação/conferência', chave: 'expedicao.resetar' },
              { label: 'Atribuir pedidos a operadores', chave: 'expedicao.atribuir' },
              { label: 'Iniciar/finalizar em nome do operador', chave: 'expedicao.delegar' },
              {
                label: 'Liberar pedido com endereçamento inconsistente',
                chave: 'expedicao.enderecamento.liberar',
              },
              {
                label: 'Finalizar pedido no sistema de origem',
                chave: 'expedicao.finalizar_origem',
              },
            ],
          },
          {
            // Domínio que ESCREVE no ERP (GESTCOM). A tela é uma casca por
            // enquanto: a única operação existente — finalizar o pedido depois
            // da conferência — é usada de dentro da expedição, no fluxo do
            // operador. O módulo está aqui para o domínio ter menu, rota e
            // chave desde o começo, e para as próximas operações do ERP terem
            // onde morar. Ver backend/ARCHITECTURE.md → "Domínio que ESCREVE
            // no sistema de origem".
            rotulo: 'Sistema de origem',
            icone: 'rotate',
            rota: '/sistema-origem',
            acoes: [{ label: 'Acessar', chave: 'sistema_origem.acessar' }],
          },
        ],
      },
      {
        titulo: 'Inteligência de Mercado',
        modulos: [
          {
            // Domínio de CONSULTA a banco externo: os dados vêm do OuroWeb
            // (SQL Server do Bionexo), somente leitura, e nada é gravado. Por
            // isso a única ação é "acessar" — não existe incluir, editar nem
            // apagar. Ver backend/ARCHITECTURE.md → "Domínio de consulta a
            // banco externo".
            rotulo: 'Cotações',
            icone: 'chart',
            rota: '/cotacoes',
            acoes: [{ label: 'Acessar listagem', chave: 'cotacoes.acessar' }],
          },
        ],
      },
      {
        titulo: 'Administração',
        modulos: [
          {
            rotulo: 'Usuários',
            icone: 'users',
            rota: '/usuarios',
            acoes: [
              { label: 'Acessar listagem', chave: 'usuarios.acessar' },
              { label: 'Incluir', chave: 'usuarios.gravar.incluir' },
              { label: 'Editar', chave: 'usuarios.gravar.editar' },
              { label: 'Apagar', chave: 'usuarios.apagar' },
            ],
          },
        ],
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Derivação 1: menu lateral
// ---------------------------------------------------------------------------

export interface ItemMenu {
  rotulo: string;
  icone: string;
  rota?: string;
  permissao?: PermissaoKey; // se presente, item só aparece se o usuário tiver a chave
  badge?: string;
  novo?: boolean;
}

export interface GrupoMenu {
  titulo?: string;
  itens: ItemMenu[];
}

export interface SecaoMenu {
  titulo: string;
  subtitulo?: string;
  grupos: GrupoMenu[];
}

export const MENU_PRINCIPAL: SecaoMenu[] = ESTRUTURA_APP.map((secao) => ({
  titulo: secao.titulo,
  subtitulo: secao.subtitulo,
  grupos: secao.grupos.map((grupo) => ({
    titulo: grupo.titulo,
    itens: grupo.modulos.map((modulo) => ({
      rotulo: modulo.rotulo,
      icone: modulo.icone,
      rota: modulo.rota,
      permissao: modulo.acoes?.[0]?.chave,
      badge: modulo.badge,
      novo: modulo.novo,
    })),
  })),
}));

// ---------------------------------------------------------------------------
// Derivação 2: árvore de permissões (checkboxes do formulário de usuário)
// ---------------------------------------------------------------------------

/**
 * Árvore de 3 níveis: grupo → módulo → ação. A seção não vira nível aqui (é
 * só apresentação do menu), e grupos sem título ou sem nenhuma ação abaixo
 * (ex: Início) ficam de fora — não há o que marcar neles.
 */
export const ARVORE_PERMISSOES: NoArvorePermissao[] = ESTRUTURA_APP.flatMap((secao) =>
  secao.grupos.flatMap((grupo) => {
    const modulos = grupo.modulos.filter((modulo) => modulo.acoes?.length);
    if (!grupo.titulo || modulos.length === 0) return [];

    return [
      {
        label: grupo.titulo,
        filhos: modulos.map((modulo) => ({
          label: modulo.rotulo,
          filhos: modulo.acoes!.map((acao) => ({ label: acao.label, chave: acao.chave })),
        })),
      },
    ];
  }),
);

/** Achata a árvore em uma lista de todas as chaves existentes — usado pra
 * validar que nenhuma chave marcada esteja fora do catálogo conhecido. */
export function todasAsChaves(nos: NoArvorePermissao[] = ARVORE_PERMISSOES): PermissaoKey[] {
  return nos.flatMap((no) => [...(no.chave ? [no.chave] : []), ...todasAsChaves(no.filhos ?? [])]);
}
