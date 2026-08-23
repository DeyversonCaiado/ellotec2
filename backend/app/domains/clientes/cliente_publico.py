"""
Canal de leitura de `clientes` para outros domínios (hoje: `expedicao`, que
mostra o endereço de entrega no cabeçalho da lista de separação).

O pedido guarda snapshot só de nome fantasia e CNPJ — o endereço não é
snapshot, e é isso que se quer aqui: a expedição precisa do endereço ATUAL do
cadastro, porque é para lá que a mercadoria vai hoje.
"""

from sqlalchemy.orm import Session

from app.domains.cidades.cidade_model import Cidade
from app.domains.clientes.cliente_model import Cliente
from app.shared.contrato_base import ContratoBase


class CidadeCliente(ContratoBase):
    nome: str
    uf: str


class ClienteResumo(ContratoBase):
    id: str
    codigo: str | None
    razao_social: str
    nome_fantasia: str
    cpf_cnpj: str
    endereco: str
    bairro: str | None
    cep: str | None
    cidade_nome: str
    cidade_uf: str


def obter_cidades(sessao_db: Session, cliente_ids: list[str]) -> dict[str, CidadeCliente]:
    """cliente_id -> cidade, numa consulta só. Existe para a listagem da
    expedição, que mostra a cidade de cada pedido: um `obter_resumo` por linha
    seriam N consultas (e N joins de endereço) para dois campos."""
    if not cliente_ids:
        return {}
    linhas = (
        sessao_db.query(Cliente.id, Cidade.nome, Cidade.uf)
        .join(Cidade, Cidade.id == Cliente.cidade_id)
        .filter(Cliente.id.in_(cliente_ids), Cliente.sync_deleted_at.is_(None))
        .all()
    )
    return {cliente_id: CidadeCliente(nome=nome, uf=uf) for cliente_id, nome, uf in linhas}


def obter_resumo(sessao_db: Session, cliente_id: str) -> ClienteResumo | None:
    cliente = (
        sessao_db.query(Cliente)
        .filter(Cliente.id == cliente_id, Cliente.sync_deleted_at.is_(None))
        .first()
    )
    if cliente is None:
        return None

    partes = [cliente.logradouro, cliente.numero, cliente.complemento]
    return ClienteResumo(
        id=cliente.id,
        codigo=cliente.codigo,
        razao_social=cliente.razao_social,
        nome_fantasia=cliente.nome_fantasia,
        cpf_cnpj=cliente.cpf_cnpj,
        endereco=", ".join(parte for parte in partes if parte),
        bairro=cliente.bairro,
        cep=cliente.cep,
        cidade_nome=cliente.cidade.nome,
        cidade_uf=cliente.cidade.uf,
    )
