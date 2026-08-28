"""
Regra de negócio do endereçamento: o cadastro dos lugares do galpão
(`estoque_enderecos`) e o vínculo de cada lote com os lugares onde ele está
guardado (`estoque_endereco_lote`).

Este domínio é o dono das duas tabelas. O lote em si é de `estoque` — daqui só
se guarda a FK, e o id do lote é resolvido pelo canal `estoque_publico.py`,
nunca por uma query em `estoque_lotes` (ver ARCHITECTURE.md → "Regras de import
entre domínios").
"""

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.domains.empresas import empresa_publico
from app.domains.enderecamento.enderecamento_contrato import (
    EnderecoEntradaSchema,
    VinculoEntradaSchema,
)
from app.domains.enderecamento.enderecamento_model import EstoqueEndereco, EstoqueEnderecoLote
from app.domains.estoque import estoque_publico
from app.domains.produtos import produto_publico
from app.shared.sync_helpers import incrementar_versao, marcar_apagado

_ORDENACAO_ENDERECO = {
    "descricao": EstoqueEndereco.descricao,
    "sync_created_at": EstoqueEndereco.sync_created_at,
    "sync_updated_at": EstoqueEndereco.sync_updated_at,
}

_ORDENACAO_VINCULO = {
    # `descricao` é o padrão da consulta: quem procura "onde está" lê a lista na
    # ordem da etiqueta da prateleira, que é a ordem em que ele anda no galpão.
    "descricao": EstoqueEndereco.descricao,
    "quantidade": EstoqueEnderecoLote.quantidade,
    "sync_created_at": EstoqueEnderecoLote.sync_created_at,
    "sync_updated_at": EstoqueEnderecoLote.sync_updated_at,
}


def _resolver_empresa_id(sessao_db: Session, dados) -> str:
    if dados.empresa_id:
        return dados.empresa_id
    empresa_id = empresa_publico.obter_id_por_sistema_origem_id(
        sessao_db, dados.empresa_sistema_origem_id
    )
    if empresa_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Empresa não encontrada pelo sistema de origem informado.",
        )
    return empresa_id


def _ordenacao(colunas: dict, sort: str, sort_type: str):
    coluna = colunas.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo de ordenação inválido. Use " + ", ".join(sorted(colunas)) + ".",
        )
    return coluna.desc() if sort_type.lower() == "desc" else coluna.asc()


# --------------------------------------------------------------------------
# Endereços (`estoque_enderecos`)
# --------------------------------------------------------------------------
def _enderecos_vivos(sessao_db: Session):
    return sessao_db.query(EstoqueEndereco).filter(EstoqueEndereco.sync_deleted_at.is_(None))


def obter_endereco(sessao_db: Session, endereco_id: str) -> EstoqueEndereco:
    endereco = _enderecos_vivos(sessao_db).filter(EstoqueEndereco.id == endereco_id).first()
    if endereco is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endereço não encontrado.")
    return endereco


def _endereco_por_descricao(
    sessao_db: Session, empresa_id: str, descricao: str
) -> EstoqueEndereco | None:
    return (
        _enderecos_vivos(sessao_db)
        .filter(
            EstoqueEndereco.empresa_id == empresa_id,
            EstoqueEndereco.descricao == descricao,
        )
        .first()
    )


def listar_enderecos(
    sessao_db: Session,
    page: int,
    per_page: int,
    sort: str,
    sort_type: str,
    empresa_id: str | None = None,
    q: str | None = None,
) -> tuple[list[EstoqueEndereco], int]:
    consulta = _enderecos_vivos(sessao_db)
    if empresa_id:
        consulta = consulta.filter(EstoqueEndereco.empresa_id == empresa_id)
    termo = (q or "").strip()
    if termo:
        consulta = consulta.filter(EstoqueEndereco.descricao.ilike(f"%{termo}%"))

    total = consulta.count()
    itens = (
        consulta.order_by(_ordenacao(_ORDENACAO_ENDERECO, sort, sort_type), EstoqueEndereco.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return itens, total


def criar_endereco(sessao_db: Session, dados: EnderecoEntradaSchema) -> EstoqueEndereco:
    campos = dados.model_dump()
    campos["empresa_id"] = _resolver_empresa_id(sessao_db, dados)
    if _endereco_por_descricao(sessao_db, campos["empresa_id"], campos["descricao"]) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um endereço com essa descrição nesta empresa.",
        )
    endereco = EstoqueEndereco(**campos)
    sessao_db.add(endereco)
    sessao_db.commit()
    sessao_db.refresh(endereco)
    return endereco


def atualizar_endereco(
    sessao_db: Session, endereco_id: str, dados: EnderecoEntradaSchema
) -> EstoqueEndereco:
    endereco = obter_endereco(sessao_db, endereco_id)
    campos = dados.model_dump()
    campos["empresa_id"] = _resolver_empresa_id(sessao_db, dados)

    existente = _endereco_por_descricao(sessao_db, campos["empresa_id"], campos["descricao"])
    if existente is not None and existente.id != endereco.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um endereço com essa descrição nesta empresa.",
        )

    for campo, valor in campos.items():
        setattr(endereco, campo, valor)
    incrementar_versao(endereco)
    sessao_db.commit()
    sessao_db.refresh(endereco)
    return endereco


def apagar_endereco(sessao_db: Session, endereco_id: str) -> None:
    marcar_apagado(obter_endereco(sessao_db, endereco_id))
    sessao_db.commit()


# --------------------------------------------------------------------------
# Vínculos endereço ↔ lote (`estoque_endereco_lote`)
# --------------------------------------------------------------------------
def _vinculos_vivos(sessao_db: Session):
    return sessao_db.query(EstoqueEnderecoLote).filter(EstoqueEnderecoLote.sync_deleted_at.is_(None))


def obter_vinculo(sessao_db: Session, vinculo_id: str) -> EstoqueEnderecoLote:
    vinculo = _vinculos_vivos(sessao_db).filter(EstoqueEnderecoLote.id == vinculo_id).first()
    if vinculo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vínculo não encontrado.")
    return vinculo


def _resolver_endereco_id(sessao_db: Session, empresa_id: str, dados: VinculoEntradaSchema) -> str:
    if dados.estoque_enderecos_id:
        return obter_endereco(sessao_db, dados.estoque_enderecos_id).id
    endereco = _endereco_por_descricao(sessao_db, empresa_id, dados.endereco_descricao)
    if endereco is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Endereço não encontrado pela descrição informada nesta empresa.",
        )
    return endereco.id


def _resolver_lote_id(sessao_db: Session, empresa_id: str, dados: VinculoEntradaSchema) -> str:
    if dados.estoque_lotes_id:
        return dados.estoque_lotes_id

    produto_id = dados.produto_id
    if not produto_id:
        produto_id = produto_publico.obter_id_por_sistema_origem_id(
            sessao_db, dados.produto_sistema_origem_id
        )
    if produto_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Produto não encontrado pelo sistema de origem informado.",
        )

    lote_id = estoque_publico.obter_id_do_lote(sessao_db, empresa_id, produto_id, dados.lote)
    if lote_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Lote não encontrado no estoque desta empresa — cadastre o lote antes de endereçá-lo.",
        )
    return lote_id


def _campos_vinculo(sessao_db: Session, dados: VinculoEntradaSchema) -> dict:
    empresa_id = _resolver_empresa_id(sessao_db, dados)
    return {
        "empresa_id": empresa_id,
        "empresa_sistema_origem_id": dados.empresa_sistema_origem_id,
        "sistema_origem_id": dados.sistema_origem_id,
        "estoque_enderecos_id": _resolver_endereco_id(sessao_db, empresa_id, dados),
        "estoque_lotes_id": _resolver_lote_id(sessao_db, empresa_id, dados),
        "quantidade": dados.quantidade,
    }


def _vinculo_por_chave_natural(sessao_db: Session, campos: dict) -> EstoqueEnderecoLote | None:
    return (
        _vinculos_vivos(sessao_db)
        .filter(
            EstoqueEnderecoLote.estoque_enderecos_id == campos["estoque_enderecos_id"],
            EstoqueEnderecoLote.estoque_lotes_id == campos["estoque_lotes_id"],
        )
        .first()
    )


class VinculoDetalhado:
    """Uma linha da consulta de endereçamento, já resolvida para exibição.

    Junta o que vem de três domínios — o vínculo (daqui), o lote (`estoque`) e a
    identificação do produto (`produtos`) — para o router não ter que orquestrar
    isso e para a tela receber a linha pronta.
    """

    def __init__(self, vinculo, endereco_descricao, lote, produto_id, produto_codigo, produto_descricao):
        self.vinculo = vinculo
        self.endereco_descricao = endereco_descricao
        self.lote = lote
        self.produto_id = produto_id
        self.produto_codigo = produto_codigo
        self.produto_descricao = produto_descricao


def listar_vinculos(
    sessao_db: Session,
    page: int,
    per_page: int,
    sort: str,
    sort_type: str,
    empresa_id: str | None = None,
    estoque_lotes_id: str | None = None,
    estoque_enderecos_id: str | None = None,
    q: str | None = None,
) -> tuple[list[VinculoDetalhado], int]:
    """A consulta "onde está este produto".

    O termo de busca casa com QUALQUER uma das formas de a pessoa se referir ao
    que está procurando: a etiqueta do endereço, o texto do lote, e — pelas
    bordas dos domínios donos — o código do produto, a descrição dele e os
    códigos de barras (nota, logística e DUN-14).

    **Como o filtro por produto atravessa a fronteira sem quebrar a paginação.**
    Quem sabe identificar um produto é `produtos`, e quem sabe que lote é de que
    produto é `estoque`. Então o termo é traduzido em duas etapas de leitura —
    `produto_publico.buscar_ids_por_termo` e `estoque_publico.buscar_ids_de_lotes`
    — e o que sobra é um `IN` sobre `estoque_endereco_lote`, que é tabela DESTE
    domínio. O `LIMIT/OFFSET` continua no banco, numa consulta só: nada é
    filtrado ou paginado em Python (ver a regra "todo filtro de tela paginada
    resolve no servidor").

    O `IN` cresce com o número de lotes do produto procurado, não com o tamanho
    da base — um produto tem dezenas de lotes, não milhares.
    """
    consulta = _vinculos_vivos(sessao_db).join(
        EstoqueEndereco, EstoqueEndereco.id == EstoqueEnderecoLote.estoque_enderecos_id
    )
    if empresa_id:
        consulta = consulta.filter(EstoqueEnderecoLote.empresa_id == empresa_id)
    if estoque_lotes_id:
        consulta = consulta.filter(EstoqueEnderecoLote.estoque_lotes_id == estoque_lotes_id)
    if estoque_enderecos_id:
        consulta = consulta.filter(EstoqueEnderecoLote.estoque_enderecos_id == estoque_enderecos_id)

    termo = (q or "").strip()
    if termo:
        lote_ids = estoque_publico.buscar_ids_de_lotes(
            sessao_db,
            produto_ids=produto_publico.buscar_ids_por_termo(sessao_db, termo),
            texto_lote=termo,
            empresa_id=empresa_id,
        )
        condicoes = [EstoqueEndereco.descricao.ilike(f"%{termo}%")]
        if lote_ids:
            condicoes.append(EstoqueEnderecoLote.estoque_lotes_id.in_(lote_ids))
        consulta = consulta.filter(or_(*condicoes))

    total = consulta.count()
    linhas = (
        consulta.with_entities(EstoqueEnderecoLote, EstoqueEndereco.descricao)
        .order_by(_ordenacao(_ORDENACAO_VINCULO, sort, sort_type), EstoqueEnderecoLote.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Lote e produto da página inteira em duas consultas, não duas por linha.
    lotes = estoque_publico.obter_lotes(
        sessao_db, [vinculo.estoque_lotes_id for vinculo, _ in linhas]
    )
    produtos = produto_publico.obter_identificacoes(
        sessao_db, [lote.produto_id for lote in lotes.values()]
    )

    detalhadas = []
    for vinculo, endereco_descricao in linhas:
        lote = lotes.get(vinculo.estoque_lotes_id)
        produto = produtos.get(lote.produto_id) if lote else None
        detalhadas.append(
            VinculoDetalhado(
                vinculo=vinculo,
                endereco_descricao=endereco_descricao,
                lote=lote.lote if lote else "",
                produto_id=lote.produto_id if lote else "",
                produto_codigo=produto.codigo if produto else "",
                produto_descricao=produto.descricao if produto else "",
            )
        )
    return detalhadas, total


def _detalhar(sessao_db: Session, vinculo: EstoqueEnderecoLote) -> VinculoDetalhado:
    """Uma linha só, já resolvida — usada nas respostas de criar/atualizar. A
    listagem tem o caminho em lote; aqui é uma linha e não vale a cerimônia."""
    lote = estoque_publico.obter_lotes(sessao_db, [vinculo.estoque_lotes_id]).get(
        vinculo.estoque_lotes_id
    )
    produto = (
        produto_publico.obter_identificacoes(sessao_db, [lote.produto_id]).get(lote.produto_id)
        if lote
        else None
    )
    return VinculoDetalhado(
        vinculo=vinculo,
        endereco_descricao=obter_endereco(sessao_db, vinculo.estoque_enderecos_id).descricao,
        lote=lote.lote if lote else "",
        produto_id=lote.produto_id if lote else "",
        produto_codigo=produto.codigo if produto else "",
        produto_descricao=produto.descricao if produto else "",
    )


def criar_vinculo(sessao_db: Session, dados: VinculoEntradaSchema) -> VinculoDetalhado:
    campos = _campos_vinculo(sessao_db, dados)
    if _vinculo_por_chave_natural(sessao_db, campos) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este lote já está vinculado a esse endereço.",
        )
    vinculo = EstoqueEnderecoLote(**campos)
    sessao_db.add(vinculo)
    sessao_db.commit()
    sessao_db.refresh(vinculo)
    return _detalhar(sessao_db, vinculo)


def atualizar_vinculo(
    sessao_db: Session, vinculo_id: str, dados: VinculoEntradaSchema
) -> VinculoDetalhado:
    vinculo = obter_vinculo(sessao_db, vinculo_id)
    campos = _campos_vinculo(sessao_db, dados)

    existente = _vinculo_por_chave_natural(sessao_db, campos)
    if existente is not None and existente.id != vinculo.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este lote já está vinculado a esse endereço.",
        )

    for campo, valor in campos.items():
        setattr(vinculo, campo, valor)
    incrementar_versao(vinculo)
    sessao_db.commit()
    sessao_db.refresh(vinculo)
    return _detalhar(sessao_db, vinculo)


def apagar_vinculo(sessao_db: Session, vinculo_id: str) -> None:
    marcar_apagado(obter_vinculo(sessao_db, vinculo_id))
    sessao_db.commit()
