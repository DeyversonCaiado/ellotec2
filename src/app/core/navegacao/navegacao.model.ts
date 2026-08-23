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
        titulo: 'WMS',
        modulos: [
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
            ],
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
