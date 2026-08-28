"""
O SLA de entrega: quantos dias úteis a mercadoria tem para chegar, e quando
vence esse prazo.

Esta é regra de negócio **nossa**, não do ERP — por isso o prazo não chega pela
API junto com a nota. O que a integração manda é UF, cidade e se o produto é
termolábil; o cálculo é aqui.

O código nasceu de um `CASE` de ~100 linhas dentro do SQL do Oracle do sistema
antigo (`gestao_vendas/persistence/oracle.py`). Trazer para Python não é
preferência de estilo: dentro do SQL a matriz não tinha como ser testada, e um
erro de prazo só aparecia quando alguém reclamava que a entrega estava "em
atraso" sem estar.

LIMITAÇÃO CONHECIDA, herdada do sistema antigo: o cálculo pula apenas sábado e
domingo. Feriado nacional conta como dia útil, o que faz o prazo vencer antes do
que deveria e infla o "em atraso". Corrigir exige uma tabela de feriados —
`somar_dias_uteis` já está isolada para receber isso quando for a hora.
"""

import unicodedata
from datetime import date, timedelta

# UF cuja capital tem prazo próprio. DF não entra: o Distrito Federal inteiro é
# tratado como capital pelo sistema antigo, e mantivemos igual.
CAPITAIS: dict[str, str] = {
    "GO": "GOIANIA",
    "SP": "SAO PAULO",
    "BA": "SALVADOR",
    "MG": "BELO HORIZONTE",
    "ES": "VITORIA",
    "RJ": "RIO DE JANEIRO",
    "MS": "CAMPO GRANDE",
    "MT": "CUIABA",
    "TO": "PALMAS",
    "PR": "CURITIBA",
    "SC": "FLORIANOPOLIS",
    "RS": "PORTO ALEGRE",
    "PA": "BELEM",
    "PI": "TERESINA",
    "RN": "NATAL",
    "PE": "RECIFE",
    "AL": "MACEIO",
    "SE": "ARACAJU",
    "PB": "JOAO PESSOA",
    "MA": "SAO LUIS",
    "CE": "FORTALEZA",
    "RO": "PORTO VELHO",
    "AC": "RIO BRANCO",
    "AM": "MANAUS",
    "AP": "MACAPA",
    "RR": "BOA VISTA",
}

# Produto refrigerado tem prazo menor e o mesmo número em capital e interior —
# não pode ficar rodando o país esperando rota consolidar.
_PRAZO_TERMOLABIL: list[tuple[frozenset[str], int]] = [
    (frozenset({"GO", "DF"}), 1),
    (frozenset({"SP"}), 2),
    (frozenset({"BA", "MG", "ES", "RJ", "MS", "MT", "TO"}), 4),
    (frozenset({"PR"}), 5),
    (frozenset({"SC", "RS", "PA", "PI", "RN", "PE", "AL", "SE", "PB", "MA"}), 4),
    (frozenset({"CE", "RO", "AC"}), 6),
    (frozenset({"AM", "AP", "RR"}), 5),
]

_PRAZO_CAPITAL: list[tuple[frozenset[str], int]] = [
    (frozenset({"GO", "DF"}), 1),
    (frozenset({"SP", "BA", "MG", "ES", "RJ", "MS", "MT", "TO"}), 3),
    (frozenset({"PR"}), 5),
    (frozenset({"SC", "RS", "PA", "PI", "RN", "PE", "AL", "SE", "PB", "MA"}), 8),
    (frozenset({"CE", "RO", "AC"}), 10),
    (frozenset({"AM", "AP", "RR"}), 21),
]

_PRAZO_INTERIOR: list[tuple[frozenset[str], int]] = [
    (frozenset({"GO", "DF"}), 1),
    (frozenset({"SP", "BA", "MG", "ES", "RJ", "MS", "MT", "TO"}), 5),
    (frozenset({"PR"}), 7),
    (frozenset({"SC", "RS", "PA", "PI", "RN", "PE", "AL", "SE", "PB", "MA"}), 10),
    (frozenset({"CE", "RO"}), 11),
    (frozenset({"AC"}), 15),
    (frozenset({"AM", "AP", "RR"}), 25),
]


def normalizar(texto: str | None) -> str:
    """Maiúsculas, sem acento e sem espaço nas pontas.

    O nome da cidade chega do ERP em grafias diferentes ("Goiânia", "GOIANIA",
    " goiania"). Comparar sem normalizar faria a capital ser tratada como
    interior e o prazo dobrar.
    """
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto.strip().upper())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def e_capital(uf: str | None, cidade: str | None) -> bool:
    uf_normalizada = normalizar(uf)
    # O DF inteiro conta como capital — é como o sistema antigo faz, e na
    # prática Brasília e entorno têm a mesma rota.
    if uf_normalizada == "DF":
        return True
    return CAPITAIS.get(uf_normalizada) == normalizar(cidade)


def calcular_prazo_dias(uf: str | None, cidade: str | None, termolabil: bool) -> int | None:
    """Dias ÚTEIS de prazo. `None` quando a UF não está na tabela — que é
    informação legítima ("prazo não definido"), não erro."""
    uf_normalizada = normalizar(uf)
    if not uf_normalizada:
        return None

    if termolabil:
        tabela = _PRAZO_TERMOLABIL
    elif e_capital(uf, cidade):
        tabela = _PRAZO_CAPITAL
    else:
        tabela = _PRAZO_INTERIOR

    for ufs, dias in tabela:
        if uf_normalizada in ufs:
            return dias
    return None


def somar_dias_uteis(inicio: date, dias: int) -> date:
    """Avança `dias` dias úteis a partir de `inicio`, pulando fim de semana.

    Se `inicio` cai no fim de semana, o ponto de partida volta para a sexta —
    mesma regra do sistema antigo. Faz sentido: mapa de carga fechado no sábado
    não teve dia útil naquele dia, e contar a partir da segunda daria um dia a
    mais de prazo do que a transportadora combinou.
    """
    atual = inicio
    while atual.weekday() >= 5:  # 5 = sábado, 6 = domingo
        atual -= timedelta(days=1)

    restantes = dias
    while restantes > 0:
        atual += timedelta(days=1)
        if atual.weekday() < 5:
            restantes -= 1
    return atual


def calcular_data_prevista(data_mapa: date | None, prazo_dias: int | None) -> date | None:
    """A data limite de entrega. Nula sem mapa de carga (a contagem só começa
    quando a mercadoria sai) ou sem prazo definido para o destino."""
    if data_mapa is None or prazo_dias is None:
        return None
    return somar_dias_uteis(data_mapa, prazo_dias)


def calcular_status_prazo(
    data_mapa: date | None,
    data_prevista: date | None,
    entregue: bool,
    hoje: date,
) -> str:
    """Situação do prazo — calculada na hora, nunca gravada.

    Diferente de `prazo_dias` e `data_prevista_entrega`, que são congelados no
    momento em que o mapa chega, esta resposta depende de que dia é hoje: uma
    nota "no prazo" vira "em atraso" sozinha na virada da data. Guardar isso em
    coluna significaria uma rotina para reescrever a tabela toda todo dia.
    """
    if entregue:
        return "entregue"
    if data_mapa is None:
        return "sem_mapa"
    if data_prevista is None:
        return "prazo_nao_definido"
    return "em_atraso" if hoje > data_prevista else "no_prazo"
