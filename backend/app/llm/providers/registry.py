"""Zentrale Provider-Erkennung — Single Source of Truth (Issue #591).

Vorher existierten zwei unabhängige Detection-Heuristiken:

1. ``LLMClient._detect_provider`` (``app/llm/providers/base.py``) — für den
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

Hinweis: Diese Datei ist im Zuge von #591 auf den main-Split (``8b552b4``)
portiert worden; der Adapter-Lookup (``get_adapter``) folgt mit #590.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal, Optional, Union, overload
from urllib.parse import urlparse

if TYPE_CHECKING:
    from app.llm.providers.base import ProviderAdapter

# Teilmengen von app.contracts.provider_types.ProviderType
HttpDetectedProvider = Literal[
    "ollama", "cloud", "minimax", "openai", "google", "unknown"
]
OasisDetectedProvider = Literal["google", "ollama", "openai"]
DetectionMode = Literal["http", "oasis"]

# Exakter Ollama-Port (nur ":11434" gefolgt von "/" oder Stringende) —
# Verhalten aus scripts/_sim_common.py uebernommen.
_OASIS_OLLAMA_PORT_RE = re.compile(r":11434(?:/|$)")

# Ollama-Cloud-Size-Tag: fuehrende Groesse (Zahl + optionale Einheit) gefolgt
# von ``-cloud`` — z. B. ``20b-cloud``, ``120b-cloud``, ``1t-cloud``. Bewusst
# eng, damit ``<name>:<wort>-cloud`` (ohne Groessenpraefix) auf einem
# Nicht-Ollama-Gateway KEIN False-Positive ausloest.
_OLLAMA_CLOUD_SIZE_TAG_RE = re.compile(r"\d+[a-z]*-cloud")


def _is_ollama_cloud_tag(model: str) -> bool:
    """True, wenn der Modellname ein Ollama-Cloud-Tag traegt (Issue #670).

    Ollama-Cloud-Modelle folgen der ``name:tag``-Konvention, deren Tag ein
    Cloud-Tag ist — entweder das blosse ``:cloud`` (z. B.
    ``qwen3-coder-next:cloud``) oder ein ``:<size>-cloud`` (z. B.
    ``gpt-oss:20b-cloud``, das produktive Modell hinter ``ollama.com`` @
    Nicht-Standard-Port ``:11435``; weitere reale Tags: ``120b-cloud``,
    ``480b-cloud``, ``1t-cloud``).

    Bewusst NICHT als Ollama-Signal (kein False-Positive):
    - ``mistral-large-cloud`` — kein ``:``-Tag.
    - ``custom:experimental-cloud`` — ``-cloud``-Suffix ohne Groessenpraefix,
      wie ihn Dritt-Gateways (vLLM/LiteLLM) fuehren koennten.
    """
    if ":" not in model:
        return False
    tag = model.rsplit(":", 1)[-1]
    return tag == "cloud" or _OLLAMA_CLOUD_SIZE_TAG_RE.fullmatch(tag) is not None


def _detect_http(base_url: Optional[str], model: Optional[str]) -> HttpDetectedProvider:
    """
    Detect the provider used by the backend HTTP client.
    
    Provider detection follows a fixed priority order: Ollama Cloud URLs and
    cloud model tags, MiniMax URLs, local Ollama ports, OpenAI URLs, and Google
    URLs. Inputs that match none of these patterns are classified as unknown.
    
    Parameters:
        base_url (Optional[str]): The provider endpoint URL.
        model (Optional[str]): The model identifier, including any provider tag.
    
    Returns:
        HttpDetectedProvider: The detected provider identifier.
    """
    model_name = model or ""
    base = (base_url or "").lower()
    if "ollama.com" in base:
        return "cloud"
    if _is_ollama_cloud_tag(model_name):
        return "cloud"
    # CodeQL #750 — match the URL hostname exactly (suffix) instead of a raw
    # substring, which would also match `api.minimax.io.attacker.test` or
    # paths/query containing the text and misroute requests through
    # PROVIDER_MINIMAX. Consistent hostname-based detection for all providers
    # (ollama.com, openai.com, googleapis.com) is tracked in Phase F (#671)
    # / #750 — this PR only fixes the NEW minimax branch.
    _minimax_host = urlparse(base).hostname
    if _minimax_host and (
        _minimax_host == "api.minimax.io"
        or _minimax_host.endswith(".api.minimax.io")
    ):
        return "minimax"
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
       ODER Modell traegt ein Ollama-Cloud-Tag (``:cloud`` / ``:<size>-cloud``,
       Issue #670) ODER endet auf ``:latest``. Ollama Cloud bietet keinen
       OpenAI-Compat-``/v1``-Endpoint mehr; nur ``/api/chat`` (nativ).
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
        or _is_ollama_cloud_tag(m)
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

    ``mode="http"``  — Vokabular ``ollama|cloud|minimax|openai|google|unknown``;
    nutzt der OpenAI-kompatible Backend-HTTP-Client (``LLMClient``).

    ``mode="oasis"`` — Vokabular ``google|ollama|openai``; nutzt das
    CAMEL-``ModelPlatformType``-Dispatching der Simulations-Skripte.

    Beide Modi sind testfixiert und absichtlich getrennt — Divergenzen
    siehe Modul-Docstring.
    """
    if mode == "http":
        return _detect_http(base_url, model)
    return _detect_oasis(base_url, model)


EmbeddingDetectedProvider = Literal["openai", "ollama"]


def detect_embedding_provider(
    base_url: Optional[str], model: Optional[str]
) -> EmbeddingDetectedProvider:
    """Erkennt die Embeddings-API-Shape (Issue #671), vormals
    ``EmbeddingService._detect_provider`` in ``app/storage/embedding_service.py``.

    Bewusst KEINE Delegation an :func:`detect_provider` (``mode="http"``):
    beide Funktionen loesen unterschiedliche Probleme mit unterschiedlichem
    Vokabular. ``detect_provider`` entscheidet, welcher Chat-``ProviderAdapter``
    (Dispatch) genutzt wird; ``detect_embedding_provider`` entscheidet nur,
    welche Request-/Response-Shape die Embeddings-API hat
    (``POST /v1/embeddings`` + Bearer-Header vs. ``POST /api/embed``). Die
    Signale divergieren entsprechend — z. B. reicht hier ein blosses
    ``/v1``-Suffix der Base-URL fuer ``"openai"``, waehrend ``mode="http"``
    dafuer ``"unknown"`` liefert (dort ist ``/v1`` allein kein Signal).
    Eine Zusammenfuehrung waere eine Verhaltensaenderung an einer
    testfixierten Heuristik.

    Prioritaet (first match wins):
    1. ``"openai"`` — Base-URL endet auf ``/v1``/``/v1/``, Host ist
       ``api.openai.com``, oder Modellname beginnt mit ``text-embedding-``.
    2. ``"ollama"`` — Fallback fuer alles andere (z. B. lokaler/Cloud-Ollama-
       Server mit nativer ``/api/embed``-Route).
    """
    normalized_base = (base_url or "").lower()
    host = urlparse(normalized_base).hostname or ""
    model_name = model or ""
    if (
        normalized_base.endswith("/v1")
        or normalized_base.endswith("/v1/")
        or host == "api.openai.com"
        or model_name.startswith("text-embedding-")
    ):
        return "openai"
    return "ollama"


def get_adapter(
    provider: str, *, num_ctx: Optional[int] = None, think: bool = False
) -> "ProviderAdapter":
    """Liefert den passenden :class:`ProviderAdapter` fuer einen Provider-String.

    Mappt das Vokabular beider Detection-Modi (``http``: ollama/cloud/minimax/
    openai/google/unknown; ``oasis``: google/ollama/openai) auf die konkreten
    Adapter-Klassen:

    - ``ollama``, ``cloud`` und ``ollama_cloud`` ->
      :class:`~app.llm.providers.ollama.OllamaAdapter` (Ollama Cloud nutzt
      denselben Adapter wie lokales Ollama).
    - ``google`` -> :class:`~app.llm.providers.gemini.GeminiAdapter`.
    - ``openai`` und ``unknown`` (Default) ->
      :class:`~app.llm.providers.openai.OpenAIAdapter`.

    Adapter-Importe sind bewusst lazy (innerhalb der Funktion), um einen
    Import-Zyklus zu vermeiden: ``base`` importiert ``registry`` (fuer
    ``detect_provider``), die Adapter importieren ``base`` (fuer
    ``ProviderAdapter``). Zur Laufzeit wird der Zyklus erst aufgeloest, wenn
    ``get_adapter`` tatsächlich gerufen wird.

    KEIN ``'gemini'``-String-Literal — die Detection liefert ``"google"``
    fuer Gemini-Modelle; das ``gemini``-Literal-Gate
    (``test_no_gemini_literals_in_code``) bleibt unangetastet.
    """
    if provider in ("ollama", "cloud", "ollama_cloud"):
        from app.llm.providers.ollama import OllamaAdapter

        return OllamaAdapter(num_ctx=num_ctx, think=think)
    if provider == "google":
        from app.llm.providers.gemini import GeminiAdapter

        return GeminiAdapter(num_ctx=num_ctx, think=think)
    from app.llm.providers.openai import OpenAIAdapter

    return OpenAIAdapter(num_ctx=num_ctx, think=think)
