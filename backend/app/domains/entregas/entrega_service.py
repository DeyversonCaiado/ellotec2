from datetime import date, datetime, time
from decimal import Decimal

from fastapi import HTTPException, status as http_status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, noload

from app.domains.empresas import empresa_publico
from app.domains.entregas import entrega_prazo
from app.domains.entregas.entrega_contrato import (
    STATUS_ENCERRA_ENTREGA,
    EntregaCriarSchema,
    FiltrosListagemSchema,
    NotaDevolucaoSchema,
    SugestoesFiltroSchema,
    EntregaNotaCriarSchema,
    EntregaNotaRespostaSchema,
    EntregaNotaResumoSchema,
    InteracaoAtualizarSchema,
    InteracaoCriarSchema,
    InteracaoRespostaSchema,
    ItemEntregaNotaEntradaSchema,
)
from app.domains.entregas.entrega_model import (
    Entrega,
    EntregaNota,
    EntregaNotaInteracao,
    EntregaNotaItem,
)
from app.domains.usuarios import usuario_publico
from app.shared.sync_helpers import incrementar_versao, marcar_apagado

# Fechada de propósito: `sort` vem da query string, e interpolar isso num
# ORDER BY seria injeção. Mesmo padrão dos outros domínios.
_COLUNAS_ORDENAVEIS = {
    "data_nota": EntregaNota.data_nota,
    "numero_nota": EntregaNota.numero_nota,
    "valor_total": EntregaNota.valor_total,
    "data_prevista_entrega": EntregaNota.data_prevista_entrega,
    # Sem `sync_updated_at` aqui: ordenar por ele seria usar auditoria da linha
    # como regra de negócio (ver ARCHITECTURE.md). Um reprocessamento da
    # integração reorganizaria a tela sem nada ter mudado na entrega.
}


# ---------------------------------------------------------------------------
# O painel de filtros: uma tabela, não dezessete blocos `if`
#
# Cada campo filtrável é uma linha aqui, e as duas operações que a tela precisa
# — FILTRAR por valores escolhidos e LISTAR os valores que existem no período —
# saem da mesma linha. É isso que impede o defeito clássico deste tipo de tela:
# o autocomplete oferecer um valor que o filtro não reconhece, ou o filtro
# aceitar um valor que a lista nunca mostrou. Uma definição, dois usos.
#
# Três campos não cabem nesta tabela e têm tratamento próprio logo abaixo:
# `empresa` e `vendedor` (o valor exibido mora em OUTRO domínio, e a tradução
# passa pela borda pública dele) e os quatro campos de item (que são EXISTS
# sobre `entrega_nota_itens`, não coluna da nota).
# ---------------------------------------------------------------------------

# campo do contrato -> coluna de `entrega_notas`
_FILTROS_DA_NOTA = {
    "tipo_nota": EntregaNota.tipo_nota,
    "pedido": EntregaNota.pedido,
    "numero_nota": EntregaNota.numero_nota,
    "cliente": EntregaNota.cliente_nome,
    "uf": EntregaNota.cliente_uf,
    "cidade": EntregaNota.cliente_cidade,
    "situacao": EntregaNota.situacao,
    "transportadora": EntregaNota.transportadora_nome,
    "status": EntregaNota.status_atual,
}

# campo do contrato -> coluna de `entrega_nota_itens` (vira EXISTS)
_FILTROS_DO_ITEM = {
    "produto": EntregaNotaItem.produto_descricao,
    "marca": EntregaNotaItem.marca_nome,
    "lote": EntregaNotaItem.lote,
    "quantidade": EntregaNotaItem.quantidade,
}

# campo do contrato -> coluna de `entregas` (o mapa de carga; vira EXISTS na
# relação, porque nota sem mapa é caso normal e o join a excluiria)
_FILTROS_DO_MAPA = {
    "numero_mapa": Entrega.numero_mapa,
}

# ---------------------------------------------------------------------------
# O número da nota devolvida, extraído da chave de acesso referenciada
#
# O layout da NF-e fixa a posição de cada pedaço da chave de 44 dígitos:
#
#   cUF(2) AAMM(4) CNPJ(14) modelo(2) série(3) **nNF(9)** tpEmis(1) cNF(8) DV(1)
#    1-2    3-6      7-20     21-22    23-25     26-34      35      36-43   44
#
# Então o número do documento são as 9 posições a partir da 26ª. `substr` é
# 1-based tanto no MySQL quanto no SQLite dos testes, e é por isso que o
# recorte pode ser o mesmo nos dois.
#
# Isto NÃO vira coluna nova: é dado derivado de um campo que já existe, e
# guardá-lo em separado criaria duas verdades que divergem no dia em que a
# chave for corrigida. O custo é que o filtro não usa índice — aceitável,
# porque ele sempre roda dentro do recorte de período.
# ---------------------------------------------------------------------------
POSICAO_NUMERO_NA_CHAVE = 26
TAMANHO_NUMERO_NA_CHAVE = 9


def _numero_da_nota_devolvida():
    return func.substr(
        EntregaNota.chave_acesso_referenciada,
        POSICAO_NUMERO_NA_CHAVE,
        TAMANHO_NUMERO_NA_CHAVE,
    )


# Campos do painel que são EXPRESSÃO, não coluna. Entram nas mesmas duas
# operações (filtrar e listar valores) pela mesma linha, exatamente como os
# outros — é isso que garante que o valor oferecido é aceito pelo filtro.
_FILTROS_DERIVADOS_DA_NOTA = {
    "nota_devolvida": _numero_da_nota_devolvida,
}

# Campos de data: comparados pelo DIA, não pelo instante. A coluna é DATETIME e
# a pessoa escolhe "20/08/2026" numa lista — comparar direto nunca casaria,
# porque o valor gravado tem hora.
_FILTROS_DE_DATA_DA_NOTA = {"data_nota": EntregaNota.data_nota}
_FILTROS_DE_DATA_DO_MAPA = {"data_mapa": Entrega.data_mapa}


# ---------------------------------------------------------------------------
# Entrada da integração
# ---------------------------------------------------------------------------


def _resolver_empresa_id(sessao_db: Session, dados) -> str:
    if dados.empresa_sistema_origem_id:
        empresa_id = empresa_publico.obter_id_por_sistema_origem_id(
            sessao_db, dados.empresa_sistema_origem_id
        )
        if empresa_id is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Empresa não encontrada para o sistema de origem informado.",
            )
        return empresa_id
    return dados.empresa_id


def registrar_entrega(sessao_db: Session, dados: EntregaCriarSchema) -> Entrega:
    """Cria ou atualiza o mapa de carga.

    É upsert, não insert: o job de integração vai reprocessar o mesmo mapa (por
    reexecução, por correção no ERP), e duplicar o mapa duplicaria as entregas
    penduradas nele. A chave é (empresa, número do mapa).
    """
    empresa_id = _resolver_empresa_id(sessao_db, dados)

    entrega = (
        sessao_db.query(Entrega)
        .filter(
            Entrega.empresa_id == empresa_id,
            Entrega.numero_mapa == dados.numero_mapa,
            Entrega.sync_deleted_at.is_(None),
        )
        .first()
    )
    novo = entrega is None
    if novo:
        entrega = Entrega(empresa_id=empresa_id, numero_mapa=dados.numero_mapa)

    entrega.data_mapa = dados.data_mapa
    entrega.transportadora_nome = dados.transportadora_nome
    entrega.transportadora_cnpj = dados.transportadora_cnpj
    entrega.motorista = dados.motorista
    entrega.placa_veiculo = dados.placa_veiculo
    entrega.sistema_origem_id = dados.sistema_origem_id

    if novo:
        sessao_db.add(entrega)
    else:
        incrementar_versao(entrega)

    sessao_db.flush()
    # O mapa pode chegar DEPOIS das notas dele (as duas integrações são
    # independentes). Quando isso acontece, as notas já estão gravadas sem
    # vínculo, e é aqui que elas ganham mapa, prazo e data prevista.
    _vincular_notas_pendentes(sessao_db, entrega)

    sessao_db.commit()
    sessao_db.refresh(entrega)
    return entrega


def _vincular_notas_pendentes(sessao_db: Session, entrega: Entrega) -> None:
    notas = (
        sessao_db.query(EntregaNota)
        .filter(
            EntregaNota.entrega_id == entrega.id,
            EntregaNota.sync_deleted_at.is_(None),
        )
        .all()
    )
    for nota in notas:
        _aplicar_prazo(nota, entrega)


def _aplicar_prazo(nota: EntregaNota, entrega: Entrega | None) -> None:
    """Congela prazo e data prevista no momento em que o mapa é conhecido.

    Congelar é deliberado: se a tabela de SLA for revisada no ano que vem, as
    entregas de hoje continuam medidas pelo prazo que foi prometido hoje.
    """
    nota.prazo_dias = entrega_prazo.calcular_prazo_dias(
        nota.cliente_uf, nota.cliente_cidade, nota.termolabil
    )
    data_mapa = entrega.data_mapa if entrega else None
    nota.data_prevista_entrega = entrega_prazo.calcular_data_prevista(
        data_mapa.date() if data_mapa else None, nota.prazo_dias
    )


def _montar_itens(itens: list[ItemEntregaNotaEntradaSchema]) -> list[EntregaNotaItem]:
    return [
        EntregaNotaItem(
            numero_item=item.numero_item,
            produto_codigo=item.produto_codigo,
            produto_descricao=item.produto_descricao,
            marca_nome=item.marca_nome,
            quantidade=item.quantidade,
            preco_unitario=item.preco_unitario,
            valor_total=item.valor_total,
            lote=item.lote,
            validade=item.validade,
            quantidade_devolvida=item.quantidade_devolvida,
            observacao=item.observacao,
        )
        for item in itens
    ]


def registrar_nota(sessao_db: Session, dados: EntregaNotaCriarSchema) -> EntregaNota:
    """Cria ou atualiza uma nota acompanhada, com os itens.

    Upsert pela chave natural (empresa, número, série, pedido) — a integração
    reprocessa, e sem isso a mesma nota entraria duas vezes.

    A capa e os itens vão num commit só: `EntregaNota.itens` tem
    cascade="all, delete-orphan", então uma falha em qualquer item desfaz a
    gravação inteira em vez de deixar a nota com metade dos produtos.
    """
    empresa_id = _resolver_empresa_id(sessao_db, dados)

    nota = (
        sessao_db.query(EntregaNota)
        .filter(
            EntregaNota.empresa_id == empresa_id,
            EntregaNota.numero_nota == dados.numero_nota,
            EntregaNota.serie == dados.serie,
            EntregaNota.pedido == dados.pedido,
            EntregaNota.sync_deleted_at.is_(None),
        )
        .first()
    )
    novo = nota is None
    if novo:
        nota = EntregaNota(
            empresa_id=empresa_id,
            numero_nota=dados.numero_nota,
            serie=dados.serie,
            pedido=dados.pedido,
        )

    entrega = _resolver_entrega(sessao_db, empresa_id, dados.entrega_numero_mapa)

    nota.entrega_id = entrega.id if entrega else None
    nota.tipo_nota = dados.tipo_nota
    nota.data_nota = dados.data_nota
    nota.situacao = dados.situacao
    nota.valor_total = dados.valor_total
    nota.chave_acesso_nota = dados.chave_acesso_nota
    nota.chave_acesso_referenciada = dados.chave_acesso_referenciada
    nota.cliente_codigo = dados.cliente_codigo
    nota.cliente_nome = dados.cliente_nome
    nota.cliente_cidade = dados.cliente_cidade
    nota.cliente_uf = dados.cliente_uf
    nota.transportadora_nome = dados.transportadora_nome
    nota.termolabil = dados.termolabil
    nota.sistema_origem_id = dados.sistema_origem_id

    # Vendedor não resolvido NÃO recusa a nota: um código de funcionário que
    # não existe aqui é problema de cadastro, e perder o documento por causa
    # dele seria pior. A nota fica sem vendedor até alguém corrigir.
    if dados.vendedor_sistema_origem_id:
        nota.vendedor_id = usuario_publico.obter_id_por_sistema_origem_id(
            sessao_db, dados.vendedor_sistema_origem_id
        )

    _aplicar_prazo(nota, entrega)

    if novo:
        sessao_db.add(nota)
    else:
        incrementar_versao(nota)
        for item_antigo in list(nota.itens):
            sessao_db.delete(item_antigo)
        # Sem este flush o SQLAlchemy emite os INSERTs dos itens novos antes
        # dos DELETEs dos antigos, e `uq_entrega_nota_itens_numero` recusa a
        # atualização inteira.
        sessao_db.flush()

    if dados.itens:
        nota.itens = _montar_itens(dados.itens)

    sessao_db.commit()
    sessao_db.refresh(nota)
    return nota


def _resolver_entrega(
    sessao_db: Session, empresa_id: str, numero_mapa: str | None
) -> Entrega | None:
    """Localiza o mapa de carga, se ele já existir aqui.

    Devolver None quando o mapa não chegou ainda é intencional — as duas
    integrações são independentes, e recusar a nota porque o mapa está
    atrasado faria a tela perder documentos por causa de ordem de chegada.
    `registrar_entrega` costura o vínculo quando o mapa aparecer.
    """
    if not numero_mapa:
        return None
    return (
        sessao_db.query(Entrega)
        .filter(
            Entrega.empresa_id == empresa_id,
            Entrega.numero_mapa == numero_mapa,
            Entrega.sync_deleted_at.is_(None),
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def listar_paginado(
    sessao_db: Session,
    page: int,
    per_page: int,
    sort: str,
    sort_type: str,
    q: str | None = None,
    filtros: FiltrosListagemSchema | None = None,
    status_prazo: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    apenas_vendedor_id: str | None = None,
    hoje: date | None = None,
) -> tuple[list[EntregaNotaResumoSchema], int]:
    """Uma página de notas em acompanhamento.

    Todo filtro é resolvido no banco, sobre a base inteira — filtrar no front
    recortaria só a página carregada e o total do rodapé não bateria.

    A exceção é `status_prazo`, que não é coluna: depende de hoje (ver
    entrega_prazo.calcular_status_prazo). Ele é traduzido para condições sobre
    `data_prevista_entrega`/`entrega_id`, que SÃO colunas — assim o filtro
    continua valendo para a base toda, e não só para a página.
    """
    coluna = _COLUNAS_ORDENAVEIS.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Campo de ordenação inválido. Use data_nota, numero_nota, "
                "valor_total ou data_prevista_entrega."
            ),
        )

    hoje = hoje or date.today()
    ordenacao = coluna.desc() if sort_type.lower() == "desc" else coluna.asc()

    consulta = (
        sessao_db.query(EntregaNota)
        .filter(EntregaNota.sync_deleted_at.is_(None))
        .options(
            joinedload(EntregaNota.entrega),
            # A listagem devolve resumo: carregar itens e interações de 20
            # notas seriam centenas de linhas que a tela não mostra.
            noload(EntregaNota.itens),
            noload(EntregaNota.interacoes),
        )
    )

    consulta = _aplicar_filtros(sessao_db, consulta, filtros)

    # Sem `entregas.ver_todas`, o vendedor enxerga apenas as notas em que ele é
    # o vendedor. Mesma regra do `visualiza_vendas_proprias` do sistema antigo,
    # e o mesmo desenho da visibilidade por atribuição da expedição.
    if apenas_vendedor_id:
        consulta = consulta.filter(EntregaNota.vendedor_id == apenas_vendedor_id)

    # O período é sempre a DATA DA NOTA — data de negócio do documento, nunca
    # sync_updated_at, que muda a cada reprocessamento da integração.
    if data_inicio:
        consulta = consulta.filter(
            EntregaNota.data_nota >= datetime.combine(data_inicio, time.min)
        )
    if data_fim:
        consulta = consulta.filter(EntregaNota.data_nota <= datetime.combine(data_fim, time.max))

    if status_prazo:
        consulta = _filtrar_status_prazo(consulta, status_prazo, hoje)

    q = (q or "").strip()
    if q:
        termo = f"%{q}%"
        consulta = consulta.filter(
            or_(
                EntregaNota.numero_nota.ilike(termo),
                EntregaNota.pedido.ilike(termo),
                EntregaNota.cliente_nome.ilike(termo),
                EntregaNota.cliente_cidade.ilike(termo),
                EntregaNota.transportadora_nome.ilike(termo),
            )
        )

    total = consulta.count()
    notas = (
        # Desempate por id: sem ele, duas páginas podem repetir ou pular uma
        # linha quando várias têm o mesmo valor na coluna ordenada.
        consulta.order_by(ordenacao, EntregaNota.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return _montar_resumos(sessao_db, notas, hoje), total


def _aplicar_filtros(sessao_db: Session, consulta, filtros: FiltrosListagemSchema | None):
    """Aplica o painel de filtros à consulta, campo a campo.

    Dentro de um campo os valores são OU (`IN`); entre campos é E — que é como
    se lê um painel de filtros, e é o que a tela mostra. Campo com lista vazia
    não entra na consulta.
    """
    if filtros is None:
        return consulta

    for campo, coluna in _FILTROS_DA_NOTA.items():
        valores = getattr(filtros, campo)
        if valores:
            consulta = consulta.filter(coluna.in_(valores))

    for campo, coluna in _FILTROS_DE_DATA_DA_NOTA.items():
        valores = getattr(filtros, campo)
        if valores:
            consulta = consulta.filter(func.date(coluna).in_(valores))

    for campo, expressao in _FILTROS_DERIVADOS_DA_NOTA.items():
        valores = getattr(filtros, campo)
        if valores:
            consulta = consulta.filter(expressao().in_(valores))

    # Mapa de carga: `.has()` e não join. Nota sem mapa é caso normal ("sem
    # mapa" é até uma das abas da tela), e um join com `entregas` sumiria com
    # ela do resultado mesmo quando ninguém filtrou por mapa.
    for campo, coluna in _FILTROS_DO_MAPA.items():
        valores = getattr(filtros, campo)
        if valores:
            consulta = consulta.filter(EntregaNota.entrega.has(coluna.in_(valores)))
    for campo, coluna in _FILTROS_DE_DATA_DO_MAPA.items():
        valores = getattr(filtros, campo)
        if valores:
            consulta = consulta.filter(EntregaNota.entrega.has(func.date(coluna).in_(valores)))

    # Itens: `.any()` vira EXISTS. Com join, uma nota de 30 itens apareceria 30
    # vezes — o total do rodapé mentiria e a paginação repetiria linhas.
    for campo, coluna in _FILTROS_DO_ITEM.items():
        valores = getattr(filtros, campo)
        if valores:
            consulta = consulta.filter(
                EntregaNota.itens.any(
                    coluna.in_(valores) & (EntregaNotaItem.sync_deleted_at.is_(None))
                )
            )

    # Empresa e vendedor chegam pelo NOME, que é o que a tela mostra e o que o
    # autocomplete ofereceu. O id fica escondido: traduzimos nome -> ids pela
    # borda pública do domínio dono e filtramos pela FK. Consultar `empresas` ou
    # `usuarios` daqui seria query em tabela alheia (ver ARCHITECTURE.md →
    # "Regras de import entre domínios").
    if filtros.empresa:
        escolhidas = {valor.strip().lower() for valor in filtros.empresa}
        ids = [
            resumo.id
            for resumo in empresa_publico.listar_resumo(sessao_db)
            if (resumo.apelido or resumo.nome or "").strip().lower() in escolhidas
        ]
        # Lista vazia é deliberada: a pessoa filtrou por uma empresa que não
        # existe mais. Devolver nenhuma nota é a resposta honesta — ignorar o
        # filtro devolveria a base inteira como se ela não tivesse filtrado.
        consulta = consulta.filter(EntregaNota.empresa_id.in_(ids))

    if filtros.vendedor:
        escolhidos = {valor.strip().lower() for valor in filtros.vendedor}
        ids = [
            usuario_id
            for usuario_id, nome in _nomes_de_vendedores(sessao_db).items()
            if nome.strip().lower() in escolhidos
        ]
        consulta = consulta.filter(EntregaNota.vendedor_id.in_(ids))

    return consulta


def _nomes_de_vendedores(sessao_db: Session) -> dict[str, str]:
    """usuario_id -> nome, para os vendedores que aparecem em alguma nota.

    Só os que aparecem: a lista serve para traduzir o que a tela ofereceu, e
    oferecer o cadastro inteiro de usuários mostraria gente que nunca vendeu.
    """
    ids = [
        linha[0]
        for linha in sessao_db.query(EntregaNota.vendedor_id)
        .filter(
            EntregaNota.vendedor_id.isnot(None),
            EntregaNota.sync_deleted_at.is_(None),
        )
        .distinct()
        .all()
    ]
    return usuario_publico.obter_nomes(sessao_db, ids)


def _filtrar_status_prazo(consulta, status_prazo: str, hoje: date):
    if status_prazo == "entregue":
        return consulta.filter(EntregaNota.status_atual == STATUS_ENCERRA_ENTREGA)

    # As demais situações só valem para quem ainda não foi entregue — uma nota
    # entregue com atraso já é passado, e listá-la como "em atraso" faria a
    # tela pedir uma ação que não existe mais.
    consulta = consulta.filter(EntregaNota.status_atual != STATUS_ENCERRA_ENTREGA)

    if status_prazo == "sem_mapa":
        return consulta.filter(EntregaNota.entrega_id.is_(None))
    if status_prazo == "prazo_nao_definido":
        return consulta.filter(
            EntregaNota.entrega_id.isnot(None), EntregaNota.data_prevista_entrega.is_(None)
        )
    if status_prazo == "em_atraso":
        return consulta.filter(EntregaNota.data_prevista_entrega < hoje)
    if status_prazo == "no_prazo":
        return consulta.filter(EntregaNota.data_prevista_entrega >= hoje)
    return consulta


# ---------------------------------------------------------------------------
# Os valores que existem no período — o que alimenta cada autocomplete
# ---------------------------------------------------------------------------


def _base_do_periodo(
    sessao_db: Session,
    data_inicio: date | None,
    data_fim: date | None,
    apenas_vendedor_id: str | None,
):
    """O recorte sobre o qual os valores únicos são calculados.

    É o MESMO recorte da listagem em período e visibilidade — sem isso, um
    vendedor sem `entregas.ver_todas` veria no autocomplete os clientes e as
    transportadoras das notas dos colegas, que ele não pode nem listar. A lista
    de opções vazaria o que a listagem esconde.
    """
    consulta = sessao_db.query(EntregaNota).filter(EntregaNota.sync_deleted_at.is_(None))
    if data_inicio:
        consulta = consulta.filter(
            EntregaNota.data_nota >= datetime.combine(data_inicio, time.min)
        )
    if data_fim:
        consulta = consulta.filter(EntregaNota.data_nota <= datetime.combine(data_fim, time.max))
    if apenas_vendedor_id:
        consulta = consulta.filter(EntregaNota.vendedor_id == apenas_vendedor_id)
    return consulta


def _distintos(
    consulta_base, coluna, termo: str | None, limite: int, texto: bool = True
) -> tuple[list, bool]:
    """Os valores diferentes de uma coluna no recorte, filtrados pelo termo.

    DISTINCT no banco, e não `set()` em Python: o período pode ter centenas de
    milhares de notas, e trazer todas para deduplicar na aplicação carregaria a
    base inteira na memória só para montar um combo.

    O `limite` é pedido com UM A MAIS do que a tela vai mostrar. É assim que se
    sabe se havia mais sem pagar um `COUNT(DISTINCT)` na base inteira: se voltou
    o extra, existe mais coisa lá fora e a tela avisa para refinar a busca.
    """
    consulta = consulta_base.with_entities(coluna).filter(coluna.isnot(None))
    if texto:
        # `!= ""` só vale para coluna de TEXTO. Em coluna de data o MySQL recusa
        # a comparação com 1525 ("Incorrect DATE value: ''") e a requisição
        # morre — e o SQLite dos testes aceita em silêncio, então o teste passa
        # e a tela quebra. Por isso o chamador diz se o campo é texto.
        consulta = consulta.filter(coluna != "")
    if termo:
        # `ilike` com % dos dois lados: quem procura o pedido "5185" não sabe
        # que ele começa com zeros, e quem procura "SANTA CASA" digita o meio do
        # nome do cliente. Prefixo só serviria a campo numérico alinhado.
        #
        # Em coluna de data o `LIKE` compara a representação textual
        # ("2026-08-20"), que é justamente o formato que a tela mostra e envia —
        # digitar "08" acha o mês inteiro.
        consulta = consulta.filter(coluna.ilike(f"%{termo}%"))

    linhas = consulta.distinct().order_by(coluna.asc()).limit(limite + 1).all()
    valores = [linha[0] for linha in linhas]
    return valores[:limite], len(valores) > limite


def _texto_da_opcao(valor) -> str:
    """O valor como a tela mostra e como ela devolve no filtro.

    Tudo vira string porque o autocomplete é um campo de texto e o query param
    é texto — quem converte de volta é o Pydantic, no contrato de entrada.
    `Decimal` passa por `normalize()` para "2000.0000" virar "2000": ninguém
    escolhe quantidade com quatro casas numa lista.
    """
    if isinstance(valor, Decimal):
        normalizado = valor.normalize()
        inteiro = normalizado == normalizado.to_integral()
        return str(normalizado.quantize(Decimal(1)) if inteiro else normalizado)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()[:10]
    return str(valor)


# Teto de sugestões por busca. Não é performance, é usabilidade: ninguém
# escolhe numa lista de 600 pedidos rolando com o mouse — refina o termo. E o
# teto é o que impede a resposta de crescer com o tamanho do período.
LIMITE_SUGESTOES = 50


def _campo_em_snake_case(campo: str) -> str:
    """Aceita o nome do campo como a TELA o conhece: `numeroNota`, não `numero_nota`.

    A tela usa uma chave só para as duas coisas — o parâmetro de filtro
    (`?numeroNota=0116606`) e o `?campo=` das sugestões —, e é esse casamento
    que garante que o valor sugerido é aceito pelo filtro. Como o contrato
    camelCasa os nomes, o que chega aqui é camelCase.

    O de-para sai do próprio contrato, e não de uma lista escrita à mão: campo
    novo passa a ser aceito sozinho, sem ninguém lembrar de atualizar duas
    listas que divergiriam em silêncio.

    snake_case também é aceito, para quem chama a API direto.
    """
    por_alias = {
        (definicao.alias or nome): nome
        for nome, definicao in FiltrosListagemSchema.model_fields.items()
    }
    return por_alias.get(campo, campo)


def sugestoes_de_campo(
    sessao_db: Session,
    campo: str,
    termo: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    apenas_vendedor_id: str | None = None,
    limite: int = LIMITE_SUGESTOES,
) -> SugestoesFiltroSchema:
    """As sugestões de UM campo do painel, filtradas pelo que a pessoa digitou.

    Um endpoint só serve todos os campos: `campo` diz qual, e a tabela de
    filtros lá de cima diz de onde o valor sai. É a mesma definição que o
    filtro usa para recortar — é isso que garante que o valor sugerido é aceito.

    Antes disto a tela carregava TODOS os valores de TODOS os campos de uma vez,
    a cada troca de período. Num mês real isso deu ~600 pedidos e centenas de
    números de nota numa resposta só, e crescia com o intervalo escolhido.

    De propósito, NÃO leva em conta os outros filtros já escolhidos. Se levasse,
    escolher uma transportadora encolheria a lista de cidades, e trocar de ideia
    exigiria limpar tudo antes. As sugestões são do período — elas não se mexem
    enquanto a pessoa monta o filtro.
    """
    base = _base_do_periodo(sessao_db, data_inicio, data_fim, apenas_vendedor_id)
    termo = (termo or "").strip()
    campo = _campo_em_snake_case(campo)

    if campo in _FILTROS_DA_NOTA:
        valores, truncado = _distintos(base, _FILTROS_DA_NOTA[campo], termo, limite)
    elif campo in _FILTROS_DE_DATA_DA_NOTA:
        valores, truncado = _distintos(
            base, func.date(_FILTROS_DE_DATA_DA_NOTA[campo]), termo, limite, texto=False
        )
    elif campo in _FILTROS_DERIVADOS_DA_NOTA:
        valores, truncado = _distintos(base, _FILTROS_DERIVADOS_DA_NOTA[campo](), termo, limite)
    elif campo in _FILTROS_DO_MAPA or campo in _FILTROS_DE_DATA_DO_MAPA:
        e_data = campo in _FILTROS_DE_DATA_DO_MAPA
        coluna = (
            func.date(_FILTROS_DE_DATA_DO_MAPA[campo]) if e_data else _FILTROS_DO_MAPA[campo]
        )
        valores, truncado = _distintos(
            _base_do_mapa(sessao_db, base), coluna, termo, limite, texto=not e_data
        )
    elif campo in _FILTROS_DO_ITEM:
        valores, truncado = _distintos(
            _base_do_item(sessao_db, base), _FILTROS_DO_ITEM[campo], termo, limite
        )
    elif campo == "empresa":
        valores, truncado = _nomes_de_empresas(sessao_db, base, termo, limite)
    elif campo == "vendedor":
        valores, truncado = _nomes_de_vendedores_do_periodo(sessao_db, base, termo, limite)
    else:
        # Conjunto fechado, como `_COLUNAS_ORDENAVEIS`: `campo` vem da query
        # string, e aceitar qualquer nome abriria a porta para pedir uma coluna
        # que a tela não deveria expor.
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Campo de filtro desconhecido: '{campo}'.",
        )

    return SugestoesFiltroSchema(
        campo=campo, valores=[_texto_da_opcao(v) for v in valores], truncado=truncado
    )


def _base_do_mapa(sessao_db: Session, base):
    """O mapa de carga das notas do período. O recorte entra como subconsulta de
    ids — a mesma base da listagem, sem repetir os filtros dela aqui."""
    return (
        sessao_db.query(Entrega)
        .join(EntregaNota, EntregaNota.entrega_id == Entrega.id)
        .filter(
            EntregaNota.id.in_(base.with_entities(EntregaNota.id)),
            Entrega.sync_deleted_at.is_(None),
        )
    )


def _base_do_item(sessao_db: Session, base):
    return sessao_db.query(EntregaNotaItem).filter(
        EntregaNotaItem.entrega_nota_id.in_(base.with_entities(EntregaNota.id)),
        EntregaNotaItem.sync_deleted_at.is_(None),
    )


def _nomes_de_empresas(sessao_db: Session, base, termo: str, limite: int) -> tuple[list, bool]:
    """Empresa vem pelo NOME, que é o que a tela mostra — nunca pelo UUID.

    O recorte pelo termo acontece em Python, e aqui isso é correto: são poucas
    empresas (uma matriz e suas filiais), elas vêm de uma consulta só pela borda
    pública, e filtrar no banco exigiria consultar `empresas` daqui — query em
    tabela alheia, proibida (ver ARCHITECTURE.md → "Regras de import").
    """
    ids = {linha[0] for linha in base.with_entities(EntregaNota.empresa_id).distinct()}
    resumos = empresa_publico.obter_resumos(sessao_db, list(ids))
    nomes = sorted(
        {(r.apelido or r.nome) for r in resumos.values() if (r.apelido or r.nome)}
    )
    return _recortar_em_python(nomes, termo, limite)


def _nomes_de_vendedores_do_periodo(
    sessao_db: Session, base, termo: str, limite: int
) -> tuple[list, bool]:
    """Mesma razão da empresa: o nome mora em `usuarios` e vem pela borda.

    Só os vendedores que APARECEM em alguma nota do período — oferecer o
    cadastro inteiro mostraria gente que nunca vendeu.
    """
    ids = [
        linha[0]
        for linha in base.with_entities(EntregaNota.vendedor_id).distinct()
        if linha[0] is not None
    ]
    nomes = sorted(set(usuario_publico.obter_nomes(sessao_db, ids).values()))
    return _recortar_em_python(nomes, termo, limite)


def _recortar_em_python(valores: list[str], termo: str, limite: int) -> tuple[list, bool]:
    if termo:
        alvo = termo.lower()
        valores = [v for v in valores if alvo in v.lower()]
    return valores[:limite], len(valores) > limite


def _contar_interacoes(sessao_db: Session, nota_ids: list[str]) -> dict[str, int]:
    """Uma query agregada para a página inteira, em vez de carregar as
    interações de cada nota só para chamar len()."""
    if not nota_ids:
        return {}
    linhas = (
        sessao_db.query(
            EntregaNotaInteracao.entrega_nota_id, func.count(EntregaNotaInteracao.id)
        )
        .filter(
            EntregaNotaInteracao.entrega_nota_id.in_(nota_ids),
            EntregaNotaInteracao.sync_deleted_at.is_(None),
        )
        .group_by(EntregaNotaInteracao.entrega_nota_id)
        .all()
    )
    return {nota_id: qtd for nota_id, qtd in linhas}


def _montar_resumos(
    sessao_db: Session, notas: list[EntregaNota], hoje: date
) -> list[EntregaNotaResumoSchema]:
    contagens = _contar_interacoes(sessao_db, [n.id for n in notas])
    nomes = usuario_publico.obter_nomes(
        sessao_db, [n.vendedor_id for n in notas if n.vendedor_id]
    )
    # Uma consulta para a página inteira, pela borda de `empresas` — não uma
    # por linha, e nunca um join na tabela do outro domínio.
    empresas = empresa_publico.obter_resumos(sessao_db, [n.empresa_id for n in notas])
    return [
        _para_resumo(nota, hoje, contagens.get(nota.id, 0), nomes, empresas) for nota in notas
    ]


def _apelido_da_empresa(empresa_id: str, empresas: dict) -> str | None:
    """O apelido, caindo no nome fantasia quando não há apelido cadastrado.

    Cair no nome fantasia é melhor que mostrar vazio: a coluna existe para
    dizer de qual filial é a entrega, e uma célula em branco não diz nada.
    """
    resumo = empresas.get(empresa_id)
    return (resumo.apelido or resumo.nome) if resumo else None


def _para_resumo(
    nota: EntregaNota,
    hoje: date,
    qtd_interacoes: int,
    nomes: dict[str, str],
    empresas: dict | None = None,
) -> EntregaNotaResumoSchema:
    entrega = nota.entrega
    return EntregaNotaResumoSchema(
        id=nota.id,
        empresa_id=nota.empresa_id,
        empresa_apelido=_apelido_da_empresa(nota.empresa_id, empresas or {}),
        numero_nota=nota.numero_nota,
        serie=nota.serie,
        pedido=nota.pedido,
        tipo_nota=nota.tipo_nota,
        data_nota=nota.data_nota,
        situacao=nota.situacao,
        valor_total=float(nota.valor_total or 0),
        cliente_nome=nota.cliente_nome,
        cliente_cidade=nota.cliente_cidade,
        cliente_uf=nota.cliente_uf,
        vendedor_id=nota.vendedor_id,
        vendedor_nome=nomes.get(nota.vendedor_id) if nota.vendedor_id else None,
        transportadora_nome=nota.transportadora_nome,
        termolabil=nota.termolabil,
        numero_mapa=entrega.numero_mapa if entrega else None,
        data_mapa=entrega.data_mapa if entrega else None,
        prazo_dias=nota.prazo_dias,
        data_prevista_entrega=nota.data_prevista_entrega,
        status_atual=nota.status_atual,
        status_prazo=entrega_prazo.calcular_status_prazo(
            data_mapa=entrega.data_mapa.date() if entrega and entrega.data_mapa else None,
            data_prevista=nota.data_prevista_entrega,
            entregue=nota.status_atual == STATUS_ENCERRA_ENTREGA,
            hoje=hoje,
        ),
        data_entrega_realizada=nota.data_entrega_realizada,
        qtd_interacoes=qtd_interacoes,
    )


def obter_por_id(
    sessao_db: Session, nota_id: str, apenas_vendedor_id: str | None = None
) -> EntregaNota:
    consulta = sessao_db.query(EntregaNota).filter(
        EntregaNota.id == nota_id, EntregaNota.sync_deleted_at.is_(None)
    )
    # A restrição de visibilidade vale também no acesso direto por id: sem
    # isso, quem não pode ver a nota na lista veria colando a URL.
    if apenas_vendedor_id:
        consulta = consulta.filter(EntregaNota.vendedor_id == apenas_vendedor_id)

    nota = consulta.first()
    if nota is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Nota de entrega não encontrada."
        )
    return nota


def _notas_de_devolucao(
    sessao_db: Session, nota: EntregaNota, apenas_vendedor_id: str | None
) -> list[NotaDevolucaoSchema]:
    """As notas que DEVOLVEM esta — achadas pela chave de acesso.

    O vínculo é `chave_acesso_referenciada` da devolução apontando para
    `chave_acesso_nota` desta. A busca é pela chave inteira, e não pelo número
    extraído dela: o número se repete entre empresas e séries, e casar por ele
    juntaria a devolução da filial com a nota da matriz.

    Sem chave nesta nota não há por onde ninguém apontar para ela — devolve
    vazio em vez de casar `NULL` com `NULL`, que traria toda nota sem chave.

    Respeita a mesma visibilidade da listagem: um vendedor sem
    `entregas.ver_todas` não pode ver, pela seção de devoluções, uma nota que a
    listagem esconde dele.
    """
    if not nota.chave_acesso_nota:
        return []

    consulta = sessao_db.query(EntregaNota).filter(
        EntregaNota.chave_acesso_referenciada == nota.chave_acesso_nota,
        EntregaNota.sync_deleted_at.is_(None),
        # Uma nota que referencia a si mesma é erro de integração, não uma
        # devolução. Aparecer na própria seção confundiria mais que ajudaria.
        EntregaNota.id != nota.id,
    )
    if apenas_vendedor_id:
        consulta = consulta.filter(EntregaNota.vendedor_id == apenas_vendedor_id)

    return [
        NotaDevolucaoSchema(
            id=devolucao.id,
            numero_nota=devolucao.numero_nota,
            serie=devolucao.serie,
            data_nota=devolucao.data_nota,
            tipo_nota=devolucao.tipo_nota,
            situacao=devolucao.situacao,
            valor_total=float(devolucao.valor_total or 0),
            chave_acesso_nota=devolucao.chave_acesso_nota,
            status_atual=devolucao.status_atual,
        )
        # Mais recente primeiro: quando houve mais de uma devolução parcial, a
        # última é a que explica o saldo de hoje.
        for devolucao in consulta.order_by(
            EntregaNota.data_nota.desc(), EntregaNota.numero_nota.desc()
        ).all()
    ]


def montar_resposta(
    sessao_db: Session,
    nota: EntregaNota,
    hoje: date | None = None,
    apenas_vendedor_id: str | None = None,
) -> EntregaNotaRespostaSchema:
    hoje = hoje or date.today()
    interacoes_vivas = [i for i in nota.interacoes if i.sync_deleted_at is None]

    ids_usuarios = [i.usuario_id for i in interacoes_vivas]
    ids_usuarios += [i.editado_por_usuario_id for i in interacoes_vivas if i.editado_por_usuario_id]
    if nota.vendedor_id:
        ids_usuarios.append(nota.vendedor_id)
    nomes = usuario_publico.obter_nomes(sessao_db, ids_usuarios)

    empresas = empresa_publico.obter_resumos(sessao_db, [nota.empresa_id])
    resumo = _para_resumo(nota, hoje, len(interacoes_vivas), nomes, empresas)
    entrega = nota.entrega

    return EntregaNotaRespostaSchema(
        **resumo.model_dump(),
        cliente_codigo=nota.cliente_codigo,
        chave_acesso_nota=nota.chave_acesso_nota,
        chave_acesso_referenciada=nota.chave_acesso_referenciada,
        entrega_id=nota.entrega_id,
        motorista=entrega.motorista if entrega else None,
        placa_veiculo=entrega.placa_veiculo if entrega else None,
        sistema_origem_id=nota.sistema_origem_id,
        itens=[
            {
                "id": item.id,
                "numero_item": item.numero_item,
                "produto_codigo": item.produto_codigo,
                "produto_descricao": item.produto_descricao,
                "marca_nome": item.marca_nome,
                "quantidade": float(item.quantidade or 0),
                "preco_unitario": float(item.preco_unitario or 0),
                "valor_total": float(item.valor_total or 0),
                "lote": item.lote,
                "validade": item.validade,
                "quantidade_devolvida": float(item.quantidade_devolvida or 0),
                "observacao": item.observacao,
            }
            for item in nota.itens
            if item.sync_deleted_at is None
        ],
        interacoes=[_para_interacao(i, nomes) for i in interacoes_vivas],
        notas_devolucao=_notas_de_devolucao(sessao_db, nota, apenas_vendedor_id),
    )


def _para_interacao(
    interacao: EntregaNotaInteracao, nomes: dict[str, str]
) -> InteracaoRespostaSchema:
    return InteracaoRespostaSchema(
        id=interacao.id,
        status=interacao.status,
        observacao=interacao.observacao,
        usuario_id=interacao.usuario_id,
        usuario_nome=nomes.get(interacao.usuario_id, "Usuário não identificado"),
        data_interacao=interacao.data_interacao,
        editado_em=interacao.editado_em,
        editado_por_nome=(
            nomes.get(interacao.editado_por_usuario_id)
            if interacao.editado_por_usuario_id
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Interações (a timeline)
# ---------------------------------------------------------------------------


def registrar_interacao(
    sessao_db: Session,
    nota_id: str,
    dados: InteracaoCriarSchema,
    usuario_id: str,
    apenas_vendedor_id: str | None = None,
) -> EntregaNota:
    nota = obter_por_id(sessao_db, nota_id, apenas_vendedor_id)

    interacao = EntregaNotaInteracao(
        entrega_nota_id=nota.id,
        sequencia=_proxima_sequencia(sessao_db, nota.id),
        # Preenchida explicitamente com o instante da inclusão. Não é herdada
        # de sync_created_at: é campo de negócio, e o dia em que existir
        # lançamento retroativo é aqui que a data informada vai entrar.
        data_interacao=datetime.now(),
        status=dados.status,
        observacao=dados.observacao.strip(),
        usuario_id=usuario_id,
    )
    sessao_db.add(interacao)
    sessao_db.flush()

    _recalcular_status_atual(sessao_db, nota)
    sessao_db.commit()
    sessao_db.refresh(nota)
    return nota


def atualizar_interacao(
    sessao_db: Session,
    nota_id: str,
    interacao_id: str,
    dados: InteracaoAtualizarSchema,
    usuario_id: str,
    apenas_vendedor_id: str | None = None,
) -> EntregaNota:
    """Edita uma interação já lançada.

    Não mexe em `data_interacao` nem em `sequencia`: a posição do evento na
    timeline é a data em que ele aconteceu, e corrigir um texto de ontem não
    pode empurrar aquele evento para o topo de hoje. O que muda é
    `editado_em`/`editado_por`, que a tela mostra ao lado do card.
    """
    nota = obter_por_id(sessao_db, nota_id, apenas_vendedor_id)
    interacao = _obter_interacao(sessao_db, nota.id, interacao_id)

    interacao.status = dados.status
    interacao.observacao = dados.observacao.strip()
    interacao.editado_por_usuario_id = usuario_id
    interacao.editado_em = datetime.now()
    incrementar_versao(interacao)

    _recalcular_status_atual(sessao_db, nota)
    sessao_db.commit()
    sessao_db.refresh(nota)
    return nota


def apagar_interacao(
    sessao_db: Session,
    nota_id: str,
    interacao_id: str,
    apenas_vendedor_id: str | None = None,
) -> EntregaNota:
    nota = obter_por_id(sessao_db, nota_id, apenas_vendedor_id)
    interacao = _obter_interacao(sessao_db, nota.id, interacao_id)

    marcar_apagado(interacao)
    sessao_db.flush()
    # Apagar o último evento faz o status voltar para o anterior — o status da
    # nota é sempre o do evento mais recente que ainda existe.
    _recalcular_status_atual(sessao_db, nota)
    sessao_db.commit()
    sessao_db.refresh(nota)
    return nota


def _proxima_sequencia(sessao_db: Session, nota_id: str) -> int:
    """Conta a partir do maior número JÁ USADO na nota, incluindo interações
    apagadas: reaproveitar a sequência de um evento excluído colidiria com
    `uq_entrega_nota_interacoes_sequencia`, que não filtra soft delete."""
    maior = (
        sessao_db.query(func.max(EntregaNotaInteracao.sequencia))
        .filter(EntregaNotaInteracao.entrega_nota_id == nota_id)
        .scalar()
    )
    return (maior or 0) + 1


def _obter_interacao(
    sessao_db: Session, nota_id: str, interacao_id: str
) -> EntregaNotaInteracao:
    interacao = (
        sessao_db.query(EntregaNotaInteracao)
        .filter(
            EntregaNotaInteracao.id == interacao_id,
            # Confere que a interação é DESTA nota: sem isso, um id de outra
            # nota (que o usuário talvez nem pudesse ver) seria editável pela
            # URL desta.
            EntregaNotaInteracao.entrega_nota_id == nota_id,
            EntregaNotaInteracao.sync_deleted_at.is_(None),
        )
        .first()
    )
    if interacao is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Interação não encontrada."
        )
    return interacao


def _recalcular_status_atual(sessao_db: Session, nota: EntregaNota) -> None:
    """Reescreve `status_atual` a partir do último evento vivo.

    A coluna é derivada — a verdade é a timeline. Ela existe porque a listagem
    filtra por status sobre a base inteira, e buscar o último evento de cada
    nota por subquery não escala. Recalcular sempre (em vez de só na inclusão)
    é o que mantém a coluna correta quando uma interação é editada ou apagada.
    """
    ultima = (
        sessao_db.query(EntregaNotaInteracao)
        .filter(
            EntregaNotaInteracao.entrega_nota_id == nota.id,
            EntregaNotaInteracao.sync_deleted_at.is_(None),
        )
        # Pela sequência, não pela data: duas interações no mesmo segundo
        # empatam em data_interacao (DATETIME tem resolução de segundo), e o
        # desempate por id (UUID) escolheria o evento errado. Ver o comentário
        # em EntregaNotaInteracao.sequencia.
        .order_by(EntregaNotaInteracao.sequencia.desc())
        .first()
    )

    nota.status_atual = ultima.status if ultima else "aguardando_embarque"
    # A data da entrega é a do EVENTO, não a de quando a linha foi gravada.
    nota.data_entrega_realizada = (
        ultima.data_interacao
        if ultima and ultima.status == STATUS_ENCERRA_ENTREGA
        else None
    )
    incrementar_versao(nota)
