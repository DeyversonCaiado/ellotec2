from sqlalchemy.orm import Session

from app.domains.cidades.cidade_model import Cidade


def obter_id_por_codigo_municipio(sessao_db: Session, codigo_municipio: int) -> str | None:
    cidade = (
        sessao_db.query(Cidade)
        .filter(Cidade.codigo_municipio == codigo_municipio, Cidade.sync_deleted_at.is_(None))
        .first()
    )
    return cidade.id if cidade else None
