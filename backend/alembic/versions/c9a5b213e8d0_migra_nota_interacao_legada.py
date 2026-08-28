"""entregas: migra os dados de nota_interacao para o formato novo

Revision ID: c9a5b213e8d0
Revises: b8d4e0f61a37
Create Date: 2026-08-23 00:00:00.000000

Traz as interações do sistema antigo em Streamlit para as tabelas novas. A
tabela `nota_interacao` vive NESTE MESMO banco, então não há exportação nem
arquivo intermediário — é um INSERT ... SELECT com tradução no meio.

O que a tradução resolve:

1. `empresa_id` era o CNPJ em texto ('14.115.388/0001-80') → vira FK para
   `empresas.id`.
2. `usuario_alteracao` era o código do funcionário em varchar(5), sem zero à
   esquerda ('233') → vira FK para `usuarios.id`, casando com
   `usuarios.sistema_origem_id` ('00233') via LPAD.
3. `status` era a frase exibida, com e sem acento na mesma coluna
   ('Em trânsito', 'Devolucao parcial') → vira slug ('em_transito').
4. Uma nota só existia implicitamente, repetida em cada interação → vira uma
   linha em `entrega_notas`.

`nota_interacao` NÃO é apagada nem alterada: continua intacta como plano B até
alguém confirmar que a tela nova está correta.

As linhas de `entrega_notas` criadas aqui são ESQUELETOS — o legado só tem
empresa, número da nota e pedido. Cliente, valor, itens e mapa de carga chegam
depois, pela API, e o upsert de `entrega_service.registrar_nota` completa a
mesma linha porque casa pela mesma chave natural
(empresa_id, numero_nota, serie, pedido). `serie` migra como string vazia
porque a tabela legada não tem essa coluna.

"""

import unicodedata
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c9a5b213e8d0"
down_revision: Union[str, Sequence[str], None] = "b8d4e0f61a37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_PADRAO = "aguardando_embarque"

# A frase do legado (normalizada: maiúscula, sem acento) → o slug novo.
_MAPA_STATUS = {
    "AGUARDANDO EMBARQUE": "aguardando_embarque",
    "COM OCORRENCIA": "com_ocorrencia",
    "EM TRANSITO": "em_transito",
    "ENTREGA REALIZADA": "entrega_realizada",
    "RECUSADA NO ATO DA ENTREGA": "recusada_no_ato",
    "RETIDA PARA FISCALIZACAO": "retida_fiscalizacao",
    "DEVOLUCAO PARCIAL": "devolucao_parcial",
}


def _normalizar(texto: str | None) -> str:
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto.strip().upper())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def _traduzir_status(status: str | None) -> str:
    """Status nulo vira 'aguardando_embarque' — decisão tomada com o Deyverson:
    são 4 linhas antigas, e o primeiro estado de qualquer entrega é esse."""
    return _MAPA_STATUS.get(_normalizar(status), _STATUS_PADRAO)


def upgrade() -> None:
    conexao = op.get_bind()
    inspetor = sa.inspect(conexao)

    if "nota_interacao" not in inspetor.get_table_names():
        # Ambiente novo (ou os testes, em SQLite): não há legado a migrar.
        print("nota_interacao não existe neste banco — nada a migrar.")
        return

    ja_migrado = conexao.execute(
        sa.text("SELECT COUNT(*) FROM entrega_nota_interacoes")
    ).scalar()
    if ja_migrado:
        print(f"entrega_nota_interacoes já tem {ja_migrado} linhas — migração ignorada.")
        return

    # --- Passo 0: o usuário 00200 foi cadastrado à mão e ficou sem
    # sistema_origem_id. Sem ele, 4 interações não teriam autor — e usuario_id
    # é NOT NULL. Preenche só se estiver vazio, para a migração poder rodar
    # mais de uma vez sem sobrescrever nada.
    conexao.execute(
        sa.text(
            """UPDATE usuarios
               SET sistema_origem_id = '00200',
                   sync_updated_at = NOW(),
                   sync_version = sync_version + 1
               WHERE usuario = '00200' AND sistema_origem_id IS NULL"""
        )
    )

    # --- Passo 1: CNPJ do legado → empresas.id
    empresas = {
        cnpj: empresa_id
        for empresa_id, cnpj in conexao.execute(sa.text("SELECT id, cnpj FROM empresas"))
    }

    # --- Passo 2: código do funcionário → usuarios.id, só por sistema_origem_id
    usuarios = {
        sistema_origem_id: usuario_id
        for usuario_id, sistema_origem_id in conexao.execute(
            sa.text("SELECT id, sistema_origem_id FROM usuarios WHERE sistema_origem_id IS NOT NULL")
        )
    }

    linhas = list(
        conexao.execute(
            sa.text(
                """SELECT id, empresa_id, numero_nota, pedido, observacao,
                          usuario_alteracao, status, data_cadastro, updated_at, deleted_at
                   FROM nota_interacao
                   ORDER BY data_cadastro, id"""
            )
        )
    )

    # Falha ANTES de gravar qualquer coisa se algum código de usuário não
    # resolver: `usuario_id` é obrigatório, e migrar interação sem autor
    # destruiria a informação de quem registrou o quê.
    codigos_sem_usuario = {
        linha.usuario_alteracao
        for linha in linhas
        if (linha.usuario_alteracao or "").rjust(5, "0") not in usuarios
    }
    if codigos_sem_usuario:
        raise RuntimeError(
            "Códigos de funcionário sem usuário correspondente em "
            f"usuarios.sistema_origem_id: {sorted(codigos_sem_usuario)}. "
            "Cadastre-os (ou preencha o sistema_origem_id) antes de migrar."
        )

    cnpjs_sem_empresa = {linha.empresa_id for linha in linhas if linha.empresa_id not in empresas}
    if cnpjs_sem_empresa:
        raise RuntimeError(
            f"CNPJs sem empresa cadastrada: {sorted(cnpjs_sem_empresa)}."
        )

    # --- Passo 3: uma linha de entrega_notas por documento distinto
    notas: dict[tuple, str] = {}
    ultimo_status: dict[str, str] = {}
    ultima_entrega: dict[str, object] = {}
    # A sequência do evento dentro da nota. Como o SELECT vem ordenado por
    # data_cadastro, ela reproduz a ordem cronológica original — inclusive para
    # as interações que caíram no mesmo segundo, que na tabela legada não
    # tinham como ser desempatadas.
    sequencias: dict[str, int] = {}

    for linha in linhas:
        empresa_id = empresas[linha.empresa_id]
        chave = (empresa_id, linha.numero_nota, "", linha.pedido or "")

        if chave not in notas:
            nota_id = str(uuid.uuid4())
            notas[chave] = nota_id
            conexao.execute(
                sa.text(
                    """INSERT INTO entrega_notas
                        (id, empresa_id, numero_nota, serie, pedido, tipo_nota,
                         valor_total, cliente_nome, termolabil, status_atual,
                         sync_created_at, sync_updated_at, sync_version)
                       VALUES
                        (:id, :empresa_id, :numero_nota, '', :pedido, 'outros',
                         0, '', 0, :status, :criado, :criado, 1)"""
                ),
                {
                    "id": nota_id,
                    "empresa_id": empresa_id,
                    "numero_nota": linha.numero_nota,
                    "pedido": linha.pedido or "",
                    "status": _STATUS_PADRAO,
                    "criado": linha.data_cadastro,
                },
            )

        nota_id = notas[chave]
        status = _traduzir_status(linha.status)
        sequencias[nota_id] = sequencias.get(nota_id, 0) + 1

        # --- Passo 4: a interação
        conexao.execute(
            sa.text(
                """INSERT INTO entrega_nota_interacoes
                    (id, entrega_nota_id, sequencia, status, observacao, usuario_id,
                     sync_created_at, sync_updated_at, sync_deleted_at, sync_version)
                   VALUES
                    (:id, :nota_id, :sequencia, :status, :observacao, :usuario_id,
                     :criado, :atualizado, :apagado, 1)"""
            ),
            {
                "id": str(uuid.uuid4()),
                "nota_id": nota_id,
                "sequencia": sequencias[nota_id],
                "status": status,
                "observacao": linha.observacao or "",
                "usuario_id": usuarios[(linha.usuario_alteracao or "").rjust(5, "0")],
                # sync_created_at recebe data_cadastro, NÃO updated_at: é por
                # ele que a timeline ordena, e usar a data de alteração faria a
                # linha do tempo migrada nascer fora de ordem.
                "criado": linha.data_cadastro,
                "atualizado": linha.updated_at or linha.data_cadastro,
                "apagado": linha.deleted_at,
            },
        )

        # Interação apagada no legado não define o status atual da nota.
        if linha.deleted_at is None:
            ultimo_status[nota_id] = status
            ultima_entrega[nota_id] = linha.data_cadastro

    # --- Passo 5: status_atual = status da última interação viva de cada nota
    for nota_id, status in ultimo_status.items():
        conexao.execute(
            sa.text(
                """UPDATE entrega_notas
                   SET status_atual = :status,
                       data_entrega_realizada = :entregue_em
                   WHERE id = :id"""
            ),
            {
                "id": nota_id,
                "status": status,
                "entregue_em": (
                    ultima_entrega[nota_id] if status == "entrega_realizada" else None
                ),
            },
        )

    print(f"Migradas {len(linhas)} interações em {len(notas)} notas.")


def downgrade() -> None:
    """Esvazia as tabelas novas.

    É seguro apagar tudo — e não só o que veio do legado — porque `nota_interacao`
    continua intacta: subir a migração de novo reconstrói os dados a partir dela.
    O que se perde são as interações registradas na tela nova depois da migração,
    então não desça esta revisão depois que o time começar a usar a tela.
    """
    conexao = op.get_bind()
    conexao.execute(sa.text("DELETE FROM entrega_nota_interacoes"))
    conexao.execute(sa.text("DELETE FROM entrega_nota_itens"))
    conexao.execute(sa.text("DELETE FROM entrega_notas"))
