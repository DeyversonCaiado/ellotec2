from sqlalchemy import Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin


class ExpedicaoConfiguracao(Base, IdMixin, SyncMixin):
    """Os parâmetros da expedição — uma linha só, para o galpão inteiro.

    **Por que uma linha e não uma tabela chave/valor.** Chave/valor guarda tudo
    como texto e joga a tipagem para o código: quem lê precisa saber que
    `"true"` é booleano e que a chave se chama exatamente assim. Uma coluna por
    parâmetro dá tipo real no banco, no model e no contrato, e o compilador
    cobra quem escrever errado. Parâmetro novo é coluna nova com migração —
    que é justamente o momento em que se decide o valor padrão do que já existe.

    **Por que não é por empresa.** As regras que estes parâmetros ligam e
    desligam são do processo de separação/conferência, que hoje é um só. No dia
    em que uma filial precisar de regra diferente da outra, entra `empresa_id`
    aqui e a leitura passa a receber a empresa — não é o caso hoje, e antecipar
    isso seria abstrair sem dor.
    """

    __tablename__ = "expedicao_configuracoes"

    # As duas regras da trava de endereçamento, cada uma com o seu parâmetro.
    # São separadas porque respondem a problemas diferentes do galpão: a
    # primeira é falta de mercadoria endereçada, a segunda é saldo quebrado numa
    # prateleira. Um galpão pode conviver com uma e não com a outra, e juntá-las
    # num interruptor só obrigaria a desligar as duas para resolver metade.
    #
    # As duas nascem desligadas: é assim que a expedição sempre funcionou.

    # Soma dos endereços do lote menor que a quantidade vendida.
    permite_conferir_com_divergencia: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Endereço cujo saldo não fecha em múltiplo da embalagem de venda.
    permite_conferir_fora_do_multiplo_de_venda: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
