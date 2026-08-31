from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.domains.empresas.empresa_model import Empresa
from app.domains.empresas.empresa_contrato import EmpresaAtualizarSchema, EmpresaCriarSchema
from app.shared.sync_helpers import incrementar_versao, marcar_apagado
from app.shared.vinculo_origem import preservar_no_dicionario


def listar_paginado(
    sessao_db: Session,
    page: int,
    per_page: int,
    sort: str,
    sort_type: str,
    q: str | None = None,
) -> tuple[list[Empresa], int]:
    colunas_permitidas = {
        "sync_created_at": Empresa.sync_created_at,
        "sync_updated_at": Empresa.sync_updated_at,
        "codigo": Empresa.codigo,
        "razao_social": Empresa.razao_social,
        "nome_fantasia": Empresa.nome_fantasia,
        "cnpj": Empresa.cnpj,
    }

    coluna = colunas_permitidas.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo de ordenação inválido. Use sync_created_at, sync_updated_at, codigo, razao_social, nome_fantasia ou cnpj.",
        )

    ordenacao = coluna.desc() if sort_type.lower() == "desc" else coluna.asc()
    consulta_base = sessao_db.query(Empresa).filter(Empresa.sync_deleted_at.is_(None))

    q = (q or "").strip()
    if q:
        termo = f"%{q}%"
        consulta_base = consulta_base.filter(
            or_(
                Empresa.razao_social.ilike(termo),
                Empresa.nome_fantasia.ilike(termo),
                Empresa.cnpj.ilike(termo),
            )
        )

    total = consulta_base.count()
    itens = (
        consulta_base.order_by(ordenacao, Empresa.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return itens, total


def obter_por_id(sessao_db: Session, empresa_id: str) -> Empresa:
    empresa = (
        sessao_db.query(Empresa)
        .filter(Empresa.id == empresa_id, Empresa.sync_deleted_at.is_(None))
        .first()
    )
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada.")
    return empresa


def obter_por_sistema_origem_id(sessao_db: Session, sistema_origem_id: str) -> Empresa:
    empresa = (
        sessao_db.query(Empresa)
        .filter(Empresa.sistema_origem_id == sistema_origem_id, Empresa.sync_deleted_at.is_(None))
        .first()
    )
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada.")
    return empresa


def _validar_sistema_origem_disponivel(
    sessao_db: Session, sistema_origem_id: str | None, ignorar_id: str | None = None
) -> None:
    if not sistema_origem_id:
        return

    consulta = sessao_db.query(Empresa).filter(
        Empresa.sistema_origem_id == sistema_origem_id, Empresa.sync_deleted_at.is_(None)
    )
    if ignorar_id:
        consulta = consulta.filter(Empresa.id != ignorar_id)
    if consulta.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe uma empresa com esse sistema de origem."
        )


def criar(sessao_db: Session, dados: EmpresaCriarSchema) -> Empresa:
    _validar_sistema_origem_disponivel(sessao_db, dados.sistema_origem_id)

    empresa = Empresa(**dados.model_dump())
    sessao_db.add(empresa)
    sessao_db.commit()
    sessao_db.refresh(empresa)
    return empresa


def atualizar(
    sessao_db: Session,
    empresa_id: str,
    dados: EmpresaAtualizarSchema,
    sistema_origem_id: str | None = None,
) -> Empresa:
    empresa = (
        obter_por_sistema_origem_id(sessao_db, sistema_origem_id)
        if sistema_origem_id
        else obter_por_id(sessao_db, empresa_id)
    )

    campos = dados.model_dump()
    # O vínculo com o ERP nunca é apagado por uma gravação que não o traz.
    # Ver app/shared/vinculo_origem.py — a regra mora lá, num lugar só.
    preservar_no_dicionario(campos, empresa, da_busca=sistema_origem_id)
    _validar_sistema_origem_disponivel(sessao_db, campos["sistema_origem_id"], ignorar_id=empresa.id)

    for campo, valor in campos.items():
        setattr(empresa, campo, valor)
    incrementar_versao(empresa)

    sessao_db.commit()
    sessao_db.refresh(empresa)
    return empresa


def apagar(sessao_db: Session, empresa_id: str) -> None:
    empresa = obter_por_id(sessao_db, empresa_id)
    marcar_apagado(empresa)
    sessao_db.commit()
