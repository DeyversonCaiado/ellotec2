"""
Borda do domínio `enderecamento` para os outros domínios.

Contrato próprio, ids primitivos na entrada, e **nenhuma função dá `commit()`**
— nem as de leitura, nem `baixar_lote`. Ver ARCHITECTURE.md → "Escrita pela
borda: quando um domínio precisa alterar o estado de outro".

Este é o único `_publico.py` do projeto com função de escrita. Ela existe porque
a expedição precisa baixar o saldo do endereço ao finalizar a separação, e quem
é dono do saldo de endereço é este domínio — a expedição pede, não mexe.
"""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.enderecamento.enderecamento_model import EstoqueEndereco, EstoqueEnderecoLote
from app.shared.contrato_base import ContratoBase
from app.shared.sync_helpers import incrementar_versao


class EnderecoDoLote(ContratoBase):
    """Um endereço em que o lote está, com quanto tem nele.

    Contrato próprio da borda — não é o model, não é o schema do router.
    """

    vinculo_id: str
    endereco_id: str
    descricao: str
    quantidade: Decimal


class BaixaAplicada(ContratoBase):
    """O que saiu de cada endereço numa baixa. Devolvido para quem pediu poder
    registrar/exibir de onde a mercadoria saiu."""

    vinculo_id: str
    endereco_id: str
    descricao: str
    quantidade: Decimal


def obter_enderecos_por_lote(
    sessao_db: Session, estoque_lotes_ids: list[str]
) -> dict[str, list[EnderecoDoLote]]:
    """`estoque_lotes.id` -> endereços em que o lote está, com a quantidade de
    cada um, numa consulta só.

    É LISTA, e essa é a parte que importa: um lote se espalha de verdade por
    vários endereços do galpão. Era exatamente por espremer isso num campo só
    que a linha do pedido carregava um endereço — e a consulta da integração
    devolvia uma linha de pedido por endereço, cada uma com a quantidade inteira
    (ver a migração c9e4a71f5b38).

    **Endereço com saldo zero não entra.** A pergunta é "onde o lote ESTÁ", e um
    endereço vazio não é um lugar onde ele está — é um vínculo que sobrou de uma
    baixa anterior ou que a integração criou sem informar quantidade. Mandar
    zero para o coletor é pior que omitir: manda o operador andar até uma
    prateleira vazia. Somar zero também não muda a consistência da expedição, já
    que a soma é a mesma com ou sem essas linhas.

    Quem precisa ver o vínculo zerado — para descobrir que falta informar
    quantidade — é a tela de endereçamento, que lê por `listar_vinculos` e
    mostra o zero destacado. Aqui é o operador com a caixa na mão.

    Ordenado por descrição para a tela do coletor não trocar a ordem entre dois
    carregamentos — e porque é essa mesma ordem que `baixar_lote` consome.
    """
    if not estoque_lotes_ids:
        return {}

    linhas = (
        sessao_db.query(
            EstoqueEnderecoLote.estoque_lotes_id,
            EstoqueEnderecoLote.id,
            EstoqueEndereco.id,
            EstoqueEndereco.descricao,
            EstoqueEnderecoLote.quantidade,
        )
        .join(EstoqueEndereco, EstoqueEndereco.id == EstoqueEnderecoLote.estoque_enderecos_id)
        .filter(
            EstoqueEnderecoLote.estoque_lotes_id.in_(set(estoque_lotes_ids)),
            EstoqueEnderecoLote.quantidade > 0,
            EstoqueEnderecoLote.sync_deleted_at.is_(None),
            EstoqueEndereco.sync_deleted_at.is_(None),
        )
        .order_by(EstoqueEndereco.descricao.asc())
        .all()
    )

    por_lote: dict[str, list[EnderecoDoLote]] = {}
    for lote_id, vinculo_id, endereco_id, descricao, quantidade in linhas:
        por_lote.setdefault(lote_id, []).append(
            EnderecoDoLote(
                vinculo_id=vinculo_id,
                endereco_id=endereco_id,
                descricao=descricao,
                quantidade=Decimal(quantidade or 0),
            )
        )
    return por_lote


def baixar_lote(
    sessao_db: Session,
    estoque_lotes_id: str,
    quantidade: Decimal,
    permitir_saldo_insuficiente: bool = False,
) -> list[BaixaAplicada]:
    """Baixa `quantidade` do lote, distribuindo entre os endereços em que ele
    está. Devolve o que saiu de cada um.

    **NÃO dá `commit()`.** Só altera os objetos na `Session` recebida — quem
    abriu a transação decide commit ou rollback. É essa regra que permite a
    escrita cruzada existir: a baixa e a finalização da separação estão na mesma
    transação, então um erro depois desfaz as duas juntas (ver ARCHITECTURE.md →
    "Escrita pela borda").

    **Não é idempotente.** Chamar duas vezes baixa duas vezes. Quem chama é
    responsável por não finalizar o mesmo processo duas vezes — na expedição,
    quem garante isso é o guarda de `status == "finalizada"`.

    **A ordem de consumo é a alfabética da descrição do endereço**, a mesma que
    `obter_enderecos_por_lote` devolve e que o operador vê na tela. Não é FEFO:
    validade é do lote, e aqui o lote já está escolhido — o que se decide é de
    qual prateleira daquele mesmo lote tirar. Seguir a ordem da tela é o que
    faz o sistema baixar de onde o operador foi.

    Saldo insuficiente levanta 409 e não altera nada: saldo é invariante deste
    domínio, então é ele quem recusa — não quem pediu a baixa.

    **`permitir_saldo_insuficiente` é a exceção de emergência**, e continua sendo
    decisão DESTE domínio: com ela, os endereços do lote são zerados e a baixa
    para no que havia, em vez de recusar. Existe porque a mercadoria de fato saiu
    da prateleira — o que estava errado era o saldo cadastrado — e recusar a
    baixa deixaria estoque fantasma no endereço, que é pior que a divergência
    que se está aceitando. Quem passa `True` tem que ter provado a autorização
    (na expedição, a permissão `expedicao.enderecamento.liberar`).
    """
    if quantidade <= 0:
        return []

    vinculos = (
        sessao_db.query(EstoqueEnderecoLote)
        .join(EstoqueEndereco, EstoqueEndereco.id == EstoqueEnderecoLote.estoque_enderecos_id)
        .filter(
            EstoqueEnderecoLote.estoque_lotes_id == estoque_lotes_id,
            EstoqueEnderecoLote.sync_deleted_at.is_(None),
            EstoqueEndereco.sync_deleted_at.is_(None),
        )
        .order_by(EstoqueEndereco.descricao.asc())
        .all()
    )

    disponivel = sum((Decimal(v.quantidade or 0) for v in vinculos), Decimal(0))
    if disponivel < quantidade and not permitir_saldo_insuficiente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Saldo endereçado insuficiente: os endereços deste lote somam {disponivel}, "
                f"e a baixa pedida é de {quantidade}."
            ),
        )

    # Só depois de conferir o total é que qualquer linha é tocada — assim uma
    # falta no meio do caminho não deixa metade da baixa aplicada na Session.
    restante = quantidade
    aplicadas: list[BaixaAplicada] = []
    for vinculo in vinculos:
        if restante <= 0:
            break
        no_endereco = Decimal(vinculo.quantidade or 0)
        if no_endereco <= 0:
            continue

        saiu = min(no_endereco, restante)
        vinculo.quantidade = no_endereco - saiu
        incrementar_versao(vinculo)
        restante -= saiu

        endereco = sessao_db.get(EstoqueEndereco, vinculo.estoque_enderecos_id)
        aplicadas.append(
            BaixaAplicada(
                vinculo_id=vinculo.id,
                endereco_id=vinculo.estoque_enderecos_id,
                descricao=endereco.descricao if endereco else "",
                quantidade=saiu,
            )
        )

    return aplicadas
