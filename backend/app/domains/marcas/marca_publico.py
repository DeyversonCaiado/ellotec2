from sqlalchemy.orm import Session

from app.domains.marcas.marca_model import Marca


def obter_id_por_sistema_origem_id(sessao_db: Session, sistema_origem_id: str) -> str | None:
    """Só leitura — devolve o id primitivo, nunca o model. Canal usado por
    outros domínios (ex: produtos) para resolver uma marca pelo id do
    sistema de origem sem importar `marca_service`."""
    marca = (
        sessao_db.query(Marca)
        .filter(Marca.sistema_origem_id == sistema_origem_id, Marca.sync_deleted_at.is_(None))
        .first()
    )
    return marca.id if marca else None
