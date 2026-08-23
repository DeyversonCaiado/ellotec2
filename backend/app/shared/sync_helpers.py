from datetime import datetime, timezone

from app.shared.sync_mixin import SyncMixin


def marcar_apagado(registro: SyncMixin) -> None:
    """
    Soft delete único e padronizado. Nenhum service de domínio deve fazer
    `sessao.delete(registro)` — sempre passar por aqui, senão o campo
    sync_deleted_at perde o sentido (ver SyncMixin para o porquê).
    """
    registro.sync_deleted_at = datetime.now(timezone.utc)
    incrementar_versao(registro)


def incrementar_versao(registro: SyncMixin) -> None:
    """Chamado em toda escrita (criar/editar/apagar) — sync_version é o
    contador otimista usado por um futuro processo de sincronização para
    detectar conflito de edição concorrente entre réplicas."""
    registro.sync_version = (registro.sync_version or 0) + 1
