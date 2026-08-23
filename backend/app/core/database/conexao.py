from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.settings import obter_settings

settings = obter_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # evita erro de "conexão caiu" em conexões ociosas (MySQL fecha após wait_timeout)
    pool_recycle=3600,
    echo=settings.debug and settings.ambiente == "desenvolvimento",
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Classe base de todos os models. Mantida aqui (e não em cada domínio)
    porque é infraestrutura, não regra de negócio — todo domínio importa
    daqui, nunca o contrário."""

    pass


def obter_sessao() -> Generator[Session, None, None]:
    """Dependency do FastAPI: uma sessão por requisição, fechada ao final.

    O rollback no except é obrigatório, não cosmético: se um endpoint lançar
    (ex: HTTPException de validação) no meio de uma transação, sem o
    rollback a conexão volta pro pool do engine com uma transação MySQL
    ainda aberta. A próxima requisição que reutilizar essa conexão do pool
    herda esse estado sujo — sintoma típico: leitura funciona, escrita na
    conexão reciclada falha com erro genérico, sem relação aparente com o
    que a requisição atual está fazendo."""
    sessao = SessionLocal()
    try:
        yield sessao
    except Exception:
        sessao.rollback()
        raise
    finally:
        sessao.close()
