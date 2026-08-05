"""Anbieter-spezifische Probe-Adapter für Embedding-Konfigurationen (Slice 4.2).

Jeder Adapter macht genau eine Sache: ein Test-Embedding über den bereits
konfigurierten ``ProviderConnection``-Endpunkt erzeugen und die tatsächliche
Vektor-Dimension zurückgeben. Mehr nicht.

Wir kapseln die HTTP-Aufrufe hinter einem ``EmbeddingProbeAdapter``-Protokoll,
damit der ``EmbeddingConfigurationService`` anbieter-agnostisch bleibt. Die
Anbieter-Schlüssel spiegeln die ``EmbeddingProviderKind``-Restriktion aus
``app.contracts.embedding_contract`` — Anthropic / CLI-Bridges tauchen hier
nicht auf, weil sie als Embedding-Quelle strukturell ausgeschlossen sind.

Status-Semantik (deckungsgleich mit ``ProviderProbeStatus`` in Slice 3):

* ``available`` — Test-Embedding hat die deklarierte Dimension geliefert.
* ``unavailable`` — Endpunkt nicht erreichbar oder HTTP 5xx.
* ``invalid_credentials`` — HTTP 401/403.
* ``degraded`` — Test-Embedding kam zurueck, aber die Dimension weicht ab
  oder ist unerwartet (z. B. Modell liefert 0-dimensionale Antworten).
* ``unsupported`` — Provider-Art ist hier explizit nicht implementiert.

Die Adapter sind bewusst klein gehalten. Komplexere Logik (z. B. Retry,
Backoff, Caching) gehört in den Service, nicht hier.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import requests

from app.contracts.ai_provider_contract import ProviderConnection
from app.contracts.embedding_contract import EmbeddingProviderKind
from app.llm.transport_security import (
    InsecureTransportError,
    ensure_credentialed_transport_security,
)

EmbeddingProbeStatus = Literal[
    "available",
    "unavailable",
    "invalid_credentials",
    "degraded",
    "unsupported",
]


@dataclass(frozen=True)
class EmbeddingProbeResult:
    """Normiertes Probe-Ergebnis.

    ``actual_dimensions`` ist die tatsaechlich vom Endpunkt gelieferte
    Vektorlaenge. Bei ``status != "available"`` ist der Wert ``None`` —
    ein fehlgeschlagener Probe-Request hat keine verlaessliche Dimension.
    """

    status: EmbeddingProbeStatus
    status_message: str | None
    actual_dimensions: int | None = None


class EmbeddingProbeAdapter(Protocol):
    def probe(
        self,
        connection: ProviderConnection,
        model_id: str,
        api_key: str | None,
    ) -> EmbeddingProbeResult: ...


# ----------------------------------------------------------------------
# Generische HTTP-Adapter (OpenAI-kompatibel)
# ----------------------------------------------------------------------


class _OpenAICompatibleAdapter:
    """Probe fuer OpenAI- und OpenAI-kompatible Endpunkte.

    Verwendet ``POST {base_url}/v1/embeddings`` (oder den bereits im
    ``base_url`` enthaltenen ``/v1``-Pfad) mit einem minimalen
    Probe-Text. Das ist exakt das gleiche Schema, das ``EmbeddingService``
    im Legacy-Pfad benutzt.
    """

    PROBE_TEXT = "agora-embedding-probe"

    def __init__(
        self,
        *,
        session: Callable[..., Any] = requests.Session,
    ) -> None:
        self._session_factory = session

    def probe(
        self,
        connection: ProviderConnection,
        model_id: str,
        api_key: str | None,
    ) -> EmbeddingProbeResult:
        if not connection.base_url:
            return EmbeddingProbeResult(
                status="unavailable", status_message="base_url fehlt"
            )
        base = connection.base_url.rstrip("/")
        url = f"{base}/embeddings" if base.endswith("/v1") else f"{base}/v1/embeddings"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            ensure_credentialed_transport_security(connection.base_url, api_key)
        except InsecureTransportError as exc:
            return EmbeddingProbeResult(status="unavailable", status_message=str(exc))

        try:
            with self._session_factory() as http:
                response = http.post(
                    url,
                    json={"model": model_id, "input": self.PROBE_TEXT},
                    headers=headers,
                    timeout=15,
                )
        except requests.exceptions.RequestException as exc:
            return EmbeddingProbeResult(
                status="unavailable",
                status_message=f"Verbindungsfehler: {type(exc).__name__}",
            )

        if response.status_code in (401, 403):
            return EmbeddingProbeResult(
                status="invalid_credentials",
                status_message=f"HTTP {response.status_code}",
            )
        if response.status_code >= 500:
            return EmbeddingProbeResult(
                status="unavailable",
                status_message=f"HTTP {response.status_code}",
            )
        if response.status_code >= 400:
            return EmbeddingProbeResult(
                status="unavailable",
                status_message=f"HTTP {response.status_code}: {response.text[:200]}",
            )

        try:
            data = response.json()
            items = data.get("data", [])
            if not items:
                return EmbeddingProbeResult(
                    status="degraded",
                    status_message="Antwort enthaelt keine Embeddings",
                )
            vector = items[0].get("embedding")
            if not isinstance(vector, list) or not vector:
                return EmbeddingProbeResult(
                    status="degraded",
                    status_message="Embedding-Vektor fehlt oder ist leer",
                )
            return EmbeddingProbeResult(
                status="available",
                status_message=None,
                actual_dimensions=len(vector),
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            return EmbeddingProbeResult(
                status="degraded",
                status_message=f"Antwort nicht parsebar: {type(exc).__name__}",
            )


# ----------------------------------------------------------------------
# Gemini-spezifischer Adapter
# ----------------------------------------------------------------------


class _GeminiAdapter:
    """Probe fuer Google Gemini Embeddings.

    Verwendet ``POST {base_url}/v1beta/models/{model_id}:embedContent`` mit
    ``x-goog-api-key`` Header. Quelle: https://ai.google.dev/gemini-api/docs/embeddings
    """

    PROBE_TEXT = {"content": {"parts": [{"text": "agora-embedding-probe"}]}}

    def __init__(
        self,
        *,
        session: Callable[..., Any] = requests.Session,
    ) -> None:
        self._session_factory = session

    def probe(
        self,
        connection: ProviderConnection,
        model_id: str,
        api_key: str | None,
    ) -> EmbeddingProbeResult:
        if not connection.base_url:
            return EmbeddingProbeResult(
                status="unavailable", status_message="base_url fehlt"
            )
        if not api_key:
            return EmbeddingProbeResult(
                status="invalid_credentials",
                status_message="Gemini Embeddings verlangt API-Key",
            )
        base = connection.base_url.rstrip("/")
        url = f"{base}/v1beta/models/{model_id}:embedContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }

        try:
            with self._session_factory() as http:
                response = http.post(
                    url, json=self.PROBE_TEXT, headers=headers, timeout=15
                )
        except requests.exceptions.RequestException as exc:
            return EmbeddingProbeResult(
                status="unavailable",
                status_message=f"Verbindungsfehler: {type(exc).__name__}",
            )

        if response.status_code in (401, 403):
            return EmbeddingProbeResult(
                status="invalid_credentials",
                status_message=f"HTTP {response.status_code}",
            )
        if response.status_code >= 500:
            return EmbeddingProbeResult(
                status="unavailable",
                status_message=f"HTTP {response.status_code}",
            )
        if response.status_code >= 400:
            return EmbeddingProbeResult(
                status="unavailable",
                status_message=f"HTTP {response.status_code}: {response.text[:200]}",
            )

        try:
            data = response.json()
            values = data.get("embedding", {}).get("values")
            if not isinstance(values, list) or not values:
                return EmbeddingProbeResult(
                    status="degraded",
                    status_message="Antwort enthaelt keine Embedding-Werte",
                )
            return EmbeddingProbeResult(
                status="available",
                status_message=None,
                actual_dimensions=len(values),
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            return EmbeddingProbeResult(
                status="degraded",
                status_message=f"Antwort nicht parsebar: {type(exc).__name__}",
            )


# ----------------------------------------------------------------------
# Ollama-spezifischer Adapter (lokal und Cloud)
# ----------------------------------------------------------------------


class _OllamaAdapter:
    """Probe fuer Ollama-Endpoints (``POST /api/embed``).

    Verwendet denselben Endpunkt wie der bestehende ``EmbeddingService``
    im Legacy-Pfad. Funktioniert fuer lokales Ollama (Loopback) und
    Ollama Cloud (Bearer-Auth) identisch.
    """

    PROBE_TEXT = "agora-embedding-probe"

    def __init__(
        self,
        *,
        session: Callable[..., Any] = requests.Session,
    ) -> None:
        self._session_factory = session

    def probe(
        self,
        connection: ProviderConnection,
        model_id: str,
        api_key: str | None,
    ) -> EmbeddingProbeResult:
        if not connection.base_url:
            return EmbeddingProbeResult(
                status="unavailable", status_message="base_url fehlt"
            )
        base = connection.base_url.rstrip("/")
        url = f"{base}/api/embed"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            ensure_credentialed_transport_security(connection.base_url, api_key)
        except InsecureTransportError as exc:
            return EmbeddingProbeResult(status="unavailable", status_message=str(exc))

        try:
            with self._session_factory() as http:
                response = http.post(
                    url,
                    json={"model": model_id, "input": self.PROBE_TEXT},
                    headers=headers,
                    timeout=15,
                )
        except requests.exceptions.RequestException as exc:
            return EmbeddingProbeResult(
                status="unavailable",
                status_message=f"Verbindungsfehler: {type(exc).__name__}",
            )

        if response.status_code in (401, 403):
            return EmbeddingProbeResult(
                status="invalid_credentials",
                status_message=f"HTTP {response.status_code}",
            )
        if response.status_code >= 500:
            return EmbeddingProbeResult(
                status="unavailable",
                status_message=f"HTTP {response.status_code}",
            )
        if response.status_code >= 400:
            return EmbeddingProbeResult(
                status="unavailable",
                status_message=f"HTTP {response.status_code}: {response.text[:200]}",
            )

        try:
            data = response.json()
            embeddings = data.get("embeddings")
            if not embeddings or not isinstance(embeddings, list):
                return EmbeddingProbeResult(
                    status="degraded",
                    status_message="Antwort enthaelt keine embeddings",
                )
            vector = embeddings[0]
            if not isinstance(vector, list) or not vector:
                return EmbeddingProbeResult(
                    status="degraded",
                    status_message="Embedding-Vektor fehlt oder ist leer",
                )
            return EmbeddingProbeResult(
                status="available",
                status_message=None,
                actual_dimensions=len(vector),
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            return EmbeddingProbeResult(
                status="degraded",
                status_message=f"Antwort nicht parsebar: {type(exc).__name__}",
            )


# ----------------------------------------------------------------------
# Adapter-Registry
# ----------------------------------------------------------------------

_ADAPTERS: dict[EmbeddingProviderKind, EmbeddingProbeAdapter] = {
    "ollama": _OllamaAdapter(),
    "ollama_cloud": _OllamaAdapter(),
    "openai": _OpenAICompatibleAdapter(),
    "openai_compatible": _OpenAICompatibleAdapter(),
    "custom": _OpenAICompatibleAdapter(),
    "google": _GeminiAdapter(),
}


def adapter_for_provider(kind: EmbeddingProviderKind) -> EmbeddingProbeAdapter:
    """Liefert den passenden Adapter für ``kind``.

    Wirft ``KeyError``, wenn der Provider nicht in der Registry ist — das
    kann nicht passieren, weil ``EmbeddingProviderKind`` und der
    ``_ADAPTERS``-Dict dieselbe Literal-Menge teilen und mypy diesen
    Aufruf gegen ``_ADAPTERS.get(kind)`` strenger pruefen wuerde. Ein
    Fail-Fast ist trotzdem die richtige Verteidigungslinie.
    """
    adapter = _ADAPTERS.get(kind)
    if adapter is None:
        raise KeyError(f"Kein Embedding-Probe-Adapter fuer Provider: {kind}")
    return adapter
