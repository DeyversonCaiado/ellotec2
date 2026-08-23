from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth.dispositivo_model import Dispositivo
from app.core.auth.fingerprint import (
    calcular_fingerprint_hash,
    extrair_componentes,
    nome_amigavel_dispositivo,
)
from app.core.settings import obter_settings

settings = obter_settings()


class DeviceIdAusenteError(Exception):
    """Levantado quando o request não enviou o header X-Device-Id no login.
    O front PRECISA gerar um UUID estável (ex: crypto.randomUUID(), salvo
    em localStorage) no primeiro acesso e enviar em todo request daqui
    pra frente. Sem isso, não tem como diferenciar dispositivos."""


def identificar_ou_registrar_dispositivo(sessao: Session, request: Request, usuario_id: str) -> Dispositivo:
    """
    Chamado no momento do login. Resolve o dispositivo do usuário:
      - se já existe um Dispositivo com esse (usuario_id, device_id),
        atualiza o fingerprint e verifica anomalia;
      - se não existe, cria um novo Dispositivo "confiável" (primeiro
        acesso daquele device_id para aquele usuário).
    """
    componentes = extrair_componentes(request)

    if not componentes.device_id:
        raise DeviceIdAusenteError()

    fingerprint_hash = calcular_fingerprint_hash(componentes)

    dispositivo = (
        sessao.query(Dispositivo)
        .filter(
            Dispositivo.usuario_id == usuario_id,
            Dispositivo.device_id == componentes.device_id,
            Dispositivo.sync_deleted_at.is_(None),
        )
        .first()
    )

    if dispositivo is None:
        dispositivo = Dispositivo(
            usuario_id=usuario_id,
            device_id=componentes.device_id,
            fingerprint_hash=fingerprint_hash,
            user_agent=componentes.user_agent,
            ip_registro=componentes.ip_classe_c,
            nome_amigavel=nome_amigavel_dispositivo(componentes.user_agent),
            confiavel=True,
            contador_anomalias=0,
        )
        sessao.add(dispositivo)
        sessao.flush()
        return dispositivo

    if dispositivo.fingerprint_hash != fingerprint_hash:
        dispositivo.fingerprint_hash = fingerprint_hash
        dispositivo.user_agent = componentes.user_agent
        dispositivo.contador_anomalias += 1
        if dispositivo.contador_anomalias > settings.fingerprint_tolerancia_anomalias:
            dispositivo.confiavel = False

    sessao.flush()
    return dispositivo


def validar_dispositivo_da_requisicao(sessao: Session, request: Request, dispositivo_id: str) -> Dispositivo:
    """
    Chamado em TODA requisição autenticada (não só no login). Confirma que
    o device_id enviado no header bate com o dispositivo_id gravado no
    access token — impede que um access token roubado seja usado de outro
    dispositivo sem o device_id correspondente.
    """
    componentes = extrair_componentes(request)

    dispositivo = (
        sessao.query(Dispositivo)
        .filter(Dispositivo.id == dispositivo_id, Dispositivo.sync_deleted_at.is_(None))
        .first()
    )

    if dispositivo is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Dispositivo não reconhecido.")

    if not componentes.device_id or componentes.device_id != dispositivo.device_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dispositivo não corresponde ao token. Faça login novamente.",
        )

    if not dispositivo.confiavel:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dispositivo marcado como não confiável. Faça login novamente.",
        )

    return dispositivo
