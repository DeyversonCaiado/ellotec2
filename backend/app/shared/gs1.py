"""
Leitura de código GS1 (QR Code / DataMatrix) vinda do coletor.

O leitor do coletor entrega uma string só, e ela pode ser duas coisas bem
diferentes:

- **Código de barras linear** (EAN-13, DUN-14, código interno): o conteúdo é o
  código, e não há nada a interpretar.
- **QR Code / DataMatrix GS1**: o conteúdo é uma sequência de *element strings*,
  cada uma identificada por um AI (Application Identifier). O código do produto
  fica no AI `01` — o GTIN, sempre com 14 posições — e vem acompanhado de lote
  (`10`), validade (`17`), série (`21`) e o que mais o fabricante imprimir.

Este módulo responde a uma pergunta só: **dada a leitura crua, quais códigos
devo procurar no cadastro?** Ele não consulta banco e não conhece produto —
é conversão de formato, por isso mora em `shared/` e não num domínio.

Referência do formato: GS1 General Specifications, seção de element strings e
GS1 Digital Link.
"""

import re

# Caractere separador de grupo (FNC1 na simbologia, 0x1D no dado decodificado).
# É ele que separa element strings de tamanho variável.
SEPARADOR_GRUPO = "\x1d"

# Identificadores de simbologia que alguns leitores prefixam ao dado quando
# configurados para "transmitir símbolo". Não fazem parte do conteúdo.
_PREFIXOS_SIMBOLOGIA = ("]d2", "]d1", "]Q3", "]Q1", "]e0", "]C1", "]J1")

# GS1 Digital Link: o GTIN vem no caminho da URL, depois de /01/.
# Ex: https://id.gs1.org/01/07891234567895/10/LOTE123
_DIGITAL_LINK = re.compile(r"/01/(\d{8,14})(?:[/?#]|$)")

_AI_GTIN = "01"
_TAMANHO_GTIN = 14


def _sem_prefixo_de_simbologia(leitura: str) -> str:
    for prefixo in _PREFIXOS_SIMBOLOGIA:
        if leitura.startswith(prefixo):
            return leitura[len(prefixo) :]
    return leitura


def extrair_gtin(leitura: str) -> str | None:
    """Devolve o GTIN de 14 posições do AI `01`, ou None se a leitura não for
    um payload GS1.

    Reconhece as três formas que aparecem na prática:

    1. Element strings com separador de grupo — `0107891234567895\\x1d10LOTE`.
    2. Element strings concatenadas sem separador, com o AI 01 na frente —
       `010789123456789517260101`. O AI `01` tem tamanho fixo (14), então os 14
       dígitos seguintes são o GTIN, venha o que vier depois.
    3. GS1 Digital Link — `https://id.gs1.org/01/07891234567895/10/LOTE`.

    O que **não** é payload GS1 devolve None: um EAN-13 ou um DUN-14 puro é o
    código em si, não tem AI para extrair. É por isso que a forma 2 exige mais
    de 16 caracteres — um DUN-14 que por acaso comece com "01" tem 14 dígitos e
    não passa nessa porta.
    """
    leitura = _sem_prefixo_de_simbologia(leitura.strip())
    if not leitura:
        return None

    digital_link = _DIGITAL_LINK.search(leitura)
    if digital_link:
        return digital_link.group(1).zfill(_TAMANHO_GTIN)

    for segmento in leitura.split(SEPARADOR_GRUPO):
        if not segmento.startswith(_AI_GTIN):
            continue
        candidato = segmento[len(_AI_GTIN) : len(_AI_GTIN) + _TAMANHO_GTIN]
        if len(candidato) < _TAMANHO_GTIN or not candidato.isdigit():
            continue
        # Sem separador e sem nada depois do GTIN, os 16 caracteres poderiam ser
        # um código linear qualquer que comece com "01". Exigir conteúdo além do
        # GTIN (ou o separador, que já quebrou o segmento) é o que distingue.
        if len(leitura) == len(_AI_GTIN) + _TAMANHO_GTIN and SEPARADOR_GRUPO not in leitura:
            continue
        return candidato

    return None


def codigos_para_buscar(leitura: str) -> list[str]:
    """Os códigos a procurar no cadastro, na ordem em que devem ser tentados.

    Leitura linear devolve ela mesma, e nada mais. Leitura GS1 devolve o GTIN de
    14 posições **e** a forma sem os zeros à esquerda: o cadastro guarda EAN-13
    como 13 dígitos, e o mesmo produto no QR Code aparece como esse EAN-13
    precedido de zero. São o mesmo número — recusar a leitura por causa de um
    zero seria o cadastro certo com a bipagem quebrada.
    """
    leitura = leitura.strip()
    if not leitura:
        return []

    gtin = extrair_gtin(leitura)
    if gtin is not None:
        return _com_forma_sem_zeros([gtin])

    # Caso ambíguo: exatamente "01" + 14 dígitos e mais nada. Pode ser um QR
    # Code que carrega só o GTIN, ou um código linear de 16 dígitos. Como não dá
    # para distinguir, a leitura crua vai na frente (é o que o cadastro pode ter
    # literalmente) e o GTIN entra logo atrás.
    if _parece_gtin_sozinho(leitura):
        return [leitura, *_com_forma_sem_zeros([leitura[len(_AI_GTIN) :]])]

    return [leitura]


def _com_forma_sem_zeros(gtins: list[str]) -> list[str]:
    """Cada GTIN seguido da sua forma sem zeros à esquerda. Só GTIN entra aqui:
    tirar zero de um código linear qualquer inventaria um número que ninguém
    cadastrou."""
    resultado = []
    for gtin in gtins:
        resultado.append(gtin)
        sem_zeros = gtin.lstrip("0")
        if sem_zeros and sem_zeros != gtin:
            resultado.append(sem_zeros)
    return list(dict.fromkeys(resultado))


def _parece_gtin_sozinho(leitura: str) -> bool:
    return (
        len(leitura) == len(_AI_GTIN) + _TAMANHO_GTIN
        and leitura.startswith(_AI_GTIN)
        and leitura.isdigit()
    )
