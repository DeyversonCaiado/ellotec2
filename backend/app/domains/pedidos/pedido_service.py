from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.domains.empresas import empresa_publico
from app.domains.pedidos.pedido_model import Pedido, PedidoItem, PedidoStatus
from app.domains.pedidos.pedido_contrato import (
    ItemPedidoEntradaSchema,
    PedidoAtualizarSchema,
    PedidoCriarSchema,
)
from app.domains.produtos import produto_publico
from app.domains.usuarios import usuario_publico
from app.shared.sync_helpers import incrementar_versao, marcar_apagado


def listar_status(sessao_db: Session) -> list[PedidoStatus]:
    return sessao_db.query(PedidoStatus).filter(PedidoStatus.sync_deleted_at.is_(None)).order_by(PedidoStatus.chave).all()


def listar_paginado(
    sessao_db: Session,
    page: int,
    per_page: int,
    sort: str,
    sort_type: str,
    q: str | None = None,
) -> tuple[list[Pedido], int]:
    """Uma página de pedidos. Mesmo formato de `produto_service.listar_paginado`.

    Pagina no banco por necessidade, não por estilo: são ~230 mil pedidos, e
    `Pedido.itens` é `lazy="selectin"` — devolver tudo carregaria junto todos
    os itens de todos os pedidos e derrubaria a API antes do navegador.

    A lista de colunas ordenáveis é fechada de propósito: `sort` vem da query
    string, e interpolar isso num ORDER BY seria injeção.
    """
    colunas_permitidas = {
        "sync_created_at": Pedido.sync_created_at,
        "sync_updated_at": Pedido.sync_updated_at,
        "data_pedido": Pedido.data_pedido,
        "numero": Pedido.numero,
    }

    coluna = colunas_permitidas.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Campo de ordenação inválido. Use sync_created_at, sync_updated_at, "
                "data_pedido ou numero."
            ),
        )

    ordenacao = coluna.desc() if sort_type.lower() == "desc" else coluna.asc()
    consulta_base = sessao_db.query(Pedido).filter(Pedido.sync_deleted_at.is_(None))

    q = (q or "").strip()
    if q:
        termo = f"%{q}%"
        consulta_base = consulta_base.filter(
            or_(
                Pedido.numero.ilike(termo),
                Pedido.sistema_origem_id.ilike(termo),
                Pedido.cliente_nome_fantasia.ilike(termo),
            )
        )

    total = consulta_base.count()
    itens = (
        # Desempate por id: sem ele, duas páginas podem repetir ou pular uma
        # linha quando várias têm o mesmo valor na coluna ordenada.
        consulta_base.order_by(ordenacao, Pedido.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return itens, total


def obter_por_id(sessao_db: Session, pedido_id: str) -> Pedido:
    pedido = (
        sessao_db.query(Pedido)
        .filter(Pedido.id == pedido_id, Pedido.sync_deleted_at.is_(None))
        .first()
    )
    if pedido is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    return pedido


def resolver_empresa(
    sessao_db: Session, empresa_id: str | None, empresa_sistema_origem_id: str | None
) -> str | None:
    """Traduz o par (id, sistema de origem) da empresa num id, ou None se
    nenhum dos dois veio. Usado por quem precisa desambiguar uma busca sem ter
    um schema em mãos — as rotas de GET, por exemplo."""
    if empresa_sistema_origem_id:
        resolvido = empresa_publico.obter_id_por_sistema_origem_id(
            sessao_db, empresa_sistema_origem_id
        )
        if resolvido is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Empresa com sistemaOrigemId '{empresa_sistema_origem_id}' não encontrada.",
            )
        return resolvido
    return empresa_id


def obter_por_sistema_origem_id(
    sessao_db: Session, sistema_origem_id: str, empresa_id: str | None = None
) -> Pedido:
    """Localiza o pedido pelo identificador do sistema de origem.

    `sistema_origem_id` sozinho NÃO identifica um pedido: a unicidade na tabela
    é do par `(sistema_origem_id, empresa_id)` (ver UniqueConstraint em
    pedido_model.py), porque cada empresa/filial integra com o próprio ERP e o
    mesmo número existe nas duas.

    Sem a empresa, uma busca ambígua devolvia o registro da empresa errada em
    silêncio — e a atualização seguinte colidia com o registro certo, gerando um
    409 que não tinha relação aparente com a causa. Por isso, ambiguidade agora
    é erro explícito, não escolha arbitrária.
    """
    consulta = sessao_db.query(Pedido).filter(
        Pedido.sistema_origem_id == sistema_origem_id, Pedido.sync_deleted_at.is_(None)
    )
    if empresa_id:
        consulta = consulta.filter(Pedido.empresa_id == empresa_id)

    # limit(2) basta: só interessa saber se há mais de um.
    encontrados = consulta.limit(2).all()

    if not encontrados:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    if len(encontrados) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O sistemaOrigemId '{sistema_origem_id}' existe em mais de uma empresa. "
                "Informe empresaId ou empresaSistemaOrigemId para identificar o pedido."
            ),
        )
    return encontrados[0]


def _validar_sistema_origem_disponivel(
    sessao_db: Session, sistema_origem_id: str | None, empresa_id: str, ignorar_id: str | None = None
) -> None:
    """sistema_origem_id é único POR EMPRESA (ver UniqueConstraint em
    pedido_model.py) — cada empresa/filial integra com seu próprio sistema
    de origem, então o mesmo identificador pode existir em empresas
    diferentes sem colidir."""
    if not sistema_origem_id:
        return

    consulta = sessao_db.query(Pedido).filter(
        Pedido.sistema_origem_id == sistema_origem_id,
        Pedido.empresa_id == empresa_id,
        Pedido.sync_deleted_at.is_(None),
    )
    if ignorar_id:
        consulta = consulta.filter(Pedido.id != ignorar_id)
    if consulta.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um pedido com esse sistema de origem para essa empresa.",
        )


def _gerar_proximo_numero(sessao_db: Session) -> str:
    """Numeração sequencial simples (PED-00001, PED-00002, ...). Conta
    todos os pedidos já criados, inclusive os soft-deletados — não
    reaproveita número de um pedido apagado, pra manter rastreabilidade
    fiscal/contábil (um número de pedido nunca deve ser reusado)."""
    total = sessao_db.query(func.count(Pedido.id)).scalar() or 0
    return f"PED-{total + 1:05d}"


def _resolver_produto_id(sessao_db: Session, item: ItemPedidoEntradaSchema) -> str:
    if item.produto_sistema_origem_id:
        produto_id = produto_publico.obter_id_por_sistema_origem_id(sessao_db, item.produto_sistema_origem_id)
        if produto_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto não encontrado para o sistema de origem informado em um dos itens.",
            )
        return produto_id

    return item.produto_id


def _resolver_empresa_id(sessao_db: Session, dados: PedidoCriarSchema | PedidoAtualizarSchema) -> str:
    if dados.empresa_sistema_origem_id:
        empresa_id = empresa_publico.obter_id_por_sistema_origem_id(sessao_db, dados.empresa_sistema_origem_id)
        if empresa_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa não encontrada para o sistema de origem informado.",
            )
        return empresa_id

    return dados.empresa_id


def _resolver_vendedor_id(sessao_db: Session, dados: PedidoCriarSchema | PedidoAtualizarSchema) -> str | None:
    """Vendedor não é obrigatório — só resolve quando um dos dois campos vem
    preenchido. Se vendedor_sistema_origem_id vier, ele decide (mesmo padrão
    de empresa_sistema_origem_id); senão, usa vendedor_id como veio."""
    if dados.vendedor_sistema_origem_id:
        vendedor_id = usuario_publico.obter_id_por_sistema_origem_id(sessao_db, dados.vendedor_sistema_origem_id)
        if vendedor_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendedor não encontrado para o sistema de origem informado.",
            )
        return vendedor_id

    return dados.vendedor_id


def _resolver_status_id(
    sessao_db: Session, dados: PedidoCriarSchema | PedidoAtualizarSchema
) -> str:
    """status_id referencia o catálogo pedido_status diretamente — não é
    enum fechado nem chave de texto livre. Mesmo padrão de
    _resolver_produto_id: se `status_sistema_origem_id` vier informado, ele
    resolve o registro; senão, `status_id` é usado como veio, e é a FK
    (Pedido.status_id -> pedido_status.id) quem recusa um id inexistente no
    INSERT/UPDATE (ver "Validação de id por foreign key" no ARCHITECTURE.md
    do backend) — nenhuma query redundante aqui só para checar existência.
    """
    if dados.status_sistema_origem_id:
        status_registro = (
            sessao_db.query(PedidoStatus)
            .filter(PedidoStatus.sistema_origem_id == dados.status_sistema_origem_id)
            .first()
        )
        if status_registro is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Status não encontrado para o sistema de origem informado.",
            )
        return status_registro.id

    return dados.status_id


def _montar_itens(sessao_db: Session, itens_entrada: list[ItemPedidoEntradaSchema]) -> list[PedidoItem]:
    """
    Grava cada item exatamente como veio no payload — código, descrição e
    preço são snapshot do que o front enviou. O cadastro de produtos NÃO é
    consultado para os dados do snapshot: `pedidos` não importa nada de
    `domains/produtos`, exceto o canal de leitura `produto_publico.py`
    usado aqui só para resolver `produto_sistema_origem_id` -> `produto_id`
    quando o item vier identificado assim. A FK de `produto_id` continua
    sendo quem garante, no INSERT, que o produto (resolvido ou informado
    direto) existe de fato.
    """
    return [
        PedidoItem(
            produto_id=_resolver_produto_id(sessao_db, item),
            produto_codigo=item.produto_codigo,
            produto_descricao=item.produto_descricao,
            quantidade=item.quantidade,
            preco_unitario=item.preco_unitario,
            endereco_produto=item.endereco_produto,
            lote=item.lote,
        )
        for item in itens_entrada
    ]


def criar(sessao_db: Session, dados: PedidoCriarSchema) -> Pedido:
    empresa_id = _resolver_empresa_id(sessao_db, dados)
    _validar_sistema_origem_disponivel(sessao_db, dados.sistema_origem_id, empresa_id)
    itens = _montar_itens(sessao_db, dados.itens)

    # A capa (Pedido) e os itens são gravados num único Session.commit():
    # `Pedido.itens` tem cascade="all, delete-orphan" (ver pedido_model.py),
    # então o SQLAlchemy inclui os INSERTs dos itens no mesmo flush da capa.
    # Isso já é uma transação só — se o INSERT de qualquer item violar uma
    # FK/constraint, o commit inteiro falha (IntegrityError) e NADA fica
    # persistido, nem a capa. `obter_sessao()` (core/database/conexao.py)
    # faz o rollback explícito no except antes de devolver a conexão pro
    # pool, então não há transação "pendurada" nem escrita parcial.
    pedido = Pedido(
        numero=_gerar_proximo_numero(sessao_db),
        data_pedido=dados.data_pedido,
        cliente_id=dados.cliente_id,
        cliente_nome_fantasia=dados.cliente_nome_fantasia,
        cliente_cnpj=dados.cliente_cnpj,
        empresa_id=empresa_id,
        vendedor_id=_resolver_vendedor_id(sessao_db, dados),
        sistema_origem_id=dados.sistema_origem_id,
        liberado_em=dados.liberado_em,
        status_id=_resolver_status_id(sessao_db, dados),
        observacoes=dados.observacoes,
        itens=itens,
    )
    sessao_db.add(pedido)
    sessao_db.commit()
    sessao_db.refresh(pedido)
    return pedido


def atualizar(
    sessao_db: Session,
    pedido_id: str,
    dados: PedidoAtualizarSchema,
    sistema_origem_id: str | None = None,
) -> Pedido:
    # A empresa é resolvida ANTES de localizar o pedido, e não depois: é ela
    # que desambigua o `sistema_origem_id`, que sozinho pode apontar para o
    # pedido de outra filial. O corpo do PUT já traz a empresa obrigatoriamente
    # (ver validar_referencia_de_empresa), então a integração não precisa mandar
    # nada novo — era só a ordem que estava errada.
    empresa_id = _resolver_empresa_id(sessao_db, dados)

    pedido = (
        obter_por_sistema_origem_id(sessao_db, sistema_origem_id, empresa_id)
        if sistema_origem_id
        else obter_por_id(sessao_db, pedido_id)
    )

    # Preserva o sistema_origem_id usado para localizar o registro quando o
    # corpo da requisição não o repetir — ver mesmo comentário em clientes.
    sistema_origem_id_final = dados.sistema_origem_id or sistema_origem_id
    _validar_sistema_origem_disponivel(sessao_db, sistema_origem_id_final, empresa_id, ignorar_id=pedido.id)

    itens = _montar_itens(sessao_db, dados.itens)

    pedido.data_pedido = dados.data_pedido
    pedido.cliente_id = dados.cliente_id
    pedido.cliente_nome_fantasia = dados.cliente_nome_fantasia
    pedido.cliente_cnpj = dados.cliente_cnpj
    pedido.empresa_id = empresa_id
    # Mesma regra do sistema_origem_id logo acima: corpo que não repete o campo
    # não apaga o que já estava lá. Milestone é fato consumado — uma integração
    # que reenvia a capa sem a data de liberação não pode zerar a liberação.
    if dados.liberado_em is not None:
        pedido.liberado_em = dados.liberado_em
    pedido.vendedor_id = _resolver_vendedor_id(sessao_db, dados)
    pedido.sistema_origem_id = sistema_origem_id_final
    pedido.status_id = _resolver_status_id(sessao_db, dados)
    pedido.observacoes = dados.observacoes
    incrementar_versao(pedido)

    for item_antigo in list(pedido.itens):
        sessao_db.delete(item_antigo)
    pedido.itens = itens

    # Mesmo raciocínio de criar(): um único commit no fim cobre a
    # atualização da capa + a troca completa dos itens (delete dos antigos
    # + insert dos novos). Se algo falhar, o commit inteiro é desfeito.
    sessao_db.commit()
    sessao_db.refresh(pedido)
    return pedido


def apagar(sessao_db: Session, pedido_id: str) -> None:
    pedido = obter_por_id(sessao_db, pedido_id)
    marcar_apagado(pedido)
    sessao_db.commit()
