"""
Contrato de permissão do sistema: mesmo modelo do front
(core/permissions/permission.model.ts).

Cada permissão é uma string opaca ("chave"), não mais um par
(DominioId, Acao) com ações fixas de CRUD. Qualquer funcionalidade de
negócio, CRUD ou não, vira uma chave nomeada no padrão
`dominio.contexto.acao`. Adicionar um domínio novo = adicionar as
chaves dele aqui E no front, nos dois lugares — não existe geração
automática entre eles.
"""

# FRAGMENTO representa o catálogo real e completo hoje — ao adicionar um
# domínio novo, inclua as chaves dele aqui seguindo a mesma convenção.
PERMISSOES_VALIDAS: list[str] = [
    # --- Usuários ---
    "usuarios.acessar",
    "usuarios.gravar.incluir",
    "usuarios.gravar.editar",
    "usuarios.apagar",
    # --- Clientes ---
    "clientes.acessar",
    "clientes.gravar.incluir",
    "clientes.gravar.editar",
    "clientes.apagar",
    # --- Cidades ---
    "cidades.acessar",
    "cidades.gravar.incluir",
    "cidades.gravar.editar",
    "cidades.apagar",
    # --- Produtos ---
    "produtos.acessar",
    "produtos.gravar.incluir",
    "produtos.gravar.editar",
    "produtos.apagar",
    # Vincular ao produto os códigos de barras que a CMED publica para o
    # registro ANVISA dele. É ação de negócio, não CRUD: quem faz é o operador
    # do coletor, com a caixa na mão, e ele não tem (nem deve ter)
    # `produtos.gravar.editar`. Ver app/domains/expedicao/README.md.
    "produtos.codigo_barras.vincular_anvisa",
    # --- Marcas ---
    "marcas.acessar",
    "marcas.gravar.incluir",
    "marcas.gravar.editar",
    "marcas.apagar",
    # --- Empresas ---
    "empresas.acessar",
    "empresas.gravar.incluir",
    "empresas.gravar.editar",
    "empresas.apagar",
    # --- Pedidos ---
    "pedidos.acessar",
    "pedidos.gravar.incluir",
    "pedidos.gravar.editar",
    "pedidos.apagar",
    # --- Expedição (separação e conferência) ---
    "expedicao.acessar",
    "expedicao.separacao.executar",
    "expedicao.conferencia.executar",
    "expedicao.resetar",
    "expedicao.atribuir",
]

PERMISSOES_VALIDAS_SET: frozenset[str] = frozenset(PERMISSOES_VALIDAS)
