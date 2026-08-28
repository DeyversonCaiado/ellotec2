"""
Camada HTTP do endereçamento.

Dois recursos, um router: `/enderecamento/enderecos` para os lugares do galpão
e `/enderecamento/vinculos` para a amarração lote ↔ endereço.
"""

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.enderecamento import enderecamento_service
from app.domains.enderecamento.enderecamento_contrato import (
    EnderecoEntradaSchema,
    EnderecoListaPaginadaSchema,
    EnderecoRespostaSchema,
    VinculoEntradaSchema,
    VinculoListaPaginadaSchema,
    VinculoRespostaSchema,
)
from app.domains.enderecamento.enderecamento_model import EstoqueEndereco
from app.shared.router_base import RouterBase

router = RouterBase(prefix="/enderecamento", tags=["Endereçamento"])


def _endereco_para_resposta(endereco: EstoqueEndereco) -> EnderecoRespostaSchema:
    return EnderecoRespostaSchema(
        id=endereco.id,
        descricao=endereco.descricao,
        empresa_id=endereco.empresa_id,
        sistema_origem_id=endereco.sistema_origem_id,
        empresa_sistema_origem_id=endereco.empresa_sistema_origem_id,
        criado_em=endereco.sync_created_at,
    )


def _vinculo_para_resposta(linha) -> VinculoRespostaSchema:
    vinculo = linha.vinculo
    return VinculoRespostaSchema(
        id=vinculo.id,
        estoque_enderecos_id=vinculo.estoque_enderecos_id,
        estoque_lotes_id=vinculo.estoque_lotes_id,
        quantidade=float(vinculo.quantidade or 0),
        endereco_descricao=linha.endereco_descricao,
        lote=linha.lote,
        produto_id=linha.produto_id,
        produto_codigo=linha.produto_codigo,
        produto_descricao=linha.produto_descricao,
        empresa_id=vinculo.empresa_id,
        sistema_origem_id=vinculo.sistema_origem_id,
        empresa_sistema_origem_id=vinculo.empresa_sistema_origem_id,
        criado_em=vinculo.sync_created_at,
    )


def _pagina(page: int, per_page: int) -> tuple[int, int]:
    return max(page, 1), min(max(per_page, 1), 100)


# --------------------------------------------------------------------------
# Endereços
# --------------------------------------------------------------------------
@router.get("/enderecos", response_model=EnderecoListaPaginadaSchema, summary="Lista os endereços do galpão")
def listar_enderecos(
    page: int = 1,
    per_page: int = 20,
    sort: str = "descricao",
    sort_type: str = "asc",
    empresa_id: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Termo de busca na descrição do endereço"),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("enderecamento.acessar")),
) -> EnderecoListaPaginadaSchema:
    page, per_page = _pagina(page, per_page)
    itens, total = enderecamento_service.listar_enderecos(
        sessao_db, page, per_page, sort, sort_type, empresa_id, q
    )
    return EnderecoListaPaginadaSchema(
        items=[_endereco_para_resposta(item) for item in itens],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.post("/enderecos", response_model=EnderecoRespostaSchema, status_code=201, summary="Cria um endereço")
def criar_endereco(
    dados: EnderecoEntradaSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("enderecamento.gravar.incluir")),
) -> EnderecoRespostaSchema:
    return _endereco_para_resposta(enderecamento_service.criar_endereco(sessao_db, dados))


@router.get("/enderecos/{endereco_id}", response_model=EnderecoRespostaSchema, summary="Obtém um endereço pelo id")
def obter_endereco(
    endereco_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("enderecamento.acessar")),
) -> EnderecoRespostaSchema:
    return _endereco_para_resposta(enderecamento_service.obter_endereco(sessao_db, endereco_id))


@router.put("/enderecos/{endereco_id}", response_model=EnderecoRespostaSchema, summary="Atualiza um endereço")
def atualizar_endereco(
    endereco_id: str,
    dados: EnderecoEntradaSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("enderecamento.gravar.editar")),
) -> EnderecoRespostaSchema:
    return _endereco_para_resposta(
        enderecamento_service.atualizar_endereco(sessao_db, endereco_id, dados)
    )


@router.delete("/enderecos/{endereco_id}", status_code=204, summary="Remove (soft delete) um endereço")
def apagar_endereco(
    endereco_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("enderecamento.apagar")),
) -> None:
    enderecamento_service.apagar_endereco(sessao_db, endereco_id)


# --------------------------------------------------------------------------
# Vínculos lote ↔ endereço
# --------------------------------------------------------------------------
@router.get("/vinculos", response_model=VinculoListaPaginadaSchema, summary="Lista onde cada lote está guardado")
def listar_vinculos(
    page: int = 1,
    per_page: int = 20,
    sort: str = "descricao",
    sort_type: str = "asc",
    empresa_id: str | None = Query(default=None),
    estoque_lotes_id: str | None = Query(default=None),
    estoque_enderecos_id: str | None = Query(default=None),
    q: str | None = Query(
        default=None,
        description=(
            "Busca por endereço, lote, código do produto, descrição do produto "
            "ou qualquer código de barras dele"
        ),
    ),
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("enderecamento.acessar")),
) -> VinculoListaPaginadaSchema:
    page, per_page = _pagina(page, per_page)
    linhas, total = enderecamento_service.listar_vinculos(
        sessao_db,
        page,
        per_page,
        sort,
        sort_type,
        empresa_id,
        estoque_lotes_id,
        estoque_enderecos_id,
        q,
    )
    return VinculoListaPaginadaSchema(
        items=[_vinculo_para_resposta(linha) for linha in linhas],
        total=total,
        page=page,
        per_page=per_page,
        sort=sort,
        sort_type=sort_type.lower(),
    )


@router.post("/vinculos", response_model=VinculoRespostaSchema, status_code=201, summary="Endereça um lote")
def criar_vinculo(
    dados: VinculoEntradaSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("enderecamento.gravar.incluir")),
) -> VinculoRespostaSchema:
    return _vinculo_para_resposta(enderecamento_service.criar_vinculo(sessao_db, dados))


@router.put("/vinculos/{vinculo_id}", response_model=VinculoRespostaSchema, summary="Atualiza um vínculo")
def atualizar_vinculo(
    vinculo_id: str,
    dados: VinculoEntradaSchema,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("enderecamento.gravar.editar")),
) -> VinculoRespostaSchema:
    return _vinculo_para_resposta(
        enderecamento_service.atualizar_vinculo(sessao_db, vinculo_id, dados)
    )


@router.delete("/vinculos/{vinculo_id}", status_code=204, summary="Remove (soft delete) um vínculo")
def apagar_vinculo(
    vinculo_id: str,
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("enderecamento.apagar")),
) -> None:
    enderecamento_service.apagar_vinculo(sessao_db, vinculo_id)
