import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column


def gerar_uuid() -> str:
    return str(uuid.uuid4())


class SyncMixin:
    """
    Mixin aplicado em TODA tabela do sistema. Esses 5 campos existem porque
    este banco vai, no futuro, sincronizar com outras instâncias/réplicas
    (ex: filiais, app offline-first, etc.) — sem eles, não tem como saber
    o que mudou, quando, e resolver conflito de escrita concorrente.

    - sync_created_at: quando o registro nasceu (imutável após o insert).
    - sync_updated_at: quando o registro mudou pela última vez (qualquer
      campo, incluindo soft delete). Atualizado em toda escrita.
    - sync_deleted_at: soft delete. NULL = registro vivo. Sistema
      distribuído não pode usar DELETE físico — quem sincronizar depois
      precisa saber que aquele registro foi removido, não só "sumir" ele
      do banco local. Todo service de domínio implementa apagar() como
      UPDATE setando esse campo, nunca como DELETE de verdade.
    - sync_version: contador otimista de versão. Incrementado a cada
      escrita. Usado para detectar conflito de edição concorrente entre
      réplicas (resolução de conflito = comparar versões, não timestamps,
      porque relógios de máquinas diferentes podem divergir).
    - sync_synced_at: quando esse registro foi confirmado como replicado
      com sucesso para o(s) outro(s) nó(s). NULL = nunca sincronizado
      (registro "sujo", pendente de propagação). É o campo que um futuro
      worker de sincronização usa pra saber o que ainda precisa enviar.

    Importante: sync_synced_at é gerenciado pelo processo de sincronização
    (que ainda não existe nesta fase do projeto), não pelos services de
    domínio. Os services de domínio só tocam em sync_updated_at,
    sync_deleted_at e sync_version.
    """

    sync_created_at: Mapped[datetime] = mapped_column(DateTime(), default=func.now(), nullable=False)
    sync_updated_at: Mapped[datetime] = mapped_column(
        DateTime(), default=func.now(), onupdate=func.now(), nullable=False
    )
    sync_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)
    sync_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sync_synced_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, default=None)


class IdMixin:
    """
    PK em UUID (string), não auto-increment. Obrigatório em sistema
    distribuído: se duas réplicas offline criam registros com
    auto-increment, os IDs colidem na hora de sincronizar. UUID gerado
    no momento da criação evita esse problema inteiramente, sem precisar
    de coordenação central.
    """

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gerar_uuid)
