"""
Histórico de alterações feitas pelo sistema — inclusive as que gravam em outro
banco.

Mora em `core/` porque é transversal: qualquer domínio ou tela pode registrar
uma alteração aqui, e nenhum é dono dela. É o mesmo critério de `core/auth`.

O primeiro caso de uso é a correção de código de barras na bipagem, que escreve
em `fat_produtos` no Oracle do ERP. Por isso `tabela` é texto livre e não uma FK
para nada: a tabela alterada pode nem existir neste banco.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin

# As FKs abaixo referenciam tabelas de domínio pelo NOME, sem importar os models
# — é o que mantém `core` sem depender de `domains` (mesma técnica usada em
# expedicao_model.py). Quem recusa id inexistente é a foreign key do banco.


class Historico(Base, IdMixin, SyncMixin):
    __tablename__ = "historico"

    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    # Quem estava logado quando a alteração aconteceu. Não é necessariamente
    # quem autorizou — a autorização de gerente vai em `observacao`.
    usuario_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)

    # Texto livre: pode ser tabela deste banco ou do ERP (ex: 'fat_produtos').
    tabela: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    campo: Mapped[str] = mapped_column(String(100), nullable=False)
    # Nulos porque um campo pode estar vazio antes (ou depois) da alteração.
    valor_antigo: Mapped[str | None] = mapped_column(Text(), nullable=True)
    valor_novo: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # De onde a alteração partiu (ex: 'expedicao.bipagem'). Sem isso, meses
    # depois ninguém sabe qual fluxo gravou aquilo.
    tela: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    observacao: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # Quando a alteração aconteceu. Existe além de `sync_created_at` porque
    # aquele é campo de sincronização, e misturar auditoria com infraestrutura
    # de replicação sempre acaba mal.
    data_alteracao: Mapped[datetime] = mapped_column(DateTime(), nullable=False, index=True)
