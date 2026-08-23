from app.shared.router_base import RouterBase
from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.produtos import produto_service
from app.domains.produtos.produto_model import Produto
from app.domains.produtos.produto_contrato import (
    ConflitoCodigoBarrasSchema,
    ProdutoAtualizarSchema,
    ProdutoCriarSchema,
    ProdutoListaPaginadaSchema,
    ProdutoRespostaSchema,
    VincularAnvisaRespostaSchema,
    VincularAnvisaSchema,
)

router = RouterBase(prefix="/produtos", tags=["Produtos"])


def _para_resposta(produto: Produto) -> ProdutoRespostaSchema:
    return ProdutoRespostaSchema(
        id=produto.id,
        codigo=produto.codigo,
        descricao=produto.descricao,
        unidade=produto.unidade,
        codigo_barra_notas=produto.codigo_barra_notas,
        codigos_barras_logistica=[linha.codigo for linha in produto.codigos_barras_logistica],
        dun_14=produto.dun_14,
        quantidade_multipla_venda=produto.quantidade_multipla_venda,
        registro_anvisa=produto.registro_anvisa,
        marca_id=produto.marca_id,
        marca_nome=produto.marca.nome,
        sistema_origem_id=produto.sistema_origem_id,
        ativo=produto.ativo,
        criado_em=produto.sync_created_at,
    )


@router.get("", response_model=ProdutoListaPaginadaSchema, summary="Lista produtos")
def listar(
    page: int = 1,
    # Alias camelCase: o `RouterBase` só camelCasa a RESPOSTA, então o nome do
    # query param precisa ser declarado aqui para bater com o que o front manda.
    # Sem o alias, `perPage` era ignorado e valia sempre o default 20.
    per_page: int = Query(default=20, alias="perPage"),
    sort: str = "descricao",
    sort_type: str = Query(default="asc", alias="sortType"),
    q: str | None = Query(default=None, description="Termo de busca: código ou descrição"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("produtos.acessar")),
) -> ProdutoListaPaginadaSchema:
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    itens, total = produto_service.listar_paginado(sessao_db, page, per_page, sort, sort_type, q)
    return ProdutoListaPaginadaSchema(
        items=[_para_resposta(p) for p in itens],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.get("/{produto_id}", response_model=ProdutoRespostaSchema, summary="Obtém um produto pelo id")
def obter(
    produto_id: str,
    sistema_origem_id: str | None = Query(default=None, description="Se informado, busca o produto por esse campo em vez do id da URL"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("produtos.acessar")),
) -> ProdutoRespostaSchema:
    produto = (
        produto_service.obter_por_sistema_origem_id(sessao_db, sistema_origem_id)
        if sistema_origem_id
        else produto_service.obter_por_id(sessao_db, produto_id)
    )
    return _para_resposta(produto)


@router.post("", response_model=ProdutoRespostaSchema, status_code=201, summary="Cria um novo produto")
def criar(
    dados: ProdutoCriarSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("produtos.gravar.incluir")),
) -> ProdutoRespostaSchema:
    return _para_resposta(produto_service.criar(sessao_db, dados))


@router.put("/{produto_id}", response_model=ProdutoRespostaSchema, summary="Atualiza um produto existente")
def atualizar(
    produto_id: str,
    dados: ProdutoAtualizarSchema,
    sistema_origem_id: str | None = Query(default=None, description="Se informado, identifica o produto por esse campo em vez do id da URL"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("produtos.gravar.editar")),
) -> ProdutoRespostaSchema:
    return _para_resposta(produto_service.atualizar(sessao_db, produto_id, dados, sistema_origem_id))


@router.delete("/{produto_id}", status_code=204, summary="Remove (soft delete) um produto")
def apagar(
    produto_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("produtos.apagar")),
) -> None:
    produto_service.apagar(sessao_db, produto_id)


@router.post(
    "/{produto_id}/codigos-barras/anvisa",
    response_model=VincularAnvisaRespostaSchema,
    summary="Confere o código lido contra a CMED e vincula os EANs do registro",
)
def vincular_codigos_da_anvisa(
    produto_id: str,
    dados: VincularAnvisaSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(
        exigir_permissao("produtos.codigo_barras.vincular_anvisa")
    ),
) -> VincularAnvisaRespostaSchema:
    """Chave própria, e não `produtos.gravar.editar`: quem usa isto é o operador
    do coletor, com a caixa na mão, e ele não tem (nem deve ter) acesso de
    edição ao cadastro de produtos. A escrita que esta chave libera é estreita —
    só códigos publicados pela CMED para o registro do próprio produto, e só
    quando o código lido confere (ver `vincular_codigos_da_anvisa` no service).

    O endpoint é do domínio de PRODUTOS mesmo sendo acionado pela tela de
    expedição: quem grava em `produto_codigo_barras` é o dono da tabela. A
    expedição não escreve no cadastro (ver ARCHITECTURE.md → "Regras de import
    entre domínios").
    """
    resultado = produto_service.vincular_codigos_da_anvisa(
        sessao_db, produto_id, dados.codigo_barras
    )
    return VincularAnvisaRespostaSchema(
        situacao=resultado.situacao,
        mensagem=resultado.mensagem,
        codigos_vinculados=list(resultado.vinculados),
        conflitos=[
            ConflitoCodigoBarrasSchema(
                codigo=conflito.codigo,
                produto_id=conflito.produto_id,
                produto_codigo=conflito.produto_codigo,
                produto_descricao=conflito.produto_descricao,
            )
            for conflito in resultado.conflitos
        ],
    )
