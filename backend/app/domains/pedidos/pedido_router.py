from app.shared.router_base import RouterBase
from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.pedidos import pedido_service
from app.domains.pedidos.pedido_model import Pedido
from app.domains.pedidos.pedido_contrato import (
    PedidoListaPaginadaSchema,
    PedidoAtualizarSchema,
    PedidoCriarSchema,
    PedidoRespostaSchema,
    PedidoStatusRespostaSchema,
)

router = RouterBase(prefix="/pedidos", tags=["Pedidos"])


@router.get("/status", response_model=list[PedidoStatusRespostaSchema], summary="Lista o catálogo de status de pedido")
def listar_status(
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("pedidos.acessar")),
) -> list[PedidoStatusRespostaSchema]:
    return [
        PedidoStatusRespostaSchema(id=s.id, chave=s.chave) for s in pedido_service.listar_status(sessao_db)
    ]


def _para_resposta(pedido: Pedido) -> PedidoRespostaSchema:
    return PedidoRespostaSchema(
        id=pedido.id,
        numero=pedido.numero,
        data_pedido=pedido.data_pedido,
        cliente_id=pedido.cliente_id,
        empresa_id=pedido.empresa_id,
        vendedor_id=pedido.vendedor_id,
        # montado a partir do snapshot gravado no próprio pedido — o formato
        # do JSON continua idêntico ao que o front já consome.
        cliente={
            "id": pedido.cliente_id,
            "nome_fantasia": pedido.cliente_nome_fantasia,
            "cnpj": pedido.cliente_cnpj,
        },
        sistema_origem_id=pedido.sistema_origem_id,
        liberado_em=pedido.liberado_em,
        itens=[
            {
                "id": item.id,
                "produto_id": item.produto_id,
                "produto_codigo": item.produto_codigo,
                "produto_descricao": item.produto_descricao,
                "quantidade": item.quantidade,
                "preco_unitario": item.preco_unitario,
                "endereco_produto": item.endereco_produto,
                "lote": item.lote,
            }
            for item in pedido.itens
        ],
        status=pedido.status.chave,
        status_id=pedido.status_id,
        observacoes=pedido.observacoes,
        criado_em=pedido.sync_created_at,
    )


@router.get("", response_model=PedidoListaPaginadaSchema, summary="Lista paginada de pedidos")
def listar(
    page: int = 1,
    # Alias camelCase: o `RouterBase` só camelCasa a RESPOSTA, então o nome do
    # query param precisa ser declarado aqui para bater com o que o front manda.
    # Sem isso o parâmetro é silenciosamente ignorado e vale sempre o default.
    per_page: int = Query(default=20, alias="perPage"),
    sort: str = "data_pedido",
    sort_type: str = Query(default="desc", alias="sortType"),
    q: str | None = Query(default=None, description="Termo de busca: número, sistema de origem ou cliente"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("pedidos.acessar")),
) -> PedidoListaPaginadaSchema:
    # Teto de 100 igual aos outros domínios: é a página que protege o navegador
    # e a API de uma listagem de centenas de milhares.
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    itens, total = pedido_service.listar_paginado(sessao_db, page, per_page, sort, sort_type, q)
    return PedidoListaPaginadaSchema(
        items=[_para_resposta(o) for o in itens],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.get("/{pedido_id}", response_model=PedidoRespostaSchema, summary="Obtém um orçamento pelo id")
def obter(
    pedido_id: str,
    sistema_origem_id: str | None = Query(default=None, description="Se informado, busca o pedido por esse campo em vez do id da URL"),
    # O par (sistemaOrigemId, empresa) é que identifica um pedido — o número
    # sozinho existe em mais de uma filial. No PUT a empresa vem no corpo; aqui,
    # que não tem corpo, ela precisa vir na query string.
    empresa_id: str | None = Query(default=None, alias="empresaId"),
    empresa_sistema_origem_id: str | None = Query(default=None, alias="empresaSistemaOrigemId"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("pedidos.acessar")),
) -> PedidoRespostaSchema:
    if sistema_origem_id:
        pedido = pedido_service.obter_por_sistema_origem_id(
            sessao_db,
            sistema_origem_id,
            pedido_service.resolver_empresa(sessao_db, empresa_id, empresa_sistema_origem_id),
        )
    else:
        pedido = pedido_service.obter_por_id(sessao_db, pedido_id)
    return _para_resposta(pedido)


@router.post("", response_model=PedidoRespostaSchema, status_code=201, summary="Cria um novo orçamento")
def criar(
    dados: PedidoCriarSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("pedidos.gravar.incluir")),
) -> PedidoRespostaSchema:
    return _para_resposta(pedido_service.criar(sessao_db, dados))


@router.put("/{pedido_id}", response_model=PedidoRespostaSchema, summary="Atualiza um orçamento existente")
def atualizar(
    pedido_id: str,
    dados: PedidoAtualizarSchema,
    sistema_origem_id: str | None = Query(default=None, description="Se informado, identifica o pedido por esse campo em vez do id da URL"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("pedidos.gravar.editar")),
) -> PedidoRespostaSchema:
    return _para_resposta(pedido_service.atualizar(sessao_db, pedido_id, dados, sistema_origem_id))


@router.delete("/{pedido_id}", status_code=204, summary="Remove (soft delete) um orçamento")
def apagar(
    pedido_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("pedidos.apagar")),
) -> None:
    pedido_service.apagar(sessao_db, pedido_id)
