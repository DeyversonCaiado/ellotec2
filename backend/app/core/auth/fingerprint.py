import hashlib
from dataclasses import dataclass

from fastapi import Request

HEADER_DEVICE_ID = "X-Device-Id"


@dataclass(frozen=True)
class ComponentesFingerprint:
    """Componentes brutos extraídos do request, antes de virar hash."""

    device_id: str | None
    user_agent: str
    accept_language: str
    ip_classe_c: str


def _normalizar_ip(ip: str) -> str:
    """
    Usa só a 'classe C' do IPv4 (3 primeiros octetos) em vez do IP
    completo. O motivo: o último octeto muda toda hora em redes
    domésticas/móveis com IP dinâmico, e isso sozinho derrubaria sessões
    válidas sem necessidade. Mantendo só os 3 primeiros octetos, ainda
    capturamos "saiu da rede/região" sem reagir a flutuações normais de
    DHCP. Para IPv6, faz o equivalente truncando o endereço.
    """
    if ":" in ip:
        partes = ip.split(":")
        return ":".join(partes[:4])
    partes = ip.split(".")
    if len(partes) == 4:
        return ".".join(partes[:3])
    return ip


def extrair_componentes(request: Request) -> ComponentesFingerprint:
    device_id = request.headers.get(HEADER_DEVICE_ID)
    user_agent = request.headers.get("user-agent", "")
    accept_language = request.headers.get("accept-language", "")
    ip_origem = request.client.host if request.client else ""

    return ComponentesFingerprint(
        device_id=device_id,
        user_agent=user_agent,
        accept_language=accept_language,
        ip_classe_c=_normalizar_ip(ip_origem),
    )


def calcular_fingerprint_hash(componentes: ComponentesFingerprint) -> str:
    """
    Hash SHA-256 dos componentes server-side. Não inclui o device_id no
    hash de propósito — o device_id já é comparado separadamente como
    chave de busca do Dispositivo (ver core/auth/dispositivo_service.py).
    Esse hash aqui é só pra detectar se o resto do contexto (navegador,
    idioma, faixa de rede) é plausivelmente o mesmo aparelho.
    """
    bruto = f"{componentes.user_agent}|{componentes.accept_language}|{componentes.ip_classe_c}"
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def nome_amigavel_dispositivo(user_agent: str) -> str:
    """Heurística simples pra dar um nome legível ao dispositivo (mostrado
    numa futura tela de 'meus dispositivos'). Não precisa ser perfeita,
    só legível o bastante pro usuário reconhecer."""
    ua = user_agent.lower()

    if "edg/" in ua:
        navegador = "Edge"
    elif "chrome/" in ua and "chromium" not in ua:
        navegador = "Chrome"
    elif "firefox/" in ua:
        navegador = "Firefox"
    elif "safari/" in ua and "chrome" not in ua:
        navegador = "Safari"
    else:
        navegador = "Navegador"

    if "windows" in ua:
        sistema = "Windows"
    elif "mac os" in ua or "macintosh" in ua:
        sistema = "macOS"
    elif "android" in ua:
        sistema = "Android"
    elif "iphone" in ua or "ipad" in ua:
        sistema = "iOS"
    elif "linux" in ua:
        sistema = "Linux"
    else:
        sistema = "dispositivo desconhecido"

    return f"{navegador} em {sistema}"
