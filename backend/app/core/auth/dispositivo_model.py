from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.conexao import Base
from app.shared.sync_mixin import IdMixin, SyncMixin


class Dispositivo(Base, IdMixin, SyncMixin):
    """
    Um dispositivo é a combinação de:
      - device_id: UUID gerado UMA VEZ pelo cliente (front) no primeiro
        login, e enviado em todo request no header `X-Device-Id`. É a
        âncora principal — não muda mesmo se IP, navegador ou rede mudarem.
      - fingerprint_hash: hash server-side de componentes relativamente
        estáveis do cliente (ver core/auth/fingerprint.py), calculado a
        cada request e comparado com o salvo aqui. Existe pra detectar
        uso indevido de um device_id roubado/copiado — se o device_id
        bate mas o fingerprint mudou DRASTICAMENTE (não só a versão do
        navegador), é sinal de que não é o mesmo aparelho físico.

    Por que não usar só fingerprint (estilo FingerprintJS puro)? Porque
    fingerprint de componentes de navegador muda com frequência natural
    (atualização automática de browser, mudança de rede, modo
    anônimo, etc.) e isso geraria logout indevido toda hora. O device_id
    fixo, gerado e persistido pelo cliente, é a parte "imutável" pedida;
    o fingerprint entra só como verificação adicional de plausibilidade,
    não como identificador primário.
    """

    __tablename__ = "dispositivos"

    usuario_id: Mapped[str] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    ip_registro: Mapped[str] = mapped_column(String(45), nullable=False, default="")
    nome_amigavel: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    contador_anomalias: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confiavel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    sessoes: Mapped[list["Sessao"]] = relationship(back_populates="dispositivo", cascade="all, delete-orphan")
