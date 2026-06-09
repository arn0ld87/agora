"""Zentrale Provider-Erkennung — Single Source of Truth (Issue #591).

Vorher existierten zwei unabhängige Detection-Heuristiken:

1. ``LLMClient._detect_provider`` (``app/utils/llm_client.py``) — für den
   OpenAI-kompatiblen HTTP-Client des Backends.
2. ``detect_oasis_platform`` (``backend/scripts/_sim_common.py``) — für das
   CAMEL-``ModelPlatformType``-Dispatching der OASIS-Subprozesse.

Beide Verhalten sind durch bestehende Tests festgeschrieben
(``tests/utils/test_llm_client_publishes_model_active.py`` bzw.
``tests/scripts/test_oasis_provider_dispatch.py``) und divergieren bewusst —
deshalb leben hier BEIDE Pfade hinter EINER Funktion mit explizitem
``mode``-Parameter statt einer (verhaltensändernden) Zusammenführung.

Dokumentierte Divergenzen zwischen ``mode="http"`` und ``mode="oasis"``:

================  =========================  ============================
Aspekt            http (Backend-HTTP-Client)  oasis (CAMEL-Dispatch)
================  =========================  ============================
Priorität         Base-URL zuerst             ``gemini-``-Modell-Prefix
                  (ollama.com → :cloud →      zuerst, dann Ollama-Signale,
                  11434 → openai → google)    Default OpenAI
Gemini-Erkennung  nur über Base-URL           Base-URL ODER Modell-Prefix
                  (googleapis/generativelang) ``gemini-`` (Gemini-3 braucht
                                              ``thought_signature``-Echo,
                                              das der OpenAI-Compat-Pfad
                                              wegstrippt)
Ollama-Port       Substring ``"11434"``       Regex ``:11434(?:/|$)``
                  (matcht auch ``:114340``)   (nur exakter Port)
``:latest``-Tag   kein Signal                 → ``"ollama"``
Fallback          ``"unknown"``               ``"openai"`` (Compat-Gateways)
Vokabular         ollama/cloud/openai/        google/ollama/openai
                  google/unknown              (cloud+lokal ⇒ ``"ollama"``)
================  =========================  ============================

Hybrid-Beispiel: ``gemini-2.5-pro`` @ ``http://localhost:11434`` ergibt
``http → "ollama"``, aber ``oasis → "google"`` — der OASIS-Pfad MUSS die
native Gemini-API nutzen (Tool-Turns schlagen sonst mit HTTP 400 fehl),
während der HTTP-Client weiterhin den lokalen Ollama-Proxy anspricht.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal, Optional, Union, overload

if TYPE_CHECKING:
    from app.llm.providers.base import ProviderAdapter

# Teilmengen von app.contracts.provider_types.ProviderType
HttpDetectedProvider = Literal["ollama", "cloud", "openai", "google", "unknown"]
OasisDetectedProvider = Literal["google", "ollama", "openai"]
DetectionMode = Literal["http", "oasis"]

# Exakter Ollama-Port (nur ":11434" gefolgt von "/" oder Stringende) —
# Verhalten aus scripts/_sim_common.py uebernommen.
_OASIS_OLLAMA_PORT_RE = re.compile(r":11434(?:/|$)")


def _detect_http(base_url: Optional[str], model: Optional[str]) -> HttpDetectedProvider:
    """Heuristik des Backend-HTTP-Clients (vormals ``LLMClient._detect_provider``).

    Prioritäten:
    1. Base URL enthält ``ollama.com`` → ``"cloud"`` (Ollama Cloud proxy).
    2. Modell-Suffix ``:cloud`` → ``"cloud"`` (Cloud-Modelle laufen auch über
       den lokalen ollama-Proxy auf :11434 — deshalb VOR der Port-Heuristik).
    3. Base URL enthält ``11434`` → ``"ollama"`` (lokales Ollama).
    4. Base URL enthält ``openai.com`` oder ``api.openai`` → ``"openai"``.
    5. Base URL enthält ``googleapis.com`` oder ``generativelanguage`` →
       ``"google"`` (Gemini-OpenAI-Compat-Layer mit nativem ``tools=``).
    6. Fallback → ``"unknown"``.
    """
    model_name = model or ""
    base = (base_url or "").lower()
    if "ollama.com" in base:
        return "cloud"
    if model_name.endswith(":cloud"):
        return "cloud"
    if "11434" in base:
        return "ollama"
    if "openai.com" in base or "api.openai" in base:
        return "openai"
    if "googleapis.com" in base or "generativelanguage" in base:
        return "google"
    return "unknown"


def _detect_oasis(base_url: Optional[str], model: Optional[str]) -> OasisDetectedProvider:
    """Heuristik des OASIS-/CAMEL-Dispatches (vormals ``detect_oasis_platform``).

    Prioritäten (first match wins):
    1. ``"google"`` — Base-URL enthält ``generativelanguage.googleapis.com``
       ODER Modell beginnt mit ``gemini-``. Gemini-3 verlangt ein
       ``thought_signature``-Echo in Multi-Turn-Tool-Calls; der
       OpenAI-Compat-Pfad strippt das Feld → HTTP 400 bei jedem Tool-Turn.
    2. ``"ollama"`` — Base-URL enthält ``ollama.com`` oder Port ``:11434``
       ODER Modell endet auf ``:cloud`` / ``:latest``. Ollama Cloud bietet
       keinen OpenAI-Compat-``/v1``-Endpoint mehr; nur ``/api/chat`` (nativ).
    3. ``"openai"`` — alles andere (echtes OpenAI, Compat-Gateways, Qwen
       Cloud über Nicht-Ollama-URLs, Mistral, DeepSeek, …).
    """
    url = base_url or ""
    m = model or ""

    if "generativelanguage.googleapis.com" in url or m.startswith("gemini-"):
        return "google"

    if (
        "ollama.com" in url
        or _OASIS_OLLAMA_PORT_RE.search(url)
        or m.endswith(":cloud")
        or m.endswith(":latest")
    ):
        return "ollama"

    return "openai"


@overload
def detect_provider(
    base_url: Optional[str],
    model: Optional[str],
    *,
    mode: Literal["http"] = "http",
) -> HttpDetectedProvider: ...


@overload
def detect_provider(
    base_url: Optional[str],
    model: Optional[str],
    *,
    mode: Literal["oasis"],
) -> OasisDetectedProvider: ...


def detect_provider(
    base_url: Optional[str],
    model: Optional[str],
    *,
    mode: DetectionMode = "http",
) -> Union[HttpDetectedProvider, OasisDetectedProvider]:
    """Erkennt den LLM-Provider aus Base-URL + Modellname.

    ``mode="http"``  — Vokabular ``ollama|cloud|openai|google|unknown``;
    nutzt der OpenAI-kompatible Backend-HTTP-Client (``LLMClient``).

    ``mode="oasis"`` — Vokabular ``google|ollama|openai``; nutzt das
    CAMEL-``ModelPlatformType``-Dispatching der Simulations-Skripte.

    Beide Modi sind testfixiert und absichtlich getrennt — Divergenzen
    siehe Modul-Docstring.
    """
    if mode == "http":
        return _detect_http(base_url, model)
    return _detect_oasis(base_url, model)


def get_adapter(
    provider: str,
    *,
    num_ctx: Optional[int] = None,
    think: bool = False,
) -> "ProviderAdapter":
    """Loest einen erkannten Provider auf den passenden Adapter auf (#590).

    Akzeptiert das volle ``ProviderType``-Vokabular plus die Detection-
    Vokabulare beider Modi. Unbekannte/generische Provider laufen ueber den
    OpenAI-Adapter (OpenAI-Wire-Format als kleinster gemeinsamer Nenner).
    """
    # Lazy Imports: Skripte (z. B. scripts/_sim_common.py) sollen die Registry
    # nutzen koennen, ohne die Adapter-Abhaengigkeiten (openai-SDK) zu laden.
    if provider in ("ollama", "cloud", "ollama_cloud"):
        from app.llm.providers.ollama import OllamaAdapter

        return OllamaAdapter(num_ctx=num_ctx, think=think)
    if provider == "google":
        from app.llm.providers.gemini import GeminiAdapter

        return GeminiAdapter(num_ctx=num_ctx, think=think)
    from app.llm.providers.openai import OpenAIAdapter

    return OpenAIAdapter(num_ctx=num_ctx, think=think)
