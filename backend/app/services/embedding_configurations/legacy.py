"""Legacy-Adapter für ``Config.EMBEDDING_*`` (Onboarding Slice 4.2).

Vor Slice 4.2 war die Embedding-Konfiguration ausschließlich über
``Config.EMBEDDING_MODEL``, ``Config.EMBEDDING_BASE_URL``,
``Config.EMBEDDING_API_KEY`` und ``Config.VECTOR_DIM`` erreichbar. Diese
Werte leben in ``.env`` und sind statisch.

Slice 4.2 führt die kanonische ``EmbeddingConfiguration`` ein, die pro
Provider-Verbindung, Modell und verifizierter Dimension lebt. Damit alte
Installationen ohne Migration funktionieren, materialisiert dieser Adapter
aus den Legacy-Werten eine **virtuelle** Konfiguration — sie wird nicht
persistiert, sondern on-demand erzeugt, wenn die API nach der aktiven
Konfiguration gefragt wird und der Store leer ist.

Drei Dinge werden explizit NICHT gemacht:

* Kein stilles Anlegen einer ``ProviderConnection`` aus den Legacy-Werten
  — Verbindungen sind ein eigenständiger Lifecycle (Slice 3) und müssen
  explizit erzeugt werden, damit der Operator eine sichtbare Karte
  seiner Verbindungen hat.
* Kein Schreiben einer echten ``EmbeddingConfiguration`` in den Store.
  Solange kein Probe stattgefunden hat, ist die Konfiguration nicht
  verifiziert und gehört nicht in die Source of Truth.
* Kein Ueberschreiben der `Config.*`-Werte. Die Legacy-Quelle bleibt
  erhaltbar, bis der Operator explizit auf den kanonischen Pfad
  umstellt (das ist Slice 4.3-Folgescope).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Config
from app.contracts.ai_provider_contract import (
    LocalOllamaBaseUrl,
    ProviderConnection,
)
from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingProviderKind,
)


@dataclass(frozen=True)
class LegacyEmbeddingView:
    """Read-only-Sicht auf die aktuelle ``Config.EMBEDDING_*``-Konfiguration.

    Wird sowohl für die ``GET /api/embedding/configurations``-Antwort
    verwendet (wenn keine kanonische Konfiguration existiert) als auch
    für den Auto-Sync (``EmbeddingConfigurationService.sync_legacy``).
    """

    provider_connection_id: str
    provider_kind: EmbeddingProviderKind
    model_id: str
    dimensions: int
    base_url: str | None


def _classify_legacy_provider(base_url: str, has_api_key: bool) -> EmbeddingProviderKind:
    """Leitet den ``EmbeddingProviderKind`` aus den Legacy-Werten ab.

    Heuristik: Loopback-Host oder exakter ``ollama.com``-Host (kein
    Substring-Match, weil das ein klassischer SSRF-Vektor wäre: ein
    Operator koennte ``EMBEDDING_BASE_URL="https://evil.com/?ref=ollama.com"``
    setzen, der Probe wuerde dann mit dem API-Key an ``evil.com``
    gehen). Ollama-Cloud-Subdomains (``*.ollama.com``) zaehlen ebenfalls
    als Ollama Cloud. Alles andere mit Key → OpenAI; ohne Key → custom.

    Diese Heuristik ist dieselbe, die der bestehende ``EmbeddingService``
    fuer die Provider-Erkennung nutzt.
    """
    from urllib.parse import urlparse

    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    host = (parsed.hostname or "").lower()
    if host == "ollama.com" or host.endswith(".ollama.com"):
        return "ollama_cloud"
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "ollama"
    if has_api_key:
        return "openai"
    return "custom"


def build_legacy_view() -> LegacyEmbeddingView | None:
    """Liest die aktuelle Legacy-Konfiguration. Gibt ``None`` zurück, wenn
    keine sinnvolle Konfiguration vorliegt (z. B. leerer Base-URL).
    """
    model = (Config.EMBEDDING_MODEL or "").strip()
    base_url = (Config.EMBEDDING_BASE_URL or "").strip()
    if not model or not base_url:
        return None
    has_api_key = bool(Config.EMBEDDING_API_KEY)
    provider_kind = _classify_legacy_provider(base_url, has_api_key)
    return LegacyEmbeddingView(
        provider_connection_id="legacy-embedding",
        provider_kind=provider_kind,
        model_id=model,
        dimensions=Config.VECTOR_DIM,
        base_url=base_url,
    )


def legacy_view_to_configuration(
    view: LegacyEmbeddingView,
) -> EmbeddingConfiguration:
    """Synthetisiert eine kanonische (nicht-persistente) ``EmbeddingConfiguration``
    aus dem Legacy-View. Status ist ``proposed``, weil kein Probe
    stattgefunden hat — der Wert ist nur eine Lese-Brücke.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return EmbeddingConfiguration(
        id="legacy-embedding",
        provider_connection_id=view.provider_connection_id,
        provider_kind=view.provider_kind,
        model_id=view.model_id,
        dimensions=view.dimensions,
        scope="global",
        project_id=None,
        index_version=1,
        status="proposed",
        status_message="aus Config.EMBEDDING_* abgeleitet (nicht verifiziert)",
        created_at=now,
        updated_at=now,
        last_validated_at=None,
    )


def legacy_view_to_provider_connection(
    view: LegacyEmbeddingView,
) -> ProviderConnection:
    """Baut eine virtuelle ``ProviderConnection`` aus dem Legacy-View.

    Wird nur zur Probe verwendet, nicht persistiert. Der ``secret_ref``
    zeigt auf den Legacy-API-Key (sofern vorhanden), den der Secret-Store
    unter dem festen Namen ``legacy-embedding`` fuehrt — das ist
    bewusst NICHT der Name, den ein Operator-angelegter
    ``ProviderConnection`` bekommen wuerde, damit die Quelle klar bleibt.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    is_ollama_local = view.provider_kind == "ollama"
    base_url_value: str | None = view.base_url
    if is_ollama_local and base_url_value is not None:
        # Validiere Loopback-URL strukturell.
        base_url_value = LocalOllamaBaseUrl(base_url_value)
    return ProviderConnection(
        id=view.provider_connection_id,
        provider_kind=view.provider_kind,
        display_name=f"Legacy Embedding ({view.provider_kind})",
        transport="local" if is_ollama_local else "http",
        auth_mode="api_key" if Config.EMBEDDING_API_KEY else "none",
        base_url=base_url_value,
        enabled=True,
        status="unknown",
        status_message="Legacy-Config.EMBEDDING_*",
        secret_ref="legacy-embedding" if Config.EMBEDDING_API_KEY else None,
        capabilities={},
        created_at=now,
        updated_at=now,
        last_tested_at=None,
    )


__all__ = [
    "LegacyEmbeddingView",
    "build_legacy_view",
    "legacy_view_to_configuration",
    "legacy_view_to_provider_connection",
]
