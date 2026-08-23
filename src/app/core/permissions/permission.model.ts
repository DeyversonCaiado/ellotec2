/**
 * Cada permissão do sistema é uma string opaca e única do tipo
 * `PermissaoKey`, no padrão `dominio.contexto.acao`. Não existe mais o par
 * (DominioId, Acao) com ações fixas de CRUD — qualquer funcionalidade de
 * negócio, seja ela CRUD ou não, vira uma chave nomeada aqui.
 *
 * Ao adicionar um domínio novo, adicione as chaves dele aqui E no backend
 * (`core/permissions/permission_model.py`) — os dois lados precisam ficar
 * em sync manualmente, não existe geração automática entre eles.
 */
export type PermissaoKey =
  // --- Usuários ---
  | 'usuarios.acessar'
  | 'usuarios.gravar.incluir'
  | 'usuarios.gravar.editar'
  | 'usuarios.apagar'
  // --- Clientes ---
  | 'clientes.acessar'
  | 'clientes.gravar.incluir'
  | 'clientes.gravar.editar'
  | 'clientes.apagar'
  // --- Produtos ---
  | 'produtos.acessar'
  | 'produtos.gravar.incluir'
  | 'produtos.gravar.editar'
  | 'produtos.apagar'
  | 'produtos.codigo_barras.vincular_anvisa'
  // --- Pedidos ---
  | 'pedidos.acessar'
  | 'pedidos.gravar.incluir'
  | 'pedidos.gravar.editar'
  | 'pedidos.apagar'
  // --- Cidades ---
  | 'cidades.acessar'
  | 'cidades.gravar.incluir'
  | 'cidades.gravar.editar'
  | 'cidades.apagar'
  // --- Marcas ---
  | 'marcas.acessar'
  | 'marcas.gravar.incluir'
  | 'marcas.gravar.editar'
  | 'marcas.apagar'
  // --- Empresas ---
  | 'empresas.acessar'
  | 'empresas.gravar.incluir'
  | 'empresas.gravar.editar'
  | 'empresas.apagar'
  // --- Expedição (separação e conferência) ---
  | 'expedicao.acessar'
  | 'expedicao.separacao.executar'
  | 'expedicao.conferencia.executar'
  | 'expedicao.resetar'
  | 'expedicao.atribuir';

/** O que o usuário carrega — simples e verificável em O(1).
 * Serializado como array de strings no JSON (backend → front) e convertido
 * para Set na hidratação da sessão em AuthService. */
export type PermissoesUsuario = Set<PermissaoKey>;

/** Nó da árvore visual — usado APENAS pela tela de gestão de permissões
 * (árvore de checkboxes no formulário de usuário). Não é fonte da verdade:
 * a fonte da verdade é o union type PermissaoKey acima.
 *
 * A árvore em si (`ARVORE_PERMISSOES`) NÃO mora aqui: ela é derivada de
 * `ESTRUTURA_APP` em `core/navegacao/navegacao.model.ts`, junto com o menu
 * lateral, para que as duas nunca divirjam. Este arquivo guarda só os tipos —
 * assim não tem import de runtime e nunca fecha ciclo. */
export interface NoArvorePermissao {
  label: string;
  chave?: PermissaoKey; // ausente em nós-pai (agrupadores)
  filhos?: NoArvorePermissao[];
}
