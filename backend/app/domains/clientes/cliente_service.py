from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.domains.cidades import cidade_publico
from app.domains.clientes.cliente_model import Cliente
from app.domains.clientes.cliente_contrato import ClienteAtualizarSchema, ClienteCriarSchema
from app.shared.sync_helpers import incrementar_versao, marcar_apagado


def listar_paginado(
    sessao_db: Session,
    page: int,
    per_page: int,
    sort: str,
    sort_type: str,
    q: str | None = None,
) -> tuple[list[Cliente], int]:
    colunas_permitidas = {
        "sync_created_at": Cliente.sync_created_at,
        "sync_updated_at": Cliente.sync_updated_at,
        "codigo": Cliente.codigo,
        "razao_social": Cliente.razao_social,
        "nome_fantasia": Cliente.nome_fantasia,
        "cpf_cnpj": Cliente.cpf_cnpj,
    }

    coluna = colunas_permitidas.get(sort)
    if coluna is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo de ordenação inválido. Use sync_created_at, sync_updated_at, codigo, razao_social, nome_fantasia ou cpf_cnpj.",
        )

    ordenacao = coluna.desc() if sort_type.lower() == "desc" else coluna.asc()
    consulta_base = sessao_db.query(Cliente).filter(Cliente.sync_deleted_at.is_(None))

    q = (q or "").strip()
    if q:
        termo = f"%{q}%"
        consulta_base = consulta_base.filter(
            or_(
                Cliente.razao_social.ilike(termo),
                Cliente.nome_fantasia.ilike(termo),
                Cliente.cpf_cnpj.ilike(termo),
            )
        )

    total = consulta_base.count()
    itens = (
        consulta_base.order_by(ordenacao, Cliente.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return itens, total


def obter_por_id(sessao_db: Session, cliente_id: str) -> Cliente:
    cliente = (
        sessao_db.query(Cliente)
        .filter(Cliente.id == cliente_id, Cliente.sync_deleted_at.is_(None))
        .first()
    )
    if cliente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado.")
    return cliente


def obter_por_sistema_origem_id(sessao_db: Session, sistema_origem_id: str) -> Cliente:
    cliente = (
        sessao_db.query(Cliente)
        .filter(Cliente.sistema_origem_id == sistema_origem_id, Cliente.sync_deleted_at.is_(None))
        .first()
    )
    if cliente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado.")
    return cliente


def _validar_sistema_origem_disponivel(
    sessao_db: Session, sistema_origem_id: str | None, ignorar_id: str | None = None
) -> None:
    if not sistema_origem_id:
        return

    consulta = sessao_db.query(Cliente).filter(
        Cliente.sistema_origem_id == sistema_origem_id, Cliente.sync_deleted_at.is_(None)
    )
    if ignorar_id:
        consulta = consulta.filter(Cliente.id != ignorar_id)
    if consulta.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe um cliente com esse sistema de origem."
        )


def _resolver_cidade_id(sessao_db: Session, dados: ClienteCriarSchema | ClienteAtualizarSchema) -> str:
    if dados.cidade_id:
        return dados.cidade_id

    cidade_id = cidade_publico.obter_id_por_codigo_municipio(sessao_db, dados.cidade_ibge)
    if cidade_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cidade não encontrada para o código IBGE informado.",
        )
    return cidade_id


def criar(sessao_db: Session, dados: ClienteCriarSchema) -> Cliente:
    _validar_sistema_origem_disponivel(sessao_db, dados.sistema_origem_id)

    campos = dados.model_dump(exclude={"cidade_ibge"})
    campos["cidade_id"] = _resolver_cidade_id(sessao_db, dados)

    cliente = Cliente(**campos)
    sessao_db.add(cliente)
    sessao_db.commit()
    sessao_db.refresh(cliente)
    return cliente


def atualizar(
    sessao_db: Session,
    cliente_id: str,
    dados: ClienteAtualizarSchema,
    sistema_origem_id: str | None = None,
) -> Cliente:
    cliente = (
        obter_por_sistema_origem_id(sessao_db, sistema_origem_id)
        if sistema_origem_id
        else obter_por_id(sessao_db, cliente_id)
    )

    campos = dados.model_dump(exclude={"cidade_ibge"})
    campos["cidade_id"] = _resolver_cidade_id(sessao_db, dados)
    # Se o cliente foi localizado pelo sistema_origem_id (via query param) e o
    # corpo da requisição não repetiu o campo, preserva o valor usado na busca
    # em vez de apagá-lo — o integrador não deveria precisar reenviar a própria
    # chave que já usou para identificar o registro.
    campos["sistema_origem_id"] = campos.get("sistema_origem_id") or sistema_origem_id
    _validar_sistema_origem_disponivel(sessao_db, campos["sistema_origem_id"], ignorar_id=cliente.id)

    for campo, valor in campos.items():
        setattr(cliente, campo, valor)
    incrementar_versao(cliente)

    sessao_db.commit()
    sessao_db.refresh(cliente)
    return cliente


def apagar(sessao_db: Session, cliente_id: str) -> None:
    cliente = obter_por_id(sessao_db, cliente_id)
    marcar_apagado(cliente)
    sessao_db.commit()
