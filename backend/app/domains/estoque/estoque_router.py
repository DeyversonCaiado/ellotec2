"""
Camada HTTP do domínio de estoque.

Dois recursos, um router (é um domínio só): `/estoque/saldos` para a tabela
`estoque` e `/estoque/lotes` para `estoque_lotes`.

O PUT sem id na URL é o caminho da integração: ela reenvia o saldo inteiro toda
vez e localiza a linha pela chave natural (empresa + produto [+ lote]), sem ter
que guardar o UUID daqui do lado dela.
"""

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.estoque import estoque_service
from app.domains.estoque.estoque_contrato import (
    LoteEntradaSchema,
    LoteListaPaginadaSchema,
    LoteRespostaSchema,
    SaldoEntradaSchema,
    SaldoListaPaginadaSchema,
    SaldoRespostaSchema,
)
from app.domains.estoque.estoque_model import Estoque, EstoqueLote
from app.shared.router_base import RouterBase

router = RouterBase(prefix="/estoque", tags=["Estoque"])


def _saldo_para_resposta(saldo: Estoque, produto=None) -> SaldoRespostaSchema:
    return SaldoRespostaSchema(
        id=saldo.id,
        produto_id=saldo.produto_id,
        produto_codigo=produto.codigo if produto else "",
        produto_descricao=produto.descricao if produto else "",
        empresa_id=saldo.empresa_id,
        quantidade=float(saldo.quantidade),
        sistema_origem_id=saldo.sistema_origem_id,
        empresa_sistema_origem_id=saldo.empresa_sistema_origem_id,
        criado_em=saldo.sync_created_at,
    )


def _lote_para_resposta(lote: EstoqueLote, produto=None) -> LoteRespostaSchema:
    return LoteRespostaSchema(
        id=lote.id,
        produto_id=lote.produto_id,
        produto_codigo=produto.codigo if produto else "",
        produto_descricao=produto.descricao if produto else "",
        empresa_id=lote.empresa_id,
        lote=lote.lote,
        quantidade=float(lote.quantidade),
        fabricacao=lote.fabricacao,
        vencimento=lote.vencimento,
        sistema_origem_id=lote.sistema_origem_id,
        empresa_sistema_origem_id=lote.empresa_sistema_origem_id,
        criado_em=lote.sync_created_at,
    )


def _com_produto(sessao_db: Session, registro, para_resposta):
    """Resposta de item único já com código e descrição do produto — as
    listagens resolvem isso em lote; aqui é uma linha só."""
    return para_resposta(registro, estoque_service.identificar_produto(sessao_db, registro.produto_id))


def _pagina(page: int, per_page: int) -> tuple[int, int]:
    return max(page, 1), min(max(per_page, 1), 100)


# --------------------------------------------------------------------------
# Saldo total (tabela `estoque`)
# --------------------------------------------------------------------------
@router.get("/saldos", response_model=SaldoListaPaginadaSchema, summary="Lista o saldo por produto")
def listar_saldos(
    page: int = 1,
    per_page: int = 20,
    sort: str = "sync_updated_at",
    sort_type: str = "desc",
    empresa_id: str | None = Query(default=None),
    produto_id: str | None = Query(default=None),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("estoque.acessar")),
) -> SaldoListaPaginadaSchema:
    page, per_page = _pagina(page, per_page)
    itens, total, produtos = estoque_service.listar_saldos(
        sessao_db, page, per_page, sort, sort_type, empresa_id, produto_id
    )
    return SaldoListaPaginadaSchema(
        items=[_saldo_para_resposta(item, produtos.get(item.produto_id)) for item in itens],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.post("/saldos", response_model=SaldoRespostaSchema, status_code=201, summary="Cria o saldo de um produto")
def criar_saldo(
    dados: SaldoEntradaSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("estoque.gravar.incluir")),
) -> SaldoRespostaSchema:
    return _com_produto(sessao_db, estoque_service.criar_saldo(sessao_db, dados), _saldo_para_resposta)


@router.put("/saldos", response_model=SaldoRespostaSchema, summary="Atualiza o saldo pela chave natural (empresa + produto)")
def atualizar_saldo_por_chave(
    dados: SaldoEntradaSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("estoque.gravar.editar")),
) -> SaldoRespostaSchema:
    return _com_produto(sessao_db, estoque_service.atualizar_saldo(sessao_db, None, dados), _saldo_para_resposta)


@router.get("/saldos/{saldo_id}", response_model=SaldoRespostaSchema, summary="Obtém um saldo pelo id")
def obter_saldo(
    saldo_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("estoque.acessar")),
) -> SaldoRespostaSchema:
    return _com_produto(sessao_db, estoque_service.obter_saldo(sessao_db, saldo_id), _saldo_para_resposta)


@router.put("/saldos/{saldo_id}", response_model=SaldoRespostaSchema, summary="Atualiza um saldo existente")
def atualizar_saldo(
    saldo_id: str,
    dados: SaldoEntradaSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("estoque.gravar.editar")),
) -> SaldoRespostaSchema:
    return _com_produto(sessao_db, estoque_service.atualizar_saldo(sessao_db, saldo_id, dados), _saldo_para_resposta)


@router.delete("/saldos/{saldo_id}", status_code=204, summary="Remove (soft delete) um saldo")
def apagar_saldo(
    saldo_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("estoque.apagar")),
) -> None:
    estoque_service.apagar_saldo(sessao_db, saldo_id)


# --------------------------------------------------------------------------
# Saldo por lote (tabela `estoque_lotes`)
# --------------------------------------------------------------------------
@router.get("/lotes", response_model=LoteListaPaginadaSchema, summary="Lista o saldo por lote")
def listar_lotes(
    page: int = 1,
    per_page: int = 20,
    sort: str = "vencimento",
    sort_type: str = "asc",
    empresa_id: str | None = Query(default=None),
    produto_id: str | None = Query(default=None),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("estoque.acessar")),
) -> LoteListaPaginadaSchema:
    page, per_page = _pagina(page, per_page)
    itens, total, produtos = estoque_service.listar_lotes(
        sessao_db, page, per_page, sort, sort_type, empresa_id, produto_id
    )
    return LoteListaPaginadaSchema(
        items=[_lote_para_resposta(item, produtos.get(item.produto_id)) for item in itens],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.post("/lotes", response_model=LoteRespostaSchema, status_code=201, summary="Cria o saldo de um lote")
def criar_lote(
    dados: LoteEntradaSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("estoque.gravar.incluir")),
) -> LoteRespostaSchema:
    return _com_produto(sessao_db, estoque_service.criar_lote(sessao_db, dados), _lote_para_resposta)


@router.put("/lotes", response_model=LoteRespostaSchema, summary="Atualiza o lote pela chave natural (empresa + produto + lote)")
def atualizar_lote_por_chave(
    dados: LoteEntradaSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("estoque.gravar.editar")),
) -> LoteRespostaSchema:
    return _com_produto(sessao_db, estoque_service.atualizar_lote(sessao_db, None, dados), _lote_para_resposta)


@router.get("/lotes/{lote_id}", response_model=LoteRespostaSchema, summary="Obtém um lote pelo id")
def obter_lote(
    lote_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("estoque.acessar")),
) -> LoteRespostaSchema:
    return _com_produto(sessao_db, estoque_service.obter_lote(sessao_db, lote_id), _lote_para_resposta)


@router.put("/lotes/{lote_id}", response_model=LoteRespostaSchema, summary="Atualiza um lote existente")
def atualizar_lote(
    lote_id: str,
    dados: LoteEntradaSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("estoque.gravar.editar")),
) -> LoteRespostaSchema:
    return _com_produto(sessao_db, estoque_service.atualizar_lote(sessao_db, lote_id, dados), _lote_para_resposta)


@router.delete("/lotes/{lote_id}", status_code=204, summary="Remove (soft delete) um lote")
def apagar_lote(
    lote_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("estoque.apagar")),
) -> None:
    estoque_service.apagar_lote(sessao_db, lote_id)
