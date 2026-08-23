import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

# garante que o pacote `app` é importável quando o Alembic roda a partir
# da raiz do projeto (onde fica alembic.ini)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database.conexao import Base  # noqa: E402
from app.core.database import todos_os_models  # noqa: E402, F401 — registra todas as tabelas no metadata
from app.core.settings import obter_settings  # noqa: E402

config = context.config

settings = obter_settings()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(object_: object, name: str, type_: str, reflected: bool, compare_to: object) -> bool:
    """Autogenerate apenas tabelas do projeto.

    O banco é compartilhado com outros sistemas (`cidades`, `cotacao_*`,
    `pedido_*`, etc). Sem esse filtro, o autogenerate geraria `drop_table`
    para essas tabelas estranhas. Retornamos False para qualquer tabela que
    não esteja no metadata dos models da aplicação.
    """
    if type_ == "table":
        return name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
