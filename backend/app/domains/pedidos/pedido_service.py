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
from app.shared.vinculo_origem import resolver as resolver_vinculo_origem


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


def _gerar_proximo_numero(sessao_db: Session, empresa_id: str) -> str:
    """Numeração sequencial NUMÉRICA, por empresa: 1, 2, 3...

    Só é usada quando o pedido nasce aqui. Pedido que vem do ERP não passa por
    aqui — o número dele é o `sistema_origem_id`, ver `_numero_do_pedido`.

    **Sem prefixo.** Já foi "PED-00001", e o prefixo atrapalhava mais do que
    ajudava: o número do pedido é o que o cliente e o vendedor falam ao telefone,
    e ninguém dita "pê-é-dê-traço". Como código de ERP também é numérico, tirar o
    prefixo deixa os dois no mesmo formato.

    Parte da contagem e sobe até achar um número livre NAQUELA empresa. O laço
    existe porque a contagem sozinha não garante nada: os pedidos do ERP entram
    com o número deles e ocupam faixas quaisquer, então o contador pode cair em
    cima de um número que já existe. Uma volta a mais é barato — isto só roda
    quando alguém cria um pedido pela tela, o que é raro.

    Conta inclusive os soft-deletados, e o laço também os enxerga: número de
    pedido nunca deve ser reusado, por rastreabilidade fiscal.
    """
    proximo = sessao_db.query(func.count(Pedido.id)).scalar() or 0
    while True:
        proximo += 1
        numero = str(proximo)
        existe = (
            sessao_db.query(Pedido.id)
            .filter(Pedido.numero == numero, Pedido.empresa_id == empresa_id)
            .first()
        )
        if existe is None:
            return numero


def _numero_do_pedido(
    sessao_db: Session, sistema_origem_id: str | None, empresa_id: str
) -> str | None:
    """O número do pedido: **nulo** quando ele vem do ERP, sequencial daqui
    quando nasce na tela.

    **Um pedido tem um identificador só.** Quando o ERP manda o pedido, quem
    identifica é o `sistema_origem_id` — e `numero` fica NULO em vez de repetir
    aquele mesmo valor. Duplicar o código em duas colunas cria a pergunta "qual
    dos dois vale?" toda vez que os dois divergirem, e eles divergem: basta uma
    correção chegar por um caminho e não pelo outro.

    Quem exibe resolve com `sistema_origem_id or numero` — regra que a expedição
    e a tela de pedidos já aplicavam antes disso, e que agora tem exatamente um
    lado preenchido em cada caso.

    Sequencial só para o pedido que nasce aqui, porque aí não existe número de
    lugar nenhum e alguém precisa dar um.
    """
    if sistema_origem_id:
        return None
    return _gerar_proximo_numero(sessao_db, empresa_id)


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


def _montar_itens(
    sessao_db: Session,
    itens_entrada: list[ItemPedidoEntradaSchema],
    empresa_sistema_origem_id: str | None = None,
    pedido_sistema_origem_id: str | None = None,
) -> list[PedidoItem]:
    """
    Grava cada item exatamente como veio no payload — código, descrição e
    preço são snapshot do que o front enviou. O cadastro de produtos NÃO é
    consultado para os dados do snapshot: `pedidos` não importa nada de
    `domains/produtos`, exceto o canal de leitura `produto_publico.py`
    usado aqui só para resolver `produto_sistema_origem_id` -> `produto_id`
    quando o item vier identificado assim. A FK de `produto_id` continua
    sendo quem garante, no INSERT, que o produto (resolvido ou informado
    direto) existe de fato.

    `empresa_sistema_origem_id` e `pedido_sistema_origem_id` são os valores da
    CAPA, usados como padrão quando o item não repete o campo: os itens de um
    pedido são todos da mesma empresa e do mesmo pedido, então obrigar a
    integração a repetir os mesmos dois textos em cada linha só criaria
    oportunidade de divergir. Item que informar o seu próprio valor manda nele.
    """
    return [
        _aplicar_dados_do_item(
            PedidoItem(),
            item,
            _resolver_produto_id(sessao_db, item),
            empresa_sistema_origem_id,
            pedido_sistema_origem_id,
        )
        for item in itens_entrada
    ]


def _aplicar_dados_do_item(
    linha: PedidoItem,
    entrada: ItemPedidoEntradaSchema,
    produto_id: str,
    empresa_sistema_origem_id: str | None,
    pedido_sistema_origem_id: str | None,
) -> PedidoItem:
    """Copia o payload para a linha. Serve tanto para uma linha nova quanto para
    uma que já existe — é o que permite a reconciliação atualizar NO LUGAR em
    vez de apagar e recriar."""
    linha.produto_id = produto_id
    linha.produto_codigo = entrada.produto_codigo
    linha.produto_descricao = entrada.produto_descricao
    linha.quantidade = entrada.quantidade
    linha.preco_unitario = entrada.preco_unitario
    linha.lote = entrada.lote
    # Os três vínculos com o ERP nunca são apagados por uma reconciliação que
    # não os traz — ver app/shared/vinculo_origem.py.
    linha.empresa_sistema_origem_id = resolver_vinculo_origem(
        entrada.empresa_sistema_origem_id,
        empresa_sistema_origem_id,
        linha.empresa_sistema_origem_id,
    )
    linha.pedido_sistema_origem_id = resolver_vinculo_origem(
        entrada.pedido_sistema_origem_id,
        pedido_sistema_origem_id,
        linha.pedido_sistema_origem_id,
    )
    linha.produto_sistema_origem_id = resolver_vinculo_origem(
        entrada.produto_sistema_origem_id, ja_gravado=linha.produto_sistema_origem_id
    )
    return linha


def _reconciliar_itens(
    sessao_db: Session,
    pedido: Pedido,
    itens_entrada: list[ItemPedidoEntradaSchema],
    empresa_sistema_origem_id: str | None = None,
    pedido_sistema_origem_id: str | None = None,
) -> None:
    """Compara o payload com o que já está gravado, linha a linha.

    Antes daqui, `atualizar` apagava fisicamente todas as linhas e inseria
    outras. Duas coisas quebravam:

    1. **O id do item mudava a cada PUT.** `expedicao_separacao_itens.
       pedido_item_id` aponta para cá, então uma integração que reenviasse a
       capa sem mudar nada destruía o vínculo com a separação — em silêncio,
       ou com erro de FK depois que a expedição passou a existir.
    2. **Era DELETE físico em model com SyncMixin**, o que o ARCHITECTURE.md
       proíbe desde sempre. O bug de arquitetura é anterior à expedição; ela só
       o tornou visível.

    A chave de reconciliação é `(produto_id, lote)` — a mesma de
    `uq_pedido_itens_pedido_produto_lote` e a mesma que
    `itens_sem_linha_duplicada` já valida na entrada. O endereço não entra: ele
    diz onde a mercadoria está no galpão, não o que o cliente comprou.

    Linha que sai do payload é `marcar_apagado()`, nunca `delete()`. Linha
    apagada que volta é REVIVIDA no lugar, e não reinserida: além de preservar o
    id, é o que evita o INSERT bater no unique, que enxerga a linha soft-deletada
    ocupando a chave.

    Não dá `commit()` — quem fecha a transação é `atualizar`, junto com a capa.
    """
    # Inclui as apagadas: são elas que ocupam a chave no unique, e reviver é o
    # comportamento certo quando a mesma linha volta.
    existentes: dict[tuple[str, str | None], PedidoItem] = {}
    for linha in pedido.itens:
        existentes.setdefault((linha.produto_id, linha.lote), linha)

    vistas: set[tuple[str, str | None]] = set()
    for entrada in itens_entrada:
        produto_id = _resolver_produto_id(sessao_db, entrada)
        chave = (produto_id, entrada.lote)
        vistas.add(chave)

        linha = existentes.get(chave)
        if linha is None:
            pedido.itens.append(
                _aplicar_dados_do_item(
                    PedidoItem(),
                    entrada,
                    produto_id,
                    empresa_sistema_origem_id,
                    pedido_sistema_origem_id,
                )
            )
            continue

        _aplicar_dados_do_item(
            linha, entrada, produto_id, empresa_sistema_origem_id, pedido_sistema_origem_id
        )
        # Reviver é explícito: `marcar_apagado` não tem contrapartida em
        # sync_helpers, e inventar uma só para este caso seria abstração por
        # antecipação (a expedição, que também soft-deleta, nunca revive nada).
        linha.sync_deleted_at = None
        incrementar_versao(linha)

    for chave, linha in existentes.items():
        if chave not in vistas and linha.sync_deleted_at is None:
            marcar_apagado(linha)


def criar(sessao_db: Session, dados: PedidoCriarSchema) -> Pedido:
    empresa_id = _resolver_empresa_id(sessao_db, dados)
    _validar_sistema_origem_disponivel(sessao_db, dados.sistema_origem_id, empresa_id)
    itens = _montar_itens(
        sessao_db, dados.itens, dados.empresa_sistema_origem_id, dados.sistema_origem_id
    )

    # A capa (Pedido) e os itens são gravados num único Session.commit():
    # `Pedido.itens` tem cascade="all, delete-orphan" (ver pedido_model.py),
    # então o SQLAlchemy inclui os INSERTs dos itens no mesmo flush da capa.
    # Isso já é uma transação só — se o INSERT de qualquer item violar uma
    # FK/constraint, o commit inteiro falha (IntegrityError) e NADA fica
    # persistido, nem a capa. `obter_sessao()` (core/database/conexao.py)
    # faz o rollback explícito no except antes de devolver a conexão pro
    # pool, então não há transação "pendurada" nem escrita parcial.
    pedido = Pedido(
        numero=_numero_do_pedido(sessao_db, dados.sistema_origem_id, empresa_id),
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

    # NUNCA apaga o vínculo com o ERP. A ordem é: o que o corpo mandou, senão o
    # que localizou o registro, senão O QUE JÁ ESTAVA GRAVADO.
    #
    # Esse último degrau é o que faltava, e ele quebrou a produção: editar o
    # registro pela TELA manda um corpo sem `sistemaOrigemId` e sem o query
    # param, então o campo era zerado em silêncio. O funcionário 00168 perdeu o
    # vínculo desse jeito, e a integração de pedidos parou por três dias em
    # loop de restart — todo pedido dele passou a responder 404 "Vendedor não
    # encontrado para o sistema de origem informado".
    #
    # Só a integração cria esse vínculo; ninguém o remove por um formulário que
    # nem exibe o campo. Para desvincular de verdade, é um caminho explícito.
    sistema_origem_id_final = resolver_vinculo_origem(
        dados.sistema_origem_id, sistema_origem_id, pedido.sistema_origem_id
    )
    _validar_sistema_origem_disponivel(sessao_db, sistema_origem_id_final, empresa_id, ignorar_id=pedido.id)

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
    # Pedido que passa a ter identidade no ERP larga o número local: quem
    # identifica passa a ser o `sistema_origem_id`, e manter os dois
    # preenchidos recria a pergunta "qual dos dois vale?" (ver
    # `_numero_do_pedido`).
    if sistema_origem_id_final:
        pedido.numero = None
    pedido.status_id = _resolver_status_id(sessao_db, dados)
    pedido.observacoes = dados.observacoes
    incrementar_versao(pedido)

    # `sistema_origem_id_final`, e não `dados.sistema_origem_id`: no PUT que
    # localiza o pedido pela query string o corpo pode não repetir o campo, e os
    # itens ficariam sem a perna do pedido por um detalhe de transporte.
    _reconciliar_itens(
        sessao_db,
        pedido,
        dados.itens,
        dados.empresa_sistema_origem_id,
        sistema_origem_id_final,
    )

    # Mesmo raciocínio de criar(): um único commit no fim cobre a atualização da
    # capa + a reconciliação dos itens. Se algo falhar, o commit inteiro é
    # desfeito.
    sessao_db.commit()
    sessao_db.refresh(pedido)
    return pedido


def apagar(sessao_db: Session, pedido_id: str) -> None:
    pedido = obter_por_id(sessao_db, pedido_id)
    marcar_apagado(pedido)
    sessao_db.commit()
