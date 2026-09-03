from sqlalchemy.orm import Session

from app.domains.empresas.empresa_model import Empresa
from app.shared.contrato_base import ContratoBase


class EmpresaResumo(ContratoBase):
    """Contrato próprio da fronteira — não é o model, não é o schema do router
    de empresas."""

    id: str
    nome: str
    # Nome curto do dia a dia ("Matriz", "BSB"). Nulo enquanto ninguém cadastrar:
    # quem exibe decide o que fazer nesse caso, a fronteira não inventa valor.
    apelido: str | None = None


def listar_resumo(sessao_db: Session) -> list[EmpresaResumo]:
    """Todas as empresas do cadastro (matriz e filiais), ordenadas por nome.

    Existe para o filtro por empresa da expedição. Antes a tela montava a lista
    a partir dos pedidos carregados na página, e a matriz simplesmente não
    aparecia quando nenhum pedido dela caía naquela página — filtro que só
    oferece o que já está na tela não filtra nada.

    Devolve inclusive empresa inativa: se existe pedido dela na base, o
    coordenador precisa conseguir filtrar por ela.
    """
    linhas = (
        sessao_db.query(Empresa.id, Empresa.nome_fantasia, Empresa.apelido)
        .filter(Empresa.sync_deleted_at.is_(None))
        .order_by(Empresa.nome_fantasia.asc())
        .all()
    )
    return [
        EmpresaResumo(id=id_, nome=nome, apelido=apelido) for id_, nome, apelido in linhas
    ]


def obter_resumos(sessao_db: Session, empresa_ids: list[str]) -> dict[str, EmpresaResumo]:
    """empresa_id -> nome fantasia e apelido, numa consulta só.

    Canal usado pela expedição, que mostra e filtra os pedidos por empresa
    (matriz e filiais) na listagem. Os dois campos saem juntos porque saem da
    mesma linha: nome e apelido da mesma empresa não justificam uma consulta
    cada."""
    if not empresa_ids:
        return {}
    linhas = (
        sessao_db.query(Empresa.id, Empresa.nome_fantasia, Empresa.apelido)
        .filter(Empresa.id.in_(empresa_ids), Empresa.sync_deleted_at.is_(None))
        .all()
    )
    return {
        id_: EmpresaResumo(id=id_, nome=nome, apelido=apelido) for id_, nome, apelido in linhas
    }


def obter_id_por_sistema_origem_id(sessao_db: Session, sistema_origem_id: str) -> str | None:
    """Só leitura — devolve o id primitivo, nunca o model. Canal usado por
    outros domínios (ex: pedidos) para resolver uma empresa pelo id do
    sistema de origem sem importar `empresa_service`."""
    empresa = (
        sessao_db.query(Empresa)
        .filter(Empresa.sistema_origem_id == sistema_origem_id, Empresa.sync_deleted_at.is_(None))
        .first()
    )
    return empresa.id if empresa else None


def obter_sistema_origem_id(sessao_db: Session, empresa_id: str) -> str | None:
    """O caminho inverso de `obter_id_por_sistema_origem_id`: o código da
    empresa no ERP a partir do nosso id.

    É LEITURA do campo de vínculo, não escrita — a regra de nunca apagar
    `sistema_origem_id` (ver ARCHITECTURE.md) não se aplica aqui. Existe porque
    o ERP identifica o pedido por EMPRESA_ID + PEDIDO, e os dois códigos são
    dele, não nossos.
    """
    empresa = (
        sessao_db.query(Empresa)
        .filter(Empresa.id == empresa_id, Empresa.sync_deleted_at.is_(None))
        .first()
    )
    return empresa.sistema_origem_id if empresa else None
