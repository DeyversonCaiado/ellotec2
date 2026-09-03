"""
Regra de negócio das operações que este sistema executa DENTRO do ERP (GESTCOM).

Este service é diferente de todos os outros do projeto, do mesmo jeito que
`cotacoes/` é: ele **não usa a sessão do SQLAlchemy e não toca o nosso MySQL**.
Tudo aqui acontece no Oracle do ERP, por
`app/shared/sistema_origem/gestcom/conexao.py` — ver backend/ARCHITECTURE.md →
"Domínio que ESCREVE no sistema de origem".

Por isso o domínio não tem `sistema_origem_model.py`: não existe tabela nossa
para mapear, e mapear o schema do ERP criaria a ilusão de que podemos mudá-lo.

> Não confundir com o pacote `app/shared/sistema_origem/`, que é a
> **infraestrutura** (conexão, config, rotinas de sincronização). Este aqui é o
> **domínio**: a regra de negócio de "o que o ELLOTEC pode mandar o ERP fazer".
> O domínio usa a infraestrutura; nunca o contrário.

Hoje existe uma operação só (finalizar a conferência do pedido). O nome do
domínio é do assunto e não dela de propósito — outras funções do ERP virão para
cá, e renomear domínio depois custa rota, permissão e tela.
"""

from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status

from app.shared.sistema_origem.gestcom.conexao import OracleIndisponivel, conectar

# ---------------------------------------------------------------------------
# Constantes do ERP
#
# Não são configuração: são o valor que o ERP espera ver gravado quando a baixa
# vem por ESTE canal. Trocar qualquer uma delas muda o que o pessoal do
# faturamento enxerga na tela do GESTCOM, então o lugar delas é aqui, com nome,
# e não digitadas dentro do SQL.
# ---------------------------------------------------------------------------

# O formulário do ERP que registra a operação no log de acessos (FAT_POLICE).
FORMULARIO = "Situação de Pedidos"

# De onde a baixa veio. Fixo para todos os coletores: o ERP usa isso para
# separar o que foi feito pelo ELLOTEC do que foi feito na tela dele.
TERMINAL = "NOTRESFIN-ELL"

# Status que o pedido assume quando a conferência fecha.
STATUS_FECHADO = "FEC"

# Status em que o pedido PRECISA estar para poder ser finalizado. Qualquer
# outro significa que alguém já mexeu no pedido do lado de lá (faturou,
# cancelou, embarcou) e a nossa finalização chegou tarde.
STATUS_EXIGIDO = "PED"

# A marca gravada no pedido quando a baixa vem por este canal. `MARCA_PEDIDO` é
# VARCHAR2(20) no ERP (conferido em `all_tab_columns`), então os 8 caracteres
# cabem — o "VARCHAR[6]" da especificação original era o tamanho do literal
# 'OUTROS' que estava ali antes, não a largura da coluna.
MARCA_PEDIDO = "DIVERSOS"

# Limites das colunas do ERP, conferidos em `all_tab_columns` e não estimados.
# Estão aqui porque um valor grande demais não volta como erro de negócio: volta
# como ORA-12899 no meio da transação.
#
# `FAT_POLICE.FUNCIONARIO` é VARCHAR2(5) — e é ele que manda, porque
# `FAT_CAPAPEDIDO.CONFERIDOR`, que recebe o mesmo código, é VARCHAR2(20). Entre
# dois limites para o mesmo valor, vale o menor.
TAMANHO_FUNCIONARIO = 5
# `ESPECIE_PEDIDO` é VARCHAR2(10).
TAMANHO_ESPECIE = 10
# `VOLUME_PEDIDO` também é VARCHAR2(10) — TEXTO, não número, apesar de a
# especificação da tela do ERP chamar o parâmetro de FLOAT. Ver a conversão em
# `_volume_para_o_erp`.
TAMANHO_VOLUME = 10


_SQL_STATUS_ATUAL = """
    SELECT STATUS
    FROM FAT_CAPAPEDIDO
    WHERE EMPRESA_ID = :empresa_id
      AND PEDIDO = :pedido
    FOR UPDATE
"""

_SQL_REGISTRAR_ACESSO = """
    INSERT INTO FAT_POLICE (
        FUNCIONARIO,
        FORMULARIO,
        DATA_INICIO,
        DATA_FINAL,
        TERMINAL,
        DATA_HORA_ALTERACAO
    ) VALUES (
        :funcionario,
        :formulario,
        SYSDATE,
        SYSDATE,
        :terminal,
        SYSDATE
    )
"""

_SQL_FECHAR_PEDIDO = """
    UPDATE FAT_CAPAPEDIDO SET
        STATUS                    = :status,
        CONFERIDOR                = :conferidor,
        DATA_HORA_CONFERENCIA     = SYSDATE,
        DATA_HORA_ALTERACAO       = SYSDATE,
        LIBERACAO_SEM_CONFERENCIA = :liberacao_sem_conferencia,
        VOLUME_PEDIDO             = :volume,
        ESPECIE_PEDIDO            = :especie,
        PESO_LIQUIDO              = :peso_liquido,
        PESO_BRUTO                = :peso_bruto,
        MARCA_PEDIDO              = :marca_pedido
    WHERE EMPRESA_ID = :empresa_id
      AND PEDIDO     = :pedido
"""


def _validar_entrada(
    usuario_sistema_origem_id: str, especie: str, quem: str = ""
) -> tuple[str, str]:
    """As duas colunas curtas do ERP, checadas antes de abrir conexão.

    `FAT_POLICE.FUNCIONARIO` é VARCHAR2(5) e `ESPECIE_PEDIDO` é VARCHAR2(10): o
    Oracle não recusa estouro com uma mensagem útil, recusa com ORA-12899 depois
    de a transação já ter começado.

    `quem` é o login de quem clicou, e entra na mensagem de recusa. Sem ele a
    frase "seu usuário não tem vínculo" obriga a adivinhar de qual conta se
    está falando — e a conta que clicou não é necessariamente a que o operador
    acha que está usando (contas administrativas nossas, como `admin`, não têm
    contrapartida no ERP e caem exatamente aqui).
    """
    funcionario = (usuario_sistema_origem_id or "").strip()
    if not funcionario:
        identificacao = f" ('{quem}')" if quem else ""
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O usuário com que você está logado{identificacao} não tem vínculo com o "
                "sistema de origem, então o ERP não tem em nome de quem registrar a "
                "conferência. Entre com o seu usuário do GESTCOM para finalizar por aqui."
            ),
        )
    if len(funcionario) > TAMANHO_FUNCIONARIO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O código do seu usuário no sistema de origem ('{funcionario}') tem mais "
                f"de {TAMANHO_FUNCIONARIO} caracteres e não cabe no campo do ERP."
            ),
        )

    # Maiúscula garantida aqui, e não só no front: o front é conveniência, o
    # backend é a barreira — o ERP grava o que chegar.
    especie_normalizada = (especie or "").strip().upper()
    if not especie_normalizada:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Informe a espécie da embalagem (ex.: CX).",
        )
    if len(especie_normalizada) > TAMANHO_ESPECIE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A espécie da embalagem tem no máximo {TAMANHO_ESPECIE} caracteres.",
        )
    return funcionario, especie_normalizada


def _volume_para_o_erp(volume: Decimal) -> str:
    """A contagem de volumes como o ERP a guarda: texto de dígitos, sem separador.

    `VOLUME_PEDIDO` é `VARCHAR2(10)`, não numérico — a especificação da tela do
    ERP chama o parâmetro de FLOAT, mas a coluna é texto, e o que o próprio ERP
    grava lá são inteiros puros ('0', '4').

    Por isso a string é montada AQUI e não deixada para o Oracle converter: um
    bind numérico viraria texto pelo `NLS_NUMERIC_CHARACTERS` da sessão, que em
    português usa vírgula — e o pedido acabaria com `4,0` gravado onde o resto
    do sistema tem `4`. O tipo de divergência que ninguém procura, porque os
    dois "parecem" quatro.
    """
    texto = str(int(volume))
    if len(texto) > TAMANHO_VOLUME:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A quantidade de volumes não cabe no campo do ERP ({TAMANHO_VOLUME} dígitos).",
        )
    return texto


def _exigir_status_pedido(cursor: Any, empresa_sistema_origem_id: str, pedido_sistema_origem_id: str) -> None:
    """O pedido só pode ser fechado se ainda estiver como `PED` no ERP.

    O `FOR UPDATE` do SELECT não é detalhe: sem ele, entre ler o status e
    gravar o `FEC` cabe o faturamento do pedido pelo outro lado, e a nossa
    baixa passaria por cima dele sem ninguém perceber.
    """
    cursor.execute(
        _SQL_STATUS_ATUAL,
        {"empresa_id": empresa_sistema_origem_id, "pedido": pedido_sistema_origem_id},
    )
    linha = cursor.fetchone()
    if linha is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Pedido {pedido_sistema_origem_id} não foi encontrado no sistema de "
                f"origem (empresa {empresa_sistema_origem_id})."
            ),
        )

    status_atual = (linha[0] or "").strip().upper()
    if status_atual != STATUS_EXIGIDO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O pedido está como '{status_atual}' no sistema de origem e só pode ser "
                f"finalizado enquanto estiver como '{STATUS_EXIGIDO}'. Alguém já mexeu "
                "nele por lá — procure o faturamento antes de tentar de novo."
            ),
        )


def finalizar_pedido(
    *,
    empresa_sistema_origem_id: str,
    pedido_sistema_origem_id: str,
    usuario_sistema_origem_id: str,
    volume: Decimal,
    especie: str,
    peso_liquido: Decimal,
    peso_bruto: Decimal,
    usuario_login: str = "",
) -> None:
    """Fecha a conferência do pedido no ERP: registra o acesso e grava o `FEC`.

    Uma conexão só e um `commit` só. Os três comandos (checar status, registrar
    o acesso, fechar o pedido) são a MESMA transação no Oracle — se o UPDATE
    falhar, a linha do log não fica sobrando dizendo que alguém conferiu.

    **Não é idempotente**, e não pode ser: rodar duas vezes é impossível na
    prática porque a segunda encontra o pedido já como `FEC` e para no
    `_exigir_status_pedido`. É essa checagem que faz o papel da trava.

    Falha de infraestrutura (Oracle fora, credencial errada, Instant Client
    ausente) vira **503**, não 500: não é defeito nosso nem erro do operador —
    é o canal indisponível, e a tela precisa dizer isso com essas palavras.
    """
    funcionario, especie_normalizada = _validar_entrada(
        usuario_sistema_origem_id, especie, usuario_login
    )

    try:
        with conectar() as conexao:
            cursor = conexao.cursor()
            try:
                _exigir_status_pedido(
                    cursor, empresa_sistema_origem_id, pedido_sistema_origem_id
                )

                cursor.execute(
                    _SQL_REGISTRAR_ACESSO,
                    {
                        "funcionario": funcionario,
                        "formulario": FORMULARIO,
                        "terminal": TERMINAL,
                    },
                )

                cursor.execute(
                    _SQL_FECHAR_PEDIDO,
                    {
                        "status": STATUS_FECHADO,
                        "conferidor": funcionario,
                        "liberacao_sem_conferencia": funcionario,
                        # Texto, não número — ver `_volume_para_o_erp`.
                        "volume": _volume_para_o_erp(volume),
                        "especie": especie_normalizada,
                        "peso_liquido": float(peso_liquido),
                        "peso_bruto": float(peso_bruto),
                        "marca_pedido": MARCA_PEDIDO,
                        "empresa_id": empresa_sistema_origem_id,
                        "pedido": pedido_sistema_origem_id,
                    },
                )
                if cursor.rowcount != 1:
                    # Chegar aqui significa que o pedido sumiu entre o SELECT
                    # FOR UPDATE e o UPDATE, o que não deveria acontecer. O
                    # rollback vem do `raise` — nada foi commitado ainda.
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "O sistema de origem não confirmou a baixa do pedido. "
                            "Nada foi alterado — tente de novo."
                        ),
                    )

                conexao.commit()
            finally:
                cursor.close()
    except OracleIndisponivel as erro:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Não foi possível falar com o sistema de origem agora, então a "
                "conferência não pôde ser finalizada por este canal. "
                f"Detalhe técnico: {erro}"
            ),
        ) from erro
    except HTTPException:
        # As recusas de negócio já saíram prontas de `_exigir_status_pedido` e
        # da conferência do rowcount — não têm que virar 502 no `except`
        # abaixo. O `close()` da conexão desfaz o que não foi commitado.
        raise
    except Exception as erro:  # noqa: BLE001 - qualquer erro do driver no meio da transação
        # ORA-12899 (valor grande demais), constraint, trigger do ERP: o
        # operador não tem o que fazer com o número do erro, mas quem for
        # olhar o log precisa dele inteiro.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "O sistema de origem recusou a finalização e nada foi alterado lá. "
                f"Detalhe técnico: {erro}"
            ),
        ) from erro
