from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.marcas.marca_model import Marca
from app.domains.marcas.marca_contrato import MarcaAtualizarSchema, MarcaCriarSchema
from app.shared.sync_helpers import incrementar_versao, marcar_apagado


def listar_paginado(
    sessao_db: Session,
    page: int,
    per_page: int,
    sort: str,
    sort_type: str,
    q: str | None = None,
) -> tuple[list[Marca], int]:
    colunas_permitidas = {
        "sync_created_at": Marca.sync_created_at,
        "sync_updated_at": Marca.sync_updated_at,
        "nome": Marca.nome,
    }

    coluna = colunas_permitidas.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo de ordenação inválido. Use sync_created_at, sync_updated_at ou nome.",
        )

    ordenacao = coluna.desc() if sort_type.lower() == "desc" else coluna.asc()
    consulta_base = sessao_db.query(Marca).filter(Marca.sync_deleted_at.is_(None))

    q = (q or "").strip()
    if q:
        consulta_base = consulta_base.filter(Marca.nome.ilike(f"%{q}%"))

    total = consulta_base.count()
    itens = (
        consulta_base.order_by(ordenacao, Marca.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return itens, total


def obter_por_id(sessao_db: Session, marca_id: str) -> Marca:
    marca = (
        sessao_db.query(Marca)
        .filter(Marca.id == marca_id, Marca.sync_deleted_at.is_(None))
        .first()
    )
    if marca is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marca não encontrada.")
    return marca


def obter_por_sistema_origem_id(sessao_db: Session, sistema_origem_id: str) -> Marca:
    marca = (
        sessao_db.query(Marca)
        .filter(Marca.sistema_origem_id == sistema_origem_id, Marca.sync_deleted_at.is_(None))
        .first()
    )
    if marca is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marca não encontrada.")
    return marca


def _validar_sistema_origem_disponivel(
    sessao_db: Session, sistema_origem_id: str | None, ignorar_id: str | None = None
) -> None:
    if not sistema_origem_id:
        return

    consulta = sessao_db.query(Marca).filter(
        Marca.sistema_origem_id == sistema_origem_id, Marca.sync_deleted_at.is_(None)
    )
    if ignorar_id:
        consulta = consulta.filter(Marca.id != ignorar_id)
    if consulta.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe uma marca com esse sistema de origem."
        )


def criar(sessao_db: Session, dados: MarcaCriarSchema) -> Marca:
    _validar_sistema_origem_disponivel(sessao_db, dados.sistema_origem_id)

    marca = Marca(**dados.model_dump())
    sessao_db.add(marca)
    sessao_db.commit()
    sessao_db.refresh(marca)
    return marca


def atualizar(
    sessao_db: Session,
    marca_id: str,
    dados: MarcaAtualizarSchema,
    sistema_origem_id: str | None = None,
) -> Marca:
    marca = (
        obter_por_sistema_origem_id(sessao_db, sistema_origem_id)
        if sistema_origem_id
        else obter_por_id(sessao_db, marca_id)
    )

    campos = dados.model_dump()
    campos["sistema_origem_id"] = campos.get("sistema_origem_id") or sistema_origem_id
    _validar_sistema_origem_disponivel(sessao_db, campos["sistema_origem_id"], ignorar_id=marca.id)

    for campo, valor in campos.items():
        setattr(marca, campo, valor)
    incrementar_versao(marca)

    sessao_db.commit()
    sessao_db.refresh(marca)
    return marca


def apagar(sessao_db: Session, marca_id: str) -> None:
    marca = obter_por_id(sessao_db, marca_id)
    marcar_apagado(marca)
    sessao_db.commit()
