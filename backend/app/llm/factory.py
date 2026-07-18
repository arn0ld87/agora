"""
P5.3: Profile-basierte Client-Factory.

Extracted verbatim from ``app/utils/llm_client.py`` as part of issue #582
(mechanical split — no behavior change).
"""

from typing import TYPE_CHECKING, Optional

from .client import LLMClient
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..contracts.llm_profile_contract import LlmProfile

logger = get_logger("agora.llm.factory")


def _normalize_base_url(url: Optional[str]) -> str:
    return (url or "").strip().rstrip("/").lower()


def _resolve_connection_secret(
    profile: "LlmProfile",
) -> tuple[Optional[str], Optional[str]]:
    """Resolve the profile's API key from the canonical provider-connection store.

    Bug #3: ``build_client_from_profile`` historically trusted the key persisted
    inside the legacy profile and never consulted the connection secret store.
    A stale profile key (e.g. an old ``…-dummy`` placeholder) then produced 401s
    even though a valid key was configured via the UI provider connection.

    Matches a connection by ``provider_kind`` first, then by ``base_url`` — the
    profile's ``provider`` may be the generic ``"custom"`` while the connection
    id is provider-specific (e.g. ``"minimax"``). Only enabled connections are
    considered. Returns ``(key, connection_id)`` or ``(None, None)`` when no
    matching connection secret exists. Never raises: on any failure the caller
    falls back to the profile's own key, preserving pure-profile setups.
    """
    try:
        from ..services.provider_connection_store import ProviderConnectionStore
        from ..services.llm_provider_secrets_store import (
            get_llm_provider_secrets_store,
        )

        connections = ProviderConnectionStore().list_connections()
        target = _normalize_base_url(profile.base_url)
        match = next(
            (
                c
                for c in connections
                if c.enabled
                and (
                    c.provider_kind == profile.provider
                    or (target and _normalize_base_url(c.base_url) == target)
                )
            ),
            None,
        )
        if match is None:
            return None, None
        key = get_llm_provider_secrets_store().get_plaintext(match.secret_ref or match.id)
        return (key, match.id) if key else (None, None)
    except Exception as exc:  # noqa: BLE001 — fall back to the profile's own key
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
    """P5.3: LLMClient aus persistiertem LLM-Profil bauen (überschreibt Config).

    Bug #3: Der API-Key wird bevorzugt aus dem kanonischen
    Provider-Connection-Store aufgelöst (gleiche Quelle wie der
    connection-basierte Routing-Pfad via ``resolve_route_api_key``); der im
    Profil gespeicherte Key ist nur noch Fallback für reine Profil-Setups ohne
    passende Connection.

    Ollama-Provider (localhost oder 'ollama' in base_url) dürfen api_key leer
    lassen — der Dummy-Wert 'ollama' wird gesetzt. Cloud-Provider ohne Key
    scheitern sofort mit einem ValueError, bevor ein HTTP-Request entsteht.
    """
    connection_key, connection_id = _resolve_connection_secret(profile)
    api_key = connection_key or profile.api_key
    api_key_source = "connection_store" if connection_key else "profile"

    base_url_lower = profile.base_url.lower()
    is_local = any(
        h in base_url_lower
        for h in ("localhost", "127.0.0.1", "host.docker.internal", "ollama")
    )
    if not api_key and not is_local:
        raise ValueError(
            f"LLM-Profil {profile.id!r}: api_key fehlt für Provider {profile.provider!r}"
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
