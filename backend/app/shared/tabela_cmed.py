"""
Leitura da tabela CMED (`cotacao_tabela_cmed`).

A CMED (Câmara de Regulação do Mercado de Medicamentos) publica a lista oficial
de medicamentos com preço regulado. A tabela vive neste banco mas **não é
nossa**: quem a popula é outro sistema, ela não tem model SQLAlchemy e não
aparece no metadata do Alembic (ver o `include_object` em `alembic/env.py`, que
justamente evita que o autogenerate tente apagá-la).

Por isso a conversa com ela mora em `shared/`, como a do ERP em
`shared/sistema_origem/`: é integração com sistema de terceiro, não domínio de
negócio nosso. Nenhum outro lugar do projeto monta SQL para `cotacao_tabela_cmed`.

Só leitura. Este módulo nunca escreve na tabela.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

# Bind de parâmetro, nunca interpolação: o registro chega do cadastro do produto,
# que por sua vez vem de importação do ERP. É entrada externa como qualquer outra.
#
# A CMED traz até três EANs por apresentação (`ean_1`, `ean_2`, `ean_3`) porque o
# mesmo medicamento circula com mais de um código de barras — troca de
# embalagem, apresentação hospitalar e de farmácia, reimpressão do fabricante.
# É exatamente esse conjunto que interessa à bipagem.
_SQL_POR_REGISTRO = text(
    """
    select ean_1, ean_2, ean_3, produto, apresentacao, laboratorio
      from cotacao_tabela_cmed
     where registro = :registro
    """
)


@dataclass(frozen=True)
class ApresentacaoCmed:
    """Uma linha da CMED, reduzida ao que interessa fora daqui."""

    eans: tuple[str, ...]
    produto: str
    apresentacao: str
    laboratorio: str


def _somente_digitos(valor: str | None) -> str:
    return "".join(caractere for caractere in (valor or "") if caractere.isdigit())


def normalizar_registro(registro: str | None) -> str:
    """O registro reduzido a dígitos.

    O número do registro é escrito de várias formas — `1.5690.0350.024-1`,
    `1569003500241`, com espaço, sem espaço. A CMED guarda só os dígitos, e o
    cadastro do produto guarda o que o ERP mandou. Comparar dígito a dígito é o
    que faz as duas formas se encontrarem."""
    return _somente_digitos(registro)


def buscar_por_registro(sessao_db: Session, registro: str) -> list[ApresentacaoCmed]:
    """As apresentações da CMED com esse registro, com os EANs já limpos.

    Devolve lista porque um registro pode ter mais de uma linha na tabela — é
    raro (hoje, um caso em 26 mil), mas quem consome precisa decidir o que fazer
    quando acontece, e esconder isso aqui seria decidir por ele.

    EAN vazio ou em branco não entra: a CMED preenche `ean_2`/`ean_3` com string
    vazia quando a apresentação só tem um código, e string vazia casaria com
    qualquer coisa depois.
    """
    registro = normalizar_registro(registro)
    if not registro:
        return []

    linhas = sessao_db.execute(_SQL_POR_REGISTRO, {"registro": registro}).mappings().all()
    return [
        ApresentacaoCmed(
            eans=tuple(
                dict.fromkeys(
                    ean
                    for ean in (
                        _somente_digitos(linha["ean_1"]),
                        _somente_digitos(linha["ean_2"]),
                        _somente_digitos(linha["ean_3"]),
                    )
                    if ean
                )
            ),
            produto=linha["produto"] or "",
            apresentacao=linha["apresentacao"] or "",
            laboratorio=linha["laboratorio"] or "",
        )
        for linha in linhas
    ]
