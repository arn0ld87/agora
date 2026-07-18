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


def _normalize_base_url(url: Optional[str]) -> str:
    """Normalize a base URL for consistent comparison."""
    return (url or "").strip().rstrip("/").lower()


def _is_local_base_url(url: str) -> bool:
    """Return whether the URL targets an explicitly local hostname."""
    hostname = urlsplit(url).hostname
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
) -> tuple[Optional[str], Optional[str]]:
    """
    Resolve the API key associated with a profile's enabled provider connection.
    
    Parameters:
        profile (LlmProfile): Profile whose provider or base URL identifies the connection.
    
    Returns:
        tuple[Optional[str], Optional[str]]: The plaintext API key and connection ID, or
        ``(None, None)`` when no matching secret is available or resolution fails.
    """
    try:
        from ..services.provider_connection_store import ProviderConnectionStore
        from ..services.llm_provider_secrets_store import (
            get_llm_provider_secrets_store,
        )
        from ..contracts.provider_types import PROVIDER_CUSTOM

        connections = [
            c for c in ProviderConnectionStore().list_connections() if c.enabled
        ]
        # 1. Exact provider_kind match always wins, independent of store order.
        match = next(
            (c for c in connections if c.provider_kind == profile.provider),
            None,
        )
        # 2. base_url fallback ONLY for the generic ``custom`` profile provider —
        #    a specific (non-custom) profile must never receive another
        #    provider's secret via a coincidental base_url match.
        if match is None and profile.provider == PROVIDER_CUSTOM:
            target = _normalize_base_url(profile.base_url)
            if target:
                match = next(
                    (c for c in connections if _normalize_base_url(c.base_url) == target),
                    None,
                )
        if match is None:
            return None, None
        key = get_llm_provider_secrets_store().get_plaintext(match.secret_ref or match.id)
        return (key, match.id) if key else (None, None)
    except Exception as exc:  # noqa: BLE001 — caller handles unavailable connection secrets
        logger.warning(
            "Connection-Secret-Resolution für Profil %r fehlgeschlagen: %s",
            getattr(profile, "id", "?"),
            exc,
        )
        return None, None


def build_client_from_profile(
    profile: "LlmProfile",
    *,
    run_id: Optional[str] = None,
    timeout: float = 300.0,
) -> LLMClient:
    """
    Build an LLM client from a persisted profile and its provider connection settings.
    
    Parameters:
        profile (LlmProfile): Profile containing the provider, credentials, endpoint, and model.
        run_id (Optional[str]): Optional identifier associated with the client run.
        timeout (float): Request timeout in seconds.
    
    Returns:
        LLMClient: Configured client using the matching connection-store key,
        or local no-auth credentials for local providers.
    
    Raises:
        ValueError: If no API key is available for a non-local provider.
    """
    connection_key, connection_id = _resolve_connection_secret(profile)
    api_key = connection_key
    api_key_source = "connection_store" if connection_key else "local_no_auth"

    is_local = _is_local_base_url(profile.base_url)
    if not api_key and not is_local:
        raise ValueError(
            f"LLM-Profil {profile.id!r}: api_key fehlt; kein Secret aus einer passenden "
            f"aktivierten ProviderConnection für Provider {profile.provider!r}"
        )
    return LLMClient(
        api_key=api_key or "ollama",
        base_url=profile.base_url,
        model=profile.model_name,
        timeout=timeout,
        run_id=run_id,
        route_provider_id=connection_id,
        api_key_source=api_key_source,
    )
