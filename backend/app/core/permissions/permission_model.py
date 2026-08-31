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
    # --- Estoque (saldo por produto e por lote) ---
    "estoque.acessar",
    "estoque.gravar.incluir",
    "estoque.gravar.editar",
    "estoque.apagar",
    # --- Endereçamento (onde cada lote está guardado no galpão) ---
    "enderecamento.acessar",
    "enderecamento.gravar.incluir",
    "enderecamento.gravar.editar",
    "enderecamento.apagar",
    # --- Notas fiscais (entradas e saídas — mesma tabela, mesmo domínio) ---
    "notas_fiscais.acessar",
    "notas_fiscais.gravar.incluir",
    "notas_fiscais.gravar.editar",
    "notas_fiscais.apagar",
    # --- Entregas (acompanhamento pós-faturamento) ---
    "entregas.acessar",
    # Ver TODAS as notas. Sem ela, o vendedor enxerga só aquelas em que ele é o
    # vendedor — é o `visualiza_vendas_proprias` do sistema antigo.
    "entregas.ver_todas",
    "entregas.interacao.registrar",
    "entregas.interacao.apagar",
    # Permissão da INTEGRAÇÃO, não de gente: é o que o usuário técnico do ERP
    # usa para postar mapa de carga e notas. Fica fora da árvore do formulário.
    "entregas.integrar",
    # --- Expedição (separação e conferência) ---
    "expedicao.acessar",
    "expedicao.separacao.executar",
    "expedicao.conferencia.executar",
    "expedicao.resetar",
    "expedicao.atribuir",
    # Iniciar e finalizar uma etapa NO NOME do operador atribuído. Separada de
    # `expedicao.atribuir` de propósito: distribuir trabalho e executar por
    # outra pessoa são coisas diferentes, e o galpão pode querer dar uma sem a
    # outra. Ver "Execução delegada" em domains/expedicao/README.md.
    "expedicao.delegar",
    # Exceção de emergência: iniciar e finalizar a etapa mesmo com o
    # endereçamento inconsistente, para destravar o faturamento com o aval de
    # quem responde pelo galpão. Não libera o botão do operador — só a execução
    # delegada. Ver "A exceção" em domains/expedicao/EXECUCAO_DELEGADA.md.
    "expedicao.enderecamento.liberar",
    # --- Inteligência de Mercado / Cotações ---
    # Domínio de CONSULTA a banco externo (OuroWeb): só existe "acessar",
    # porque não há nada para incluir, editar ou apagar. Ver
    # ARCHITECTURE.md → "Domínio de consulta a banco externo".
    "cotacoes.acessar",
]

PERMISSOES_VALIDAS_SET: frozenset[str] = frozenset(PERMISSOES_VALIDAS)
