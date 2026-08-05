"""Transport-Security-Gate fuer credential-behaftete LLM-Endpoints (Issue #1103, CWE-319).

``LLMClient`` und die Discovery-Adapter senden ``Authorization: Bearer <api_key>``
an eine konfigurierbare ``base_url``. Ist die ``http://`` statt ``https://`` und
zeigt auf einen oeffentlichen Host, geht der Key im Klartext ueber die Leitung.

Diese Policy ist fail-closed: ``http`` ist nur erlaubt, wenn der Host nachweislich
lokal oder privat ist (loopback, RFC1918, CGNAT/Tailscale, Link-Local, Docker-
Compose-Servicenamen). Alles andere loest ``InsecureTransportError`` aus, es sei
denn die dokumentierte Ausnahme ``AGORA_LLM_ALLOW_INSECURE_HTTP`` ist gesetzt.
"""
from __future__ import annotations

import ipaddress
import os
from typing import Optional
from urllib.parse import urlparse

from ..utils.logger import get_logger

logger = get_logger("agora.llm_transport_security")

_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")

_TRUTHY = {"1", "true", "yes", "on"}

# Docker Desktop/Compose stellt diese festen Hostnamen bereit, um vom
# Container aus die Docker-Host-Gateway-Adresse zu erreichen (z. B. lokales
# Ollama auf dem Host, waehrend das Backend containerisiert laeuft). Beide
# loesen ausschliesslich innerhalb des lokalen Docker-Netzwerks auf und sind
# nie oeffentlich routbar — fachlich dieselbe Vertrauensstufe wie ein
# Single-Label-Compose-Servicename, nur mit Punkten im Namen.
_DOCKER_HOST_GATEWAY_NAMES = {"host.docker.internal", "gateway.docker.internal"}


class InsecureTransportError(ValueError):
    """Ein credential-behafteter LLM-Request ginge unverschluesselt ueber http://."""


def _env_flag_allow_insecure_http() -> bool:
    return os.environ.get("AGORA_LLM_ALLOW_INSECURE_HTTP", "").strip().lower() in _TRUTHY


def _sanitize_for_log(base_url: str) -> str:
    """Strippt userinfo/query/fragment fuer Log- und Fehlermeldungen.

    Eigenstaendige, minimale Implementierung statt eines Imports aus
    ``SecretResolver`` — vermeidet einen Zyklus zwischen ``app.llm`` und
    ``app.services`` und bleibt robust gegenueber unparsebaren URLs.
    """
    try:
        parsed = urlparse(base_url)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        scheme = parsed.scheme or ""
        return f"{scheme}://{host}{port}{parsed.path}" if scheme else host
    except Exception:  # noqa: BLE001 — Sanitizing darf nie selbst crashen
        return "<unparsable-url>"


def _is_private_host(host: str) -> bool:
    """True, wenn *host* lokal/privat ist und ein unverschluesselter http-Transport
    des Credentials tolerierbar ist."""
    if not host:
        return False
    normalized = host.strip().lower().rstrip(".")
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    if normalized in _DOCKER_HOST_GATEWAY_NAMES:
        return True
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        # Kein IP-Literal. Docker-Compose-Servicenamen (z. B. "ollama") sind
        # Single-Label-Hostnamen ohne Punkt — im internen Compose-Netz vertrauenswürdig.
        return "." not in normalized
    if ip.is_loopback or ip.is_link_local:
        return True
    if isinstance(ip, ipaddress.IPv4Address):
        if ip.is_private:
            return True
        return ip in _CGNAT_NETWORK
    # IPv6: ULA (fc00::/7) faellt unter is_private in modernen Python-Versionen;
    # is_loopback/is_link_local sind oben bereits abgedeckt.
    return ip.is_private


def ensure_credentialed_transport_security(
    base_url: Optional[str], api_key: Optional[str]
) -> None:
    """Verweigert unverschluesseltes http:// fuer credential-behaftete Requests
    an oeffentliche Hosts (CWE-319).

    Kein ``api_key`` oder keine ``base_url`` → nichts zu schuetzen, sofortiger
    Return. ``https`` sowie Schemes ausser ``http``/``https`` sind out of scope.
    ``http`` ist nur fuer lokale/private Hosts erlaubt (siehe ``_is_private_host``).
    Eine unparsebare URL wird wie ein unbekannt-oeffentlicher Host behandelt
    (fail-closed). Die Policy laesst sich per ``AGORA_LLM_ALLOW_INSECURE_HTTP``
    explizit ausschalten (dokumentierte Ausnahme, dann nur ``logger.warning``).
    """
    if not api_key or not base_url:
        return

    try:
        parsed = urlparse(base_url)
    except Exception:  # noqa: BLE001 — unparsebare URL faellt unten durch
        parsed = None

    scheme = (parsed.scheme or "").lower() if parsed is not None else ""
    if scheme and scheme != "http":
        return

    host = parsed.hostname if parsed is not None else None
    if scheme == "http" and host and _is_private_host(host):
        return

    sanitized = _sanitize_for_log(base_url)
    if _env_flag_allow_insecure_http():
        logger.warning(
            "AGORA_LLM_ALLOW_INSECURE_HTTP aktiv: erlaube credential-behafteten "
            "http-Transport zu oeffentlichem Host base_url=%s",
            sanitized,
        )
        return

    raise InsecureTransportError(
        f"Unverschluesselter http-Transport zu einem oeffentlichen Host mit "
        f"API-Key ist nicht erlaubt (base_url={sanitized}). Verwende https:// "
        f"oder setze AGORA_LLM_ALLOW_INSECURE_HTTP fuer eine dokumentierte "
        f"Ausnahme."
    )
