from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel


def _serializar_como_utc(valor: datetime | None) -> str | None:
    """Serializa um instante gravado em UTC com o fuso explícito no JSON.

    As colunas `DateTime()` do MySQL não guardam fuso: o valor volta do banco
    como um datetime NAIVE, e o Pydantic o serializa sem marcador nenhum
    ("2026-08-27T23:28:00"). O navegador, por regra do ECMAScript, lê uma string
    assim como HORA LOCAL — então um instante gravado às 23:28 UTC vira 23:28 de
    Brasília, três horas no futuro.

    A conta de duração de um processo FECHADO sobrevivia a isso por sorte: os
    dois instantes deslocavam junto e a diferença continuava certa. A de um
    processo EM ANDAMENTO não, porque ela compara o instante deslocado com o
    `Date.now()` do navegador, que é real — a diferença dava negativa e a tela
    não mostrava duração nenhuma.

    Usar isto exige que a coluna seja mesmo UTC. Vale para tudo que a expedição
    grava com `_agora()` (`datetime.now(timezone.utc)`) — NÃO vale para colunas
    preenchidas com `func.now()` do MySQL, que é hora local do servidor, nem
    para datas que chegam prontas da integração com o ERP.
    """
    if valor is None:
        return None
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.isoformat()


# Use em todo campo de contrato cujo instante é gravado em UTC pelo backend.
DataHoraUtc = Annotated[datetime, PlainSerializer(_serializar_como_utc, return_type=str)]


class ContratoBase(BaseModel):
    """
    Base comum de todos os contratos Pydantic da API. Configura duas coisas:

    1. alias_generator = to_camel: o JSON serializado usa camelCase
       (ex: razao_social → razaoSocial, criado_em → criadoEm), que é o
       padrão esperado pelo front Angular. O model interno continua com
       snake_case para bater com os atributos Python/SQLAlchemy — só a
       serialização JSON muda.

    2. populate_by_name = True: permite popular o model tanto pelo nome
       original (razao_social) quanto pelo alias (razaoSocial). Necessário
       para que o SQLAlchemy consiga montar schemas via from_orm usando os
       nomes snake_case dos atributos dos models.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
