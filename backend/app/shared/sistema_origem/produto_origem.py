"""
Rotinas de produto no sistema de origem (tabela `fat_produtos` do ERP).

Toda a conversa com o Oracle sobre produto mora aqui: quem chama passa o código
do produto no ERP e o valor, e recebe o resultado. Nenhum outro lugar do projeto
monta SQL para `fat_produtos`.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.sistema_origem import conexao
from app.shared.sistema_origem.config import obter_oracle_settings

# Bind de parâmetro, nunca interpolação de string. O código de barras vem de um
# leitor (ou da digitação de um operador) e é entrada externa como qualquer
# outra — concatenar isso no SQL é injeção esperando acontecer.
# A coluna é CODIGO_BARRA, no SINGULAR — conferido no dicionário de dados do
# ERP (all_tab_columns). O nome usado no cadastro daqui é `codigo_barra_notas`
# — justamente por ser este o código que sai na nota — e ele não existe lá, o
# que faria o UPDATE morrer com ORA-00904 se fosse usado no SQL do Oracle.
# VARCHAR2(20): cabe EAN-13 e DUN-14 com folga.
_SQL_ATUALIZAR_CODIGO_BARRAS = """
    update fat_produtos
       set USUARIO_ALTERACAO = :usuario_alteracao,
           DATA_HORA_ALTERACAO = SYSDATE,
           CODIGO_BARRA = :codigo_barras
     where CODIGO_PRO = :codigo_pro
"""

_SQL_LER_CODIGO_BARRAS = """
    select CODIGO_BARRA
      from fat_produtos
     where CODIGO_PRO = :codigo_pro
"""

# Espelho local: a tabela `produtos` deste banco é cópia do cadastro do ERP,
# trazida pela integração. Atualizá-la aqui não é a expedição gravando no
# domínio de produtos — é a camada de integração sincronizando o espelho do que
# acabou de mudar na origem, que é justamente o trabalho dela.
#
# SQL direto, sem importar o model `Produto`: `shared/` não pode importar de
# `domains/` (ver ARCHITECTURE.md), e para a integração isto é uma tabela, não
# um objeto de domínio. `sync_version` é incrementado à mão pelo mesmo motivo —
# `incrementar_versao` trabalha sobre instância do ORM.
#
# `sync_synced_at` fica intocado de propósito: quem escreve nele é o processo de
# sincronização, e mais ninguém.
_SQL_ESPELHO_LOCAL = text(
    """
    update produtos
       set codigo_barra_notas = :codigo_barras,
           sync_updated_at = :agora,
           sync_version = sync_version + 1
     where id = :produto_id
       and sync_deleted_at is null
    """
)


class ProdutoNaoEncontradoNaOrigem(RuntimeError):
    """O `codigo_pro` não existe no ERP. Acontece quando o cadastro daqui
    aponta para um produto que foi apagado lá."""


class AlteracaoNaoConfirmada(RuntimeError):
    """O UPDATE rodou mas a releitura no ERP não trouxe o valor novo. Sem
    confirmação, o espelho local NÃO é tocado — melhor os dois bancos com o
    valor velho do que este banco dizendo uma coisa e o ERP dizendo outra."""


@dataclass(frozen=True)
class CodigoBarrasAtualizado:
    """O antes e o depois — é o que alimenta o histórico de alteração."""

    valor_antigo: str | None
    valor_novo: str


def atualizar_codigo_barras(
    sessao_db: Session, produto_id: str, codigo_pro: str, codigo_barras: str
) -> CodigoBarrasAtualizado:
    """Grava o código de barras no ERP e, se confirmado lá, no espelho local.

    A ordem importa e não é negociável:

    1. Lê o valor atual no ERP — o valor antigo é obrigatório no histórico e,
       depois do UPDATE, não existe mais em lugar nenhum.
    2. Faz o UPDATE no ERP, que é a fonte da verdade do cadastro.
    3. **Relê no ERP para confirmar.** `rowcount` diz que o comando encontrou a
       linha, não que o valor ficou gravado — trigger, coluna calculada ou
       regra do ERP podem ter mudado o que foi escrito.
    4. Só então atualiza o espelho local.

    Se a confirmação falhar, o local não é tocado: dois bancos com o valor velho
    é uma situação recuperável; este banco discordando do ERP não é.

    O espelho local existe porque a bipagem consulta a tabela `produtos` daqui.
    Sem ele, o operador corrigiria o cadastro e a leitura seguinte continuaria
    sendo recusada até a integração rodar.

    **Hoje nenhum caminho da aplicação chama esta função.** A correção de código
    de barras a partir da bipagem foi removida da expedição: o produto passou a
    ter vários códigos (`produto_codigo_barras`) e o ERP tem um só, então o que
    a correção deve fazer no ERP ainda é uma decisão em aberto. A rotina fica
    aqui porque a conversa com `fat_produtos` continua sendo deste arquivo —
    quando a decisão vier, ela é o ponto de partida, não algo a reescrever.

    Não faz commit no MySQL — quem chamou commita junto com o histórico, na
    mesma transação. O commit no Oracle já aconteceu e é irreversível: se a
    transação local falhar depois, o ERP fica correto e o espelho volta ao
    valor velho até a próxima sincronização.
    """
    settings = obter_oracle_settings()

    atual = conexao.buscar_um(_SQL_LER_CODIGO_BARRAS, {"codigo_pro": codigo_pro})
    if atual is None:
        raise ProdutoNaoEncontradoNaOrigem(
            f"Produto '{codigo_pro}' não encontrado no sistema de origem."
        )

    afetadas = conexao.executar(
        _SQL_ATUALIZAR_CODIGO_BARRAS,
        {
            "usuario_alteracao": settings.oracle_usuario_alteracao,
            "codigo_barras": codigo_barras,
            "codigo_pro": codigo_pro,
        },
    )
    if afetadas == 0:
        raise ProdutoNaoEncontradoNaOrigem(
            f"Nenhuma linha atualizada para o produto '{codigo_pro}'."
        )

    confirmado = conexao.buscar_um(_SQL_LER_CODIGO_BARRAS, {"codigo_pro": codigo_pro})
    if confirmado is None or confirmado.get("codigo_barra") != codigo_barras:
        raise AlteracaoNaoConfirmada(
            f"O sistema de origem não confirmou o novo código de barras do produto "
            f"'{codigo_pro}'. Nada foi alterado no cadastro local."
        )

    _atualizar_espelho_local(sessao_db, produto_id, codigo_barras)

    return CodigoBarrasAtualizado(valor_antigo=atual.get("codigo_barra"), valor_novo=codigo_barras)


def _atualizar_espelho_local(sessao_db: Session, produto_id: str, codigo_barras: str) -> None:
    """Reflete no cadastro local o que já está confirmado no ERP."""
    sessao_db.execute(
        _SQL_ESPELHO_LOCAL,
        {
            "codigo_barras": codigo_barras,
            "agora": datetime.now(timezone.utc).replace(tzinfo=None),
            "produto_id": produto_id,
        },
    )
