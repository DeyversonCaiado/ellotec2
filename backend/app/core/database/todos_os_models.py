"""
Importa todos os models de todos os domínios. Necessário para que o
SQLAlchemy registre todas as tabelas no Base.metadata antes de qualquer
`create_all()` (script de bootstrap) ou autogeração de migração (Alembic).

Sempre que um domínio novo for criado, seu(s) model(s) precisam ser
importados aqui também — senão a tabela simplesmente não é criada.
"""

from app.core.auth.dispositivo_model import Dispositivo  # noqa: F401
from app.core.historico.historico_model import Historico  # noqa: F401
from app.core.auth.sessao_model import Sessao  # noqa: F401
from app.domains.cidades.cidade_model import Cidade  # noqa: F401
from app.domains.clientes.cliente_model import Cliente  # noqa: F401
from app.domains.empresas.empresa_model import Empresa  # noqa: F401
from app.domains.enderecamento.enderecamento_model import (  # noqa: F401
    EstoqueEndereco,
    EstoqueEnderecoLote,
)
from app.domains.entregas.entrega_model import (  # noqa: F401
    Entrega,
    EntregaNota,
    EntregaNotaInteracao,
    EntregaNotaItem,
)
from app.domains.estoque.estoque_model import Estoque, EstoqueLote  # noqa: F401
from app.domains.expedicao.expedicao_model import (  # noqa: F401
    Conferencia,
    ConferenciaItem,
    ExpedicaoAtribuicao,
    ExpedicaoPedidoStatus,
    Separacao,
    SeparacaoItem,
)
from app.domains.expedicao_configuracoes.expedicao_configuracao_model import (  # noqa: F401
    ExpedicaoConfiguracao,
)
from app.domains.marcas.marca_model import Marca  # noqa: F401
from app.domains.notas_fiscais.nota_fiscal_model import NotaFiscal, NotaFiscalItem  # noqa: F401
from app.domains.pedidos.pedido_model import Pedido, PedidoItem, PedidoStatus  # noqa: F401
from app.domains.produtos.produto_model import Produto, ProdutoCodigoBarras  # noqa: F401
from app.domains.usuarios.cargo_model import Cargo  # noqa: F401
from app.domains.usuarios.usuario_model import Usuario, UsuarioPermissao  # noqa: F401
