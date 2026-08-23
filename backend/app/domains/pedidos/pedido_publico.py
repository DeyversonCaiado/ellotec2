"""
Canal de leitura de `pedidos` para outros domínios (hoje: `expedicao`).

Regras do arquivo de fronteira (ver ARCHITECTURE.md → "Como se faz: o arquivo
de fronteira `<dominio>_publico.py`"): só leitura, recebe `Session` e ids
primitivos, devolve contrato próprio — nunca o model SQLAlchemy. Quem consome
importa só este arquivo, nunca `pedido_service` / `pedido_contrato`.
"""

from datetime import date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domains.pedidos.pedido_model import Pedido, PedidoItem, PedidoStatus
from app.shared.contrato_base import ContratoBase

# As chaves moram aqui, no domínio dono do catálogo `pedido_status` —
# expedição pergunta, não adivinha.
#
# `PED` é o status que o ERP usa para liberar o pedido; os quatro seguintes
# são as etapas do galpão, cadastrados por nós (ver migration d4a6f8c02b19).
STATUS_LIBERADO_PARA_EXPEDICAO = "PED"
STATUS_EM_SEPARACAO = "em_separacao"
STATUS_SEPARADO = "separado"
STATUS_EM_CONFERENCIA = "em_conferencia"
STATUS_CONFERIDO = "conferido"

# O pedido entra e permanece na fila da expedição enquanto estiver em algum
# destes. Substitui a comparação com uma única chave que existia antes: hoje o
# fluxo tem mais de um status válido, e uma igualdade solta espalhada pelo
# código de expedição voltaria a travar a cada status novo.
STATUS_DA_EXPEDICAO = (
    STATUS_LIBERADO_PARA_EXPEDICAO,
    STATUS_EM_SEPARACAO,
    STATUS_SEPARADO,
    STATUS_EM_CONFERENCIA,
    STATUS_CONFERIDO,
)


# Colunas por onde a listagem de expedição pode ordenar. Lista fechada porque
# `sort` vem da query string — interpolar isso num ORDER BY seria injeção.
#
# Só entram colunas da PRÓPRIA tabela `pedidos`. Cidade vem do cadastro vivo do
# cliente, quantidade de itens é contagem, e o andamento das etapas mora nas
# tabelas da expedição: nenhuma dessas dá para ordenar aqui sem join novo, e
# ordenar depois da paginação ordenaria só a página — que é pior que não
# ordenar, porque parece que funcionou.
# Contagem de itens do pedido como subconsulta correlacionada, para dar pra
# ordenar por ela sem trazer os itens. `pedido_itens` é do próprio domínio, então
# isto não atravessa fronteira nenhuma.
_QUANTIDADE_ITENS = (
    select(func.count(PedidoItem.id))
    .where(PedidoItem.pedido_id == Pedido.id, PedidoItem.sync_deleted_at.is_(None))
    .correlate(Pedido)
    .scalar_subquery()
)

COLUNAS_ORDENAVEIS = {
    "numero": Pedido.numero,
    "quantidade_itens": _QUANTIDADE_ITENS,
    "data_pedido": Pedido.data_pedido,
    "cliente_nome_fantasia": Pedido.cliente_nome_fantasia,
    "liberado_em": Pedido.liberado_em,
    "sync_updated_at": Pedido.sync_updated_at,
}


def pode_iniciar_expedicao(status_chave: str) -> bool:
    """Só o status liberado pelo ERP autoriza abrir separação ou conferência.

    A listagem mostra pedido de qualquer status — quem trabalha no galpão
    precisa achar um pedido para consultar mesmo quando ele ainda não foi
    liberado. Poder ABRIR o processo é outra coisa, e continua restrito.
    """
    return status_chave == STATUS_LIBERADO_PARA_EXPEDICAO


def obter_status_id(sessao_db: Session, chave: str) -> str | None:
    """Resolve uma chave do catálogo `pedido_status` para o id. Canal usado pela
    expedição, que grava o andamento do galpão referenciando este catálogo (ver
    ExpedicaoPedidoStatus) — o vocabulário de status é um só no sistema."""
    status = (
        sessao_db.query(PedidoStatus)
        .filter(PedidoStatus.chave == chave, PedidoStatus.sync_deleted_at.is_(None))
        .first()
    )
    return status.id if status else None


def listar_chaves_status(sessao_db: Session) -> list[str]:
    """Todas as chaves vivas do catálogo `pedido_status`, ordenadas.

    Canal de leitura para quem precisa montar um filtro por status sem ter
    permissão no domínio de pedidos — hoje a tela de expedição, cujo operador
    tem `expedicao.acessar` e mais nada."""
    linhas = (
        sessao_db.query(PedidoStatus.chave)
        .filter(PedidoStatus.sync_deleted_at.is_(None))
        .order_by(PedidoStatus.chave.asc())
        .all()
    )
    return [chave for (chave,) in linhas]


def obter_chaves_status(sessao_db: Session, status_ids: list[str]) -> dict[str, str]:
    """status_id -> chave, numa consulta só. Contrapartida de `obter_status_id`
    para quem guardou o id e precisa exibir a chave."""
    if not status_ids:
        return {}
    linhas = (
        sessao_db.query(PedidoStatus.id, PedidoStatus.chave)
        .filter(PedidoStatus.id.in_(status_ids))
        .all()
    )
    return dict(linhas)


class ItemPedidoResumo(ContratoBase):
    id: str
    produto_id: str
    produto_codigo: str
    produto_descricao: str
    quantidade: int
    endereco_produto: str | None
    lote: str | None


class PedidoResumo(ContratoBase):
    """Contrato próprio da fronteira — não é o model, não é o schema do router."""

    id: str
    numero: str
    sistema_origem_id: str | None
    data_pedido: date
    cliente_id: str
    cliente_nome_fantasia: str
    cliente_cnpj: str
    empresa_id: str
    vendedor_id: str | None
    status_chave: str
    # Milestone da liberação — é dele que a expedição mede o ciclo do pedido.
    liberado_em: datetime | None
    alterado_em: datetime
    observacoes: str
    itens: list[ItemPedidoResumo]


def _para_resumo(pedido: Pedido) -> PedidoResumo:
    return PedidoResumo(
        id=pedido.id,
        numero=pedido.numero,
        sistema_origem_id=pedido.sistema_origem_id,
        data_pedido=pedido.data_pedido,
        cliente_id=pedido.cliente_id,
        cliente_nome_fantasia=pedido.cliente_nome_fantasia,
        cliente_cnpj=pedido.cliente_cnpj,
        empresa_id=pedido.empresa_id,
        vendedor_id=pedido.vendedor_id,
        status_chave=pedido.status.chave,
        liberado_em=pedido.liberado_em,
        alterado_em=pedido.sync_updated_at,
        observacoes=pedido.observacoes,
        itens=[
            ItemPedidoResumo(
                id=item.id,
                produto_id=item.produto_id,
                produto_codigo=item.produto_codigo,
                produto_descricao=item.produto_descricao,
                quantidade=item.quantidade,
                endereco_produto=item.endereco_produto,
                lote=item.lote,
            )
            for item in pedido.itens
        ],
    )


def listar_para_expedicao(
    sessao_db: Session,
    data_inicio: date,
    data_fim: date,
    termo: str | None,
    page: int,
    per_page: int,
    status_chaves: list[str] | None = None,
    ids_permitidos: list[str] | None = None,
    ids_excluidos: list[str] | None = None,
    empresa_id: str | None = None,
    sort: str = "sync_updated_at",
    sort_type: str = "desc",
) -> tuple[list[PedidoResumo], int]:
    """Uma página de pedidos para a tela da expedição, de qualquer status.

    O período filtra a DATA DO PEDIDO — é a data que o usuário conhece e vê na
    tela. A ordenação é por data de alteração decrescente, para o que mexeu
    agora aparecer primeiro dentro do período escolhido.

    Pagina no banco de propósito. São ~230 mil pedidos: devolver tudo estoura a
    memória do navegador e, antes disso, faz o MySQL ordenar a tabela inteira em
    arquivo temporário. Os índices de `data_pedido` e `sync_updated_at`
    (migration f6c8b3d150ea) sustentam o filtro e o ORDER BY.

    `status_chaves` filtra pelo status do ERP (chaves do catálogo
    `pedido_status`). Vazio ou None = todos, que é o comportamento de sempre.
    O filtro é aplicado AQUI, na consulta paginada, e não na página já
    carregada: filtrar depois devolveria 3 linhas numa página de 20 e um total
    que não corresponde ao que se vê. Vale o mesmo para `empresa_id` e para o
    par `ids_permitidos` / `ids_excluidos`, conjuntos de pedidos escolhidos por
    quem chamou.

    Os dois conjuntos de ids existem porque quem chama filtra por dado que não é
    deste domínio (a expedição, pela situação das etapas e pelo operador do
    processo). Ela resolve o recorte nas tabelas dela e entrega os ids — este
    domínio não conhece separação nem conferência, e continua não conhecendo.
    `ids_excluidos` é o que permite perguntar pela AUSÊNCIA de algo: "pedido sem
    separação aberta" não é um conjunto que se possa listar sem varrer a base
    inteira, mas é trivial como "todos, menos estes".
    """
    coluna = COLUNAS_ORDENAVEIS.get(sort)
    if coluna is None:
        raise ValueError(
            f"Campo de ordenação inválido: {sort!r}. "
            f"Use um destes: {', '.join(sorted(COLUNAS_ORDENAVEIS))}."
        )

    consulta = sessao_db.query(Pedido).filter(
        Pedido.sync_deleted_at.is_(None),
        Pedido.data_pedido >= data_inicio,
        Pedido.data_pedido <= data_fim,
    )

    if ids_permitidos is not None:
        # Recorte de visibilidade decidido por quem chamou (hoje: a expedição,
        # que limita o operador aos pedidos atribuídos a ele). Aqui é só o
        # filtro; a regra de quem vê o quê não é deste domínio.
        consulta = consulta.filter(Pedido.id.in_(ids_permitidos))

    if ids_excluidos:
        consulta = consulta.filter(Pedido.id.notin_(ids_excluidos))

    if empresa_id:
        consulta = consulta.filter(Pedido.empresa_id == empresa_id)

    if status_chaves:
        # Join pelo catálogo em vez de resolver as chaves para ids antes: é uma
        # consulta a menos, e `pedido_status.chave` é único e indexado.
        consulta = consulta.join(Pedido.status).filter(PedidoStatus.chave.in_(status_chaves))

    termo = (termo or "").strip()
    if termo:
        curinga = f"%{termo}%"
        consulta = consulta.filter(
            or_(
                Pedido.numero.ilike(curinga),
                Pedido.sistema_origem_id.ilike(curinga),
                Pedido.cliente_nome_fantasia.ilike(curinga),
            )
        )

    total = consulta.count()
    pedidos = (
        # Desempate por id: sem ele, valores repetidos na coluna ordenada fazem
        # duas páginas repetirem ou pularem linha.
        consulta.order_by(
            coluna.desc() if sort_type.lower() == "desc" else coluna.asc(), Pedido.id.asc()
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return [_para_resumo(pedido) for pedido in pedidos], total


def obter_resumo(sessao_db: Session, pedido_id: str) -> PedidoResumo | None:
    pedido = (
        sessao_db.query(Pedido)
        .filter(Pedido.id == pedido_id, Pedido.sync_deleted_at.is_(None))
        .first()
    )
    return _para_resumo(pedido) if pedido else None
