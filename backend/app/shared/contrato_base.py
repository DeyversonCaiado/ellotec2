from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


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
