"""
Canal de leitura do domínio `estoque` para os outros domínios.

Só leitura: nenhuma função daqui escreve, altera, apaga ou dá `commit()`, e
nenhuma devolve model SQLAlchemy (ver ARCHITECTURE.md → "Como se faz: o arquivo
de fronteira `<dominio>_publico.py`").
"""

from decimal import Decimal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.domains.estoque.estoque_model import EstoqueLote
from app.shared.contrato_base import ContratoBase


def obter_ids_de_lotes(
    sessao_db: Session, empresa_id: str, pares_produto_lote: list[tuple[str, str]]
) -> dict[tuple[str, str], str]:
    """(produto_id, lote) -> `estoque_lotes.id`, numa consulta só.

    Existe porque quem fala de lote fora daqui fala pelo texto — a linha do
    pedido guarda `lote` como string, e é o ERP quem escolhe esse texto. Para
    chegar no endereço, porém, é preciso o id da linha de `estoque_lotes`, que
    é o que o domínio `enderecamento` referencia.

    A empresa entra no filtro porque lote é por empresa: o mesmo número de lote
    existe na matriz e na filial, e são saldos diferentes, em galpões
    diferentes. Sem ela a expedição de uma filial acharia o endereço da outra.

    Par sem lote cadastrado simplesmente não aparece no retorno — quem consome
    trata a ausência (mercadoria que ainda não foi endereçada é caso normal, não
    erro).
    """
    lotes = {lote for _, lote in pares_produto_lote if lote}
    produtos = {produto_id for produto_id, lote in pares_produto_lote if lote}
    if not lotes or not produtos:
        return {}

    linhas = (
        sessao_db.query(EstoqueLote.produto_id, EstoqueLote.lote, EstoqueLote.id)
        .filter(
            EstoqueLote.empresa_id == empresa_id,
            EstoqueLote.produto_id.in_(produtos),
            EstoqueLote.lote.in_(lotes),
            EstoqueLote.sync_deleted_at.is_(None),
        )
        .all()
    )
    procurados = {par for par in pares_produto_lote if par[1]}
    return {
        (produto_id, lote): lote_id
        for produto_id, lote, lote_id in linhas
        if (produto_id, lote) in procurados
    }


class LoteResumo(ContratoBase):
    """O que outro domínio precisa saber de uma linha de `estoque_lotes`.

    Contrato próprio da borda — não é o model.
    """

    id: str
    produto_id: str
    lote: str
    quantidade: Decimal


def obter_lotes(sessao_db: Session, estoque_lotes_ids: list[str]) -> dict[str, LoteResumo]:
    """`estoque_lotes.id` -> produto e texto do lote, numa consulta só.

    Contrapartida de `obter_ids_de_lotes`: quem guardou a FK (o vínculo de
    endereço) precisa exibir de que produto e de que lote aquela linha é.
    """
    if not estoque_lotes_ids:
        return {}
    linhas = (
        sessao_db.query(
            EstoqueLote.id, EstoqueLote.produto_id, EstoqueLote.lote, EstoqueLote.quantidade
        )
        .filter(
            EstoqueLote.id.in_(set(estoque_lotes_ids)),
            EstoqueLote.sync_deleted_at.is_(None),
        )
        .all()
    )
    return {
        id_: LoteResumo(
            id=id_, produto_id=produto_id, lote=lote, quantidade=Decimal(quantidade or 0)
        )
        for id_, produto_id, lote, quantidade in linhas
    }


def buscar_ids_de_lotes(
    sessao_db: Session,
    produto_ids: list[str] | None = None,
    texto_lote: str | None = None,
    empresa_id: str | None = None,
) -> list[str]:
    """Ids de `estoque_lotes` de um conjunto de produtos e/ou cujo texto do lote
    casa com um termo. As duas condições se somam por OU.

    Existe para a consulta de endereçamento conseguir filtrar por produto sem
    consultar `estoque_lotes` por conta própria: ela traduz "o produto que a
    pessoa digitou" em ids de lote, e depois filtra a própria tabela dela.

    Devolve lista vazia quando não recebe nenhum critério — "sem filtro" é
    responsabilidade de quem chama, não desta função inventar "todos".
    """
    condicoes = []
    if produto_ids:
        condicoes.append(EstoqueLote.produto_id.in_(set(produto_ids)))
    texto_lote = (texto_lote or "").strip()
    if texto_lote:
        condicoes.append(EstoqueLote.lote.ilike(f"%{texto_lote}%"))
    if not condicoes:
        return []

    consulta = sessao_db.query(EstoqueLote.id).filter(
        EstoqueLote.sync_deleted_at.is_(None), or_(*condicoes)
    )
    if empresa_id:
        consulta = consulta.filter(EstoqueLote.empresa_id == empresa_id)
    return [id_ for (id_,) in consulta.all()]


def obter_id_do_lote(
    sessao_db: Session, empresa_id: str, produto_id: str, lote: str
) -> str | None:
    """Versão de um par só de `obter_ids_de_lotes` — usada pelo `enderecamento`
    quando a integração manda o vínculo pelo texto do lote em vez do id."""
    encontrados = obter_ids_de_lotes(sessao_db, empresa_id, [(produto_id, lote)])
    return encontrados.get((produto_id, lote))
