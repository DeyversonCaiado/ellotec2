from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.cidades.cidade_model import Cidade
from app.domains.cidades.cidade_contrato import CidadeAtualizarSchema, CidadeCriarSchema
from app.shared.sync_helpers import incrementar_versao, marcar_apagado


def listar(sessao_db: Session) -> list[Cidade]:
    return (
        sessao_db.query(Cidade)
        .filter(Cidade.sync_deleted_at.is_(None))
        .order_by(Cidade.nome)
        .all()
    )


def listar_paginado(
    sessao_db: Session,
    page: int,
    per_page: int,
    sort: str,
    sort_type: str,
    busca: str | None = None,
) -> tuple[list[Cidade], int]:
    colunas_permitidas = {
        "sync_created_at": Cidade.sync_created_at,
        "sync_updated_at": Cidade.sync_updated_at,
        "nome": Cidade.nome,
        "uf": Cidade.uf,
        "codigo_municipio": Cidade.codigo_municipio,
    }

    coluna = colunas_permitidas.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo de ordenação inválido. Use sync_created_at, sync_updated_at, nome, uf ou codigo_municipio.",
        )

    ordenacao = coluna.desc() if sort_type.lower() == "desc" else coluna.asc()
    consulta_base = sessao_db.query(Cidade).filter(Cidade.sync_deleted_at.is_(None))

    busca = (busca or "").strip()
    if busca:
        termo = f"%{busca}%"
        consulta_base = consulta_base.filter((Cidade.nome.ilike(termo)) | (Cidade.uf.ilike(termo)))

    total = consulta_base.count()
    itens = (
        consulta_base.order_by(ordenacao, Cidade.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return itens, total


def obter_por_id(sessao_db: Session, cidade_id: str) -> Cidade:
    cidade = (
        sessao_db.query(Cidade)
        .filter(Cidade.id == cidade_id, Cidade.sync_deleted_at.is_(None))
        .first()
    )
    if cidade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cidade não encontrada.")
    return cidade


def _validar_codigo_municipio_disponivel(
    sessao_db: Session, codigo_municipio: int, ignorar_id: str | None = None
) -> None:
    consulta = sessao_db.query(Cidade).filter(
        Cidade.codigo_municipio == codigo_municipio, Cidade.sync_deleted_at.is_(None)
    )
    if ignorar_id:
        consulta = consulta.filter(Cidade.id != ignorar_id)
    if consulta.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe uma cidade com esse código de município."
        )


def criar(sessao_db: Session, dados: CidadeCriarSchema) -> Cidade:
    _validar_codigo_municipio_disponivel(sessao_db, dados.codigo_municipio)

    cidade = Cidade(**dados.model_dump())
    sessao_db.add(cidade)
    sessao_db.commit()
    sessao_db.refresh(cidade)
    return cidade


def atualizar(sessao_db: Session, cidade_id: str, dados: CidadeAtualizarSchema) -> Cidade:
    cidade = obter_por_id(sessao_db, cidade_id)
    _validar_codigo_municipio_disponivel(sessao_db, dados.codigo_municipio, ignorar_id=cidade_id)

    for campo, valor in dados.model_dump().items():
        setattr(cidade, campo, valor)
    incrementar_versao(cidade)

    sessao_db.commit()
    sessao_db.refresh(cidade)
    return cidade


def apagar(sessao_db: Session, cidade_id: str) -> None:
    cidade = obter_por_id(sessao_db, cidade_id)
    marcar_apagado(cidade)
    sessao_db.commit()
