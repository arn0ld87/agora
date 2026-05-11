"""Live-Discovery verfügbarer Modelle pro Provider.

Keine hardcodierten Modell-Listen. API-Keys werden ausschließlich aus
``os.environ`` gelesen und nie geloggt oder in Exceptions weitergereicht.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import httpx

from .errors import (
    MissingCredentialError,
    ProviderHTTPError,
    UnknownProviderError,
)

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# OpenAI-Modelle, die für Chat-Completions relevant sind. Wir matchen
# Familien (gpt-*, o1*, o3*, o4*) statt einer festen Liste, damit neue
# Modelle ohne Code-Change auftauchen.
_OPENAI_MODEL_RE = re.compile(r"^(gpt-|o1|o3|o4)", re.IGNORECASE)

# Reasoning- bzw. Audio-/Bild-/Embedding-Varianten, die nicht zur Chat-Auswahl
# gehören. Bewusst konservativ — nur klare Negative.
_OPENAI_BLOCK_SUBSTR: tuple[str, ...] = (
    "embedding",
    "tts",
    "whisper",
    "audio",
    "moderation",
    "image",
    "dall-e",
    "realtime",
)


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Provider-agnostisches Modell-Tupel."""

    provider: str
    id: str
    label: str | None = None
    context_window: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def display(self) -> str:
        return self.label or self.id


async def discover_models(
    provider: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: httpx.Timeout | float | None = None,
) -> list[ModelInfo]:
    """Liefert die aktuell vom Provider angebotenen Modelle.

    Args:
        provider: ``"openai"`` | ``"gemini"`` | ``"ollama"``.
        client: Optionaler vorhandener ``httpx.AsyncClient``.
            Sinnvoll für Tests oder zum Pooling.
        timeout: Override für den Default-Timeout.

    Raises:
        MissingCredentialError: Pflicht-ENV fehlt (openai/gemini).
        ProviderHTTPError: Upstream antwortet mit Fehlerstatus.
        UnknownProviderError: Unbekannter Provider-Slug.
    """

    slug = provider.strip().lower()
    if slug == "openai":
        fetcher = _fetch_openai
    elif slug == "gemini":
        fetcher = _fetch_gemini
    elif slug == "ollama":
        fetcher = _fetch_ollama
    else:
        raise UnknownProviderError(provider)

    own_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout or DEFAULT_TIMEOUT)
    try:
        return await fetcher(http)
    finally:
        if own_client:
            await http.aclose()


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


async def _fetch_openai(http: httpx.AsyncClient) -> list[ModelInfo]:
    api_key = _require_env("OPENAI_API_KEY")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")
    url = f"{base}/v1/models"
    resp = await http.get(url, headers={"Authorization": f"Bearer {api_key}"})
    _raise_for_status("openai", resp)
    payload = resp.json()
    raw = payload.get("data") or []
    return sorted(
        (model for model in (_map_openai(item) for item in raw) if model is not None),
        key=lambda m: m.id,
    )


def _map_openai(item: dict[str, Any]) -> ModelInfo | None:
    model_id = str(item.get("id") or "").strip()
    if not model_id:
        return None
    if not _OPENAI_MODEL_RE.match(model_id):
        return None
    lower = model_id.lower()
    if any(sub in lower for sub in _OPENAI_BLOCK_SUBSTR):
        return None
    return ModelInfo(
        provider="openai",
        id=model_id,
        extra={"owned_by": item.get("owned_by")} if item.get("owned_by") else {},
    )


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


async def _fetch_gemini(http: httpx.AsyncClient) -> list[ModelInfo]:
    api_key = _require_env("GEMINI_API_KEY")
    base = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
    url = f"{base}/v1beta/models"
    resp = await http.get(url, params={"key": api_key})
    _raise_for_status("gemini", resp, suppress_key=api_key)
    payload = resp.json()
    raw = payload.get("models") or []
    out: list[ModelInfo] = []
    for item in raw:
        info = _map_gemini(item)
        if info is not None:
            out.append(info)
    out.sort(key=lambda m: m.id)
    return out


def _map_gemini(item: dict[str, Any]) -> ModelInfo | None:
    methods = item.get("supportedGenerationMethods") or []
    if "generateContent" not in methods:
        return None
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    # Format: "models/gemini-1.5-pro" → strip prefix für stabilen ID-Slug.
    model_id = name.split("/", 1)[1] if name.startswith("models/") else name
    return ModelInfo(
        provider="gemini",
        id=model_id,
        label=item.get("displayName") or None,
        context_window=item.get("inputTokenLimit"),
        extra={
            "output_token_limit": item.get("outputTokenLimit"),
            "version": item.get("version"),
        },
    )


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


async def _fetch_ollama(http: httpx.AsyncClient) -> list[ModelInfo]:
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    url = f"{base}/api/tags"
    try:
        resp = await http.get(url)
    except httpx.HTTPError as exc:
        # Verbindung verweigert ist hier der Normalfall (Server aus).
        raise ProviderHTTPError(
            "ollama",
            0,
            detail=f"nicht erreichbar unter {base} ({type(exc).__name__})",
        ) from None
    _raise_for_status("ollama", resp)
    payload = resp.json()
    raw: Iterable[dict[str, Any]] = payload.get("models") or []
    out: list[ModelInfo] = []
    for item in raw:
        info = _map_ollama(item)
        if info is not None:
            out.append(info)
    out.sort(key=lambda m: m.id)
    return out


def _map_ollama(item: dict[str, Any]) -> ModelInfo | None:
    name = str(item.get("name") or item.get("model") or "").strip()
    if not name:
        return None
    details = item.get("details") or {}
    return ModelInfo(
        provider="ollama",
        id=name,
        label=name,
        extra={
            "size": item.get("size"),
            "parameter_size": details.get("parameter_size"),
            "quantization_level": details.get("quantization_level"),
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingCredentialError(name)
    return value


def _raise_for_status(
    provider: str,
    resp: httpx.Response,
    *,
    suppress_key: str | None = None,
) -> None:
    if resp.is_success:
        return
    # Kein Body in den Fehlertext — Body kann Echo-Keys enthalten.
    detail = resp.reason_phrase or None
    if suppress_key and detail and suppress_key in detail:
        detail = "<redacted>"
    raise ProviderHTTPError(provider, resp.status_code, detail=detail)
