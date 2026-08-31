"""
Regra de negócio do estoque: o saldo do produto na empresa (`estoque`) e o
mesmo saldo aberto por lote (`estoque_lotes`).

Este domínio é o DONO das duas tabelas. Quem precisa saber de lote — hoje o
`enderecamento`, que amarra lote a endereço, e a `expedicao`, que mostra onde a
mercadoria está — pergunta por `estoque_publico.py`, nunca consulta a tabela
direto (ver ARCHITECTURE.md → "Regras de import entre domínios").

As duas tabelas têm o mesmo desenho de escrita, então as funções abaixo são
parametrizadas por `_CONFIG_SALDO` / `_CONFIG_LOTE` em vez de existirem duas
vezes — mesma ideia do `_TIPOS` da expedição.
"""

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.empresas import empresa_publico
from app.domains.estoque.estoque_contrato import LoteEntradaSchema, SaldoEntradaSchema
from app.domains.estoque.estoque_model import Estoque, EstoqueLote
from app.domains.produtos import produto_publico
from app.shared.sync_helpers import incrementar_versao, marcar_apagado
from app.shared.vinculo_origem import preservar_no_dicionario


@dataclass(frozen=True)
class _Config:
    model: type
    rotulo: str
    # Colunas que formam a chave natural, além de empresa_id e produto_id.
    chave_extra: tuple[str, ...]
    colunas_ordenacao: dict[str, object]


_CONFIG_SALDO = _Config(
    model=Estoque,
    rotulo="Saldo de estoque",
    chave_extra=(),
    colunas_ordenacao={
        "quantidade": Estoque.quantidade,
        "sync_created_at": Estoque.sync_created_at,
        "sync_updated_at": Estoque.sync_updated_at,
    },
)

_CONFIG_LOTE = _Config(
    model=EstoqueLote,
    rotulo="Lote de estoque",
    chave_extra=("lote",),
    colunas_ordenacao={
        "lote": EstoqueLote.lote,
        "quantidade": EstoqueLote.quantidade,
        "vencimento": EstoqueLote.vencimento,
        "sync_created_at": EstoqueLote.sync_created_at,
        "sync_updated_at": EstoqueLote.sync_updated_at,
    },
)


# --------------------------------------------------------------------------
# Resolução das referências
# --------------------------------------------------------------------------
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


def _resolver_produto_id(sessao_db: Session, dados) -> str:
    if dados.produto_id:
        return dados.produto_id
    produto_id = produto_publico.obter_id_por_sistema_origem_id(
        sessao_db, dados.produto_sistema_origem_id
    )
    if produto_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Produto não encontrado pelo sistema de origem informado.",
        )
    return produto_id


def _campos(sessao_db: Session, dados) -> dict:
    """O payload já com empresa e produto resolvidos para o id daqui.

    `produto_sistema_origem_id` some do dicionário: ele é só o caminho de
    entrada da integração, não uma coluna destas tabelas. O
    `empresa_sistema_origem_id`, ao contrário, FICA — lá ele é coluna.
    """
    campos = dados.model_dump()
    campos.pop("produto_sistema_origem_id", None)
    campos["empresa_id"] = _resolver_empresa_id(sessao_db, dados)
    campos["produto_id"] = _resolver_produto_id(sessao_db, dados)
    return campos


# --------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------
def _vivos(sessao_db: Session, configuracao: _Config):
    return sessao_db.query(configuracao.model).filter(configuracao.model.sync_deleted_at.is_(None))


def _obter(sessao_db: Session, configuracao: _Config, registro_id: str):
    registro = _vivos(sessao_db, configuracao).filter(configuracao.model.id == registro_id).first()
    if registro is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=configuracao.rotulo + " não encontrado."
        )
    return registro


def _por_chave_natural(sessao_db: Session, configuracao: _Config, campos: dict):
    consulta = _vivos(sessao_db, configuracao).filter(
        configuracao.model.empresa_id == campos["empresa_id"],
        configuracao.model.produto_id == campos["produto_id"],
    )
    for coluna in configuracao.chave_extra:
        consulta = consulta.filter(getattr(configuracao.model, coluna) == campos[coluna])
    return consulta.first()


def _listar_paginado(
    sessao_db: Session,
    configuracao: _Config,
    page: int,
    per_page: int,
    sort: str,
    sort_type: str,
    empresa_id: str | None,
    produto_id: str | None,
) -> tuple[list, int]:
    coluna = configuracao.colunas_ordenacao.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo de ordenação inválido. Use "
            + ", ".join(sorted(configuracao.colunas_ordenacao))
            + ".",
        )

    consulta = _vivos(sessao_db, configuracao)
    # Os dois filtros resolvem no servidor, sobre a base inteira — nunca sobre
    # a página já carregada.
    if empresa_id:
        consulta = consulta.filter(configuracao.model.empresa_id == empresa_id)
    if produto_id:
        consulta = consulta.filter(configuracao.model.produto_id == produto_id)

    total = consulta.count()
    ordenacao = coluna.desc() if sort_type.lower() == "desc" else coluna.asc()
    itens = (
        consulta.order_by(ordenacao, configuracao.model.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return itens, total


# --------------------------------------------------------------------------
# Escrita
# --------------------------------------------------------------------------
def _criar(sessao_db: Session, configuracao: _Config, dados):
    campos = _campos(sessao_db, dados)
    if _por_chave_natural(sessao_db, configuracao, campos) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=configuracao.rotulo
            + " já existe para essa chave — use PUT para atualizar a quantidade.",
        )
    registro = configuracao.model(**campos)
    sessao_db.add(registro)
    sessao_db.commit()
    sessao_db.refresh(registro)
    return registro


def _atualizar(sessao_db: Session, configuracao: _Config, registro_id: str | None, dados):
    campos = _campos(sessao_db, dados)
    # Sem id na URL, a linha é localizada pela chave natural — é assim que a
    # integração reenvia o saldo sem precisar guardar o UUID daqui.
    registro = (
        _obter(sessao_db, configuracao, registro_id)
        if registro_id
        else _por_chave_natural(sessao_db, configuracao, campos)
    )
    if registro is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=configuracao.rotulo + " não encontrado."
        )

    # O vínculo com o ERP nunca é apagado por uma gravação que não o traz.
    # Ver app/shared/vinculo_origem.py — a regra mora lá, num lugar só.
    preservar_no_dicionario(campos, registro)

    for campo, valor in campos.items():
        setattr(registro, campo, valor)
    incrementar_versao(registro)
    sessao_db.commit()
    sessao_db.refresh(registro)
    return registro


def _apagar(sessao_db: Session, configuracao: _Config, registro_id: str) -> None:
    marcar_apagado(_obter(sessao_db, configuracao, registro_id))
    sessao_db.commit()


# --------------------------------------------------------------------------
# API do domínio — o router só chama daqui pra baixo
# --------------------------------------------------------------------------
def _com_produtos(sessao_db: Session, itens: list, total: int):
    """Anexa à página o código e a descrição de cada produto, numa consulta só.

    Sem isso a listagem mostraria UUID — a tabela guarda `produto_id`, não o
    nome. O canal é `produto_publico`: quem é dono do cadastro é o domínio de
    produtos, e ninguém consulta a tabela dele por fora.
    """
    identificacoes = produto_publico.obter_identificacoes(
        sessao_db, [item.produto_id for item in itens]
    )
    return itens, total, identificacoes


def identificar_produto(sessao_db: Session, produto_id: str):
    """Código e descrição de UM produto — o que as respostas de item único
    precisam. Mesma fronteira das listagens, só que para uma linha."""
    return produto_publico.obter_identificacoes(sessao_db, [produto_id]).get(produto_id)


def listar_saldos(sessao_db, page, per_page, sort, sort_type, empresa_id=None, produto_id=None):
    itens, total = _listar_paginado(
        sessao_db, _CONFIG_SALDO, page, per_page, sort, sort_type, empresa_id, produto_id
    )
    return _com_produtos(sessao_db, itens, total)


def obter_saldo(sessao_db: Session, saldo_id: str) -> Estoque:
    return _obter(sessao_db, _CONFIG_SALDO, saldo_id)


def criar_saldo(sessao_db: Session, dados: SaldoEntradaSchema) -> Estoque:
    return _criar(sessao_db, _CONFIG_SALDO, dados)


def atualizar_saldo(sessao_db: Session, saldo_id: str | None, dados: SaldoEntradaSchema) -> Estoque:
    return _atualizar(sessao_db, _CONFIG_SALDO, saldo_id, dados)


def apagar_saldo(sessao_db: Session, saldo_id: str) -> None:
    _apagar(sessao_db, _CONFIG_SALDO, saldo_id)


def listar_lotes(sessao_db, page, per_page, sort, sort_type, empresa_id=None, produto_id=None):
    itens, total = _listar_paginado(
        sessao_db, _CONFIG_LOTE, page, per_page, sort, sort_type, empresa_id, produto_id
    )
    return _com_produtos(sessao_db, itens, total)


def obter_lote(sessao_db: Session, lote_id: str) -> EstoqueLote:
    return _obter(sessao_db, _CONFIG_LOTE, lote_id)


def criar_lote(sessao_db: Session, dados: LoteEntradaSchema) -> EstoqueLote:
    return _criar(sessao_db, _CONFIG_LOTE, dados)


def atualizar_lote(sessao_db: Session, lote_id: str | None, dados: LoteEntradaSchema) -> EstoqueLote:
    return _atualizar(sessao_db, _CONFIG_LOTE, lote_id, dados)


def apagar_lote(sessao_db: Session, lote_id: str) -> None:
    _apagar(sessao_db, _CONFIG_LOTE, lote_id)
