"""
P5.3: Profile-basierte Client-Factory.

Extracted verbatim from ``app/utils/llm_client.py`` as part of issue #582
(mechanical split — no behavior change).
"""

from ipaddress import ip_address
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlsplit

from .client import LLMClient
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..contracts.llm_profile_contract import LlmProfile

logger = get_logger("agora.llm.factory")


def _is_local_base_url(url: str | None) -> bool:
    """Return whether the URL targets an explicitly local hostname."""
    if not url:
        return False
    try:
        hostname = urlsplit(url).hostname
    except ValueError:
        return False
    if hostname is None:
        return False

    hostname = hostname.rstrip(".").lower()
    if hostname in {"localhost", "host.docker.internal", "ollama"}:
        return True
    if hostname.endswith(".localhost"):
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def _resolve_connection_secret(
    profile: "LlmProfile",
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Resolve the enabled provider connection bound to a profile and its API key.

    Die aufgelöste Connection (``connection_id``, ``base_url``, ``auth_mode``) wird
    unabhängig vom Secret zurückgegeben, damit die autoritative Route auch für
    No-Auth-Connections erhalten bleibt. Der Hostname ist kein Authentifizierungs-
    modell — maßgeblich ist der explizite ``auth_mode`` der ProviderConnection.

    Parameters:
        profile (LlmProfile): Profile whose provider or base URL identifies the connection.

    Returns:
        tuple[Optional[str], Optional[str], Optional[str], Optional[str]]: The plaintext
        API key, connection ID, canonical connection URL and connection ``auth_mode``.
        Alle vier sind ``None``, wenn keine Connection aufgelöst wird oder der Lesepfad
        fehlschlägt. Bei einer aufgelösten api_key-Connection ohne hinterlegtes Secret
        ist der Key ``None``, ID/URL/auth_mode bleiben jedoch gesetzt.
    """
    try:
        from ..services.provider_connection_store import ProviderConnectionStore

        connections = [
            c for c in ProviderConnectionStore().list_connections() if c.enabled
        ]
    except Exception as exc:  # noqa: BLE001 — caller handles unavailable connection secrets
        logger.warning(
            "ProviderConnection-Lesen für Profil %r fehlgeschlagen: %s",
            getattr(profile, "id", "?"),
            exc,
        )
        return None, None, None, None

    from ..services.profile_connection_resolver import resolve_profile_connection

    resolved = resolve_profile_connection(profile, connections)
    if resolved is None:
        return None, None, None, None

    match = resolved.connection
    # Explizite No-Auth-Connection: autoritative Route ohne erwartetes Secret.
    if match.auth_mode == "none":
        return None, match.id, resolved.base_url, match.auth_mode

    try:
        from ..services.llm_provider_secrets_store import (
            get_llm_provider_secrets_store,
        )

        key = get_llm_provider_secrets_store().get_plaintext(match.secret_ref or match.id)
    except Exception as exc:  # noqa: BLE001 — caller handles unavailable connection secrets
        logger.warning(
            "Connection-Secret-Resolution für Profil %r fehlgeschlagen: %s",
            getattr(profile, "id", "?"),
            exc,
        )
        # Route (ID/URL/auth_mode) bleibt erhalten, damit der Aufrufer den
        # fehlenden Key als harten Fehler statt als Dummy-Key behandeln kann.
        return None, match.id, resolved.base_url, match.auth_mode
    return (key or None), match.id, resolved.base_url, match.auth_mode


def build_client_from_profile(
    profile: "LlmProfile",
    *,
    run_id: Optional[str] = None,
    timeout: float = 300.0,
) -> LLMClient:
    """
    Build an LLM client from a persisted profile and its provider connection settings.
    
    Parameters:
        profile (LlmProfile): Profile specifying the provider, endpoint, and model.
        run_id (Optional[str]): Optional identifier associated with the client run.
        timeout (float): Request timeout in seconds.
    
    Returns:
        LLMClient: Configured client using the resolved connection credentials and endpoint.
    
    Raises:
        ValueError: If no API key is available for a non-local endpoint.
    """
    connection_key, connection_id, connection_base_url, connection_auth_mode = (
        _resolve_connection_secret(profile)
    )
    api_key = connection_key
    api_key_source = "connection_store" if connection_key else "local_no_auth"

    resolved_via_connection = connection_id is not None
    connection_no_auth = connection_auth_mode == "none"
    effective_base_url = connection_base_url or profile.base_url

    # No-Auth ist nur erlaubt, wenn die aufgelöste Connection es explizit vorsieht
    # (auth_mode="none") ODER — ohne passende Connection — der Endpunkt lokal ist
    # (Legacy-Profile ohne ProviderConnection). Eine api_key-Connection ohne Secret
    # fällt NICHT auf den Dummy-Key zurück, auch nicht bei lokalem Hostnamen.
    no_auth_allowed = connection_no_auth or (
        not resolved_via_connection and _is_local_base_url(effective_base_url)
    )
    if not api_key and not no_auth_allowed:
        raise ValueError(
            f"LLM-Profil {profile.id!r}: api_key fehlt; kein Secret aus einer passenden "
            f"aktivierten ProviderConnection für Provider {profile.provider!r}"
        )
    return LLMClient(
        api_key=api_key or "ollama",
        base_url=effective_base_url,
        model=profile.model_name,
        timeout=timeout,
        run_id=run_id,
        route_provider_id=connection_id,
        api_key_source=api_key_source,
    )
