from app.shared.router_base import RouterBase
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.auth.dependencies import ContextoRequisicao, exigir_permissao
from app.core.database.conexao import obter_sessao
from app.domains.usuarios.cargo_model import Cargo
from app.domains.usuarios.cargo_contrato import CargoRespostaSchema

router = RouterBase(prefix="/cargos", tags=["Cargos"])


@router.get("", response_model=list[CargoRespostaSchema], summary="Lista os cargos disponíveis")
def listar(
    sessao_db: Session = Depends(obter_sessao),
    _ctx: ContextoRequisicao = Depends(exigir_permissao("usuarios.acessar")),
) -> list[Cargo]:
    return (
        sessao_db.query(Cargo)
        .filter(Cargo.sync_deleted_at.is_(None))
        .order_by(Cargo.nome)
        .all()
    )
