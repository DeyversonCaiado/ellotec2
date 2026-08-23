from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.database.conexao import Base
from app.core.database import todos_os_models  # noqa: F401  garante que todas as tabelas sejam registradas
from app.domains.pedidos.pedido_model import PedidoStatus


@pytest.fixture()
def sessao_db() -> Generator[Session, None, None]:
    """
    Banco SQLite em memória, criado do zero a cada teste. Isola os testes
    de domínio do MySQL real (dev/produção) — nenhum teste aqui depende de
    infraestrutura externa nem deixa rastro entre execuções.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    # O SQLite ignora foreign keys por padrão. Como os domínios não consultam
    # uns aos outros para validar id (a FK do banco é a barreira), sem esse
    # PRAGMA um teste de "id inexistente" passaria sem exercitar nada.
    @event.listens_for(engine, "connect")
    def _ativar_fk(conexao_dbapi, _registro):  # noqa: ANN001
        cursor = conexao_dbapi.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    SessaoTeste = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sessao = SessaoTeste()

    # pedido_status é catálogo fixo, populado por migração de dados em
    # produção (ver alembic/versions/d5e7f9a1b324_...). O create_all() acima
    # só cria a estrutura da tabela, não os dados — semeamos aqui pra todo
    # teste que criar um Pedido conseguir resolver status -> status_id.
    sessao.add_all(PedidoStatus(chave=chave) for chave in ("rascunho", "enviado", "aprovado", "recusado"))
    sessao.commit()

    try:
        yield sessao
    finally:
        sessao.close()
        engine.dispose()
