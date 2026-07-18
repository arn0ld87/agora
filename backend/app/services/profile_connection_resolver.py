"""Secret-freie Bindung von Legacy-LLM-Profilen an ProviderConnections."""

from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple
from urllib.parse import urlsplit, urlunsplit

from ..contracts.ai_provider_contract import ProviderConnection
from ..contracts.llm_profile_contract import LlmProfile
from ..contracts.provider_types import PROVIDER_CUSTOM
from .llm_provider_registry import LlmProviderRegistry


class ResolvedProfileConnection(NamedTuple):
    """ProviderConnection plus ihr kanonischer HTTP-Endpunkt."""

    connection: ProviderConnection
    base_url: str


_LEGACY_PROVIDER_KIND_ALIASES: dict[str, frozenset[str]] = {
    "cloud": frozenset({"cloud", "ollama_cloud"}),
    "unknown": frozenset({"unknown", "openai_compatible"}),
}


def normalize_endpoint_url(url: str | None) -> str:
    """Normalisiere einen Endpunkt fuer einen stabilen Identitaetsvergleich."""

    raw = (url or "").strip().rstrip("/")
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return raw
    if not parsed.scheme or hostname is None:
        return raw

    normalized_host = hostname.rstrip(".").lower()
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    default_port = (parsed.scheme.lower(), port) in {("http", 80), ("https", 443)}
    netloc = normalized_host if port is None or default_port else f"{normalized_host}:{port}"
    return urlunsplit(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path.rstrip("/"),
            parsed.query,
            parsed.fragment,
        )
    )


def canonical_connection_base_url(connection: ProviderConnection) -> str | None:
    """Liefere den Connection-Endpunkt oder den Registry-Default."""

    if connection.base_url:
        return str(connection.base_url)
    definition = LlmProviderRegistry.connection_definition(connection.provider_kind)
    return definition.default_base_url if definition is not None else None


def resolve_profile_connection(
    profile: LlmProfile,
    connections: Iterable[ProviderConnection],
) -> ResolvedProfileConnection | None:
    """Binde ein Legacy-Profil nur an Kind- und Endpunkt-kompatible Connections.

    ``custom`` bleibt der einzige Legacy-Provider, der bei exakt gleichem
    Endpunkt ueber Provider-Kinds hinweg gebunden werden darf.
    """

    enabled = [connection for connection in connections if connection.enabled]
    profile_endpoint = normalize_endpoint_url(profile.base_url)

    if profile.provider == PROVIDER_CUSTOM:
        candidates = enabled
    else:
        compatible_kinds = _LEGACY_PROVIDER_KIND_ALIASES.get(
            profile.provider,
            frozenset({profile.provider}),
        )
        candidates = [
            connection
            for connection in enabled
            if connection.provider_kind in compatible_kinds
        ]

    for connection in candidates:
        base_url = canonical_connection_base_url(connection)
        if base_url and normalize_endpoint_url(base_url) == profile_endpoint:
            return ResolvedProfileConnection(connection, base_url)

    if candidates and profile.provider != PROVIDER_CUSTOM:
        raise ValueError(
            f"LLM-Profil {profile.id!r}: Profil-Endpunkt {profile.base_url!r} stimmt "
            f"mit keiner aktivierten ProviderConnection fuer Provider "
            f"{profile.provider!r} ueberein"
        )
    return None


__all__ = [
    "ResolvedProfileConnection",
    "canonical_connection_base_url",
    "normalize_endpoint_url",
    "resolve_profile_connection",
]
