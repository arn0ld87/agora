"""Tests fuer die zentrale Provider-Erkennung (Issue #591).

Parametrisierte Kombos ueber Modellname/Base-URL fuer beide Detection-Modi
(``http`` = Backend-HTTP-Client, ``oasis`` = CAMEL-Dispatch) inklusive der
Hybrid-Edge-Cases, in denen die beiden testfixierten Heuristiken bewusst
divergieren.
"""
from __future__ import annotations

import pytest

from app.llm.providers.registry import detect_embedding_provider, detect_provider

# ---------------------------------------------------------------------------
# mode="http" — Verhalten von LLMClient._detect_provider (testfixiert in
# tests/utils/test_llm_client_publishes_model_active.py)
# ---------------------------------------------------------------------------

HTTP_CASES = [
    # (base_url, model, expected)
    ("http://localhost:11434/v1", "qwen2.5:32b", "ollama"),
    ("http://127.0.0.1:11434/v1", "qwen3:8b", "ollama"),
    ("http://localhost:11434/v1", "qwen3-coder-next:cloud", "cloud"),  # Suffix vor Port
    ("https://ollama.com/v1", "qwen3-coder-next:cloud", "cloud"),
    ("https://ollama.com/v1", "gemini-2.5-pro", "cloud"),  # Hybrid: Base-URL gewinnt
    ("https://api.openai.com/v1", "gpt-4", "openai"),
    ("https://api.openai.com/v1", "gpt-5-nano", "openai"),
    (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-3-flash-preview",
        "google",
    ),
    ("http://localhost:11434", "gemini-2.5-pro", "ollama"),  # Hybrid: Port gewinnt
    ("http://some-other-host:8080/v1", "some-model", "unknown"),
    ("", "", "unknown"),
    (None, None, "unknown"),
    ("http://host:114340/v1", "foo", "ollama"),  # Substring-Match (dokumentierte Eigenheit)
    # Issue #670 — Ollama-Cloud-Prod-Tag `name:<size>-cloud` @ Nicht-Standard-Port.
    # Live-Evidenz: base_url=http://<host>:11435/v1, model=gpt-oss:20b-cloud.
    ("http://100.71.152.44:11435/v1", "gpt-oss:20b-cloud", "cloud"),
    ("http://100.71.152.44:11435/v1", "gpt-oss:120b-cloud", "cloud"),
    # Kein False Positive: `-cloud` ohne `:`-Tag ist KEIN Ollama-Signal.
    ("https://api.openai.com/v1", "mistral-large-cloud", "openai"),
    # Kein False Positive: `:`-Tag mit `-cloud` OHNE Groessenpraefix (Dritt-Gateway).
    ("https://api.example.com/v1", "custom:experimental-cloud", "unknown"),
    # MiniMax (MiniMax-M3, ...) — eigener Provider-Branch unter api.minimax.io.
    # Subdomain-Match vor "11434"-Port und vor "openai.com"-Substring, sonst
    # landet MiniMax-M3 fälschlich auf api.openai.com (Smoke 2026-07-14).
    ("https://api.minimax.io/v1", "MiniMax-M3", "minimax"),
    ("https://api.minimax.io/anthropic", "MiniMax-M3", "minimax"),
    ("HTTPS://API.MINIMAX.IO/v1", "MiniMax-M3", "minimax"),  # case-insensitive
    # Issue #750 — Subdomain unter api.minimax.io erkannt (Suffix-Match).
    ("https://foo.api.minimax.io/v1", "MiniMax-M3", "minimax"),
    # CodeQL #750 — kein Substring-False-Positive: Host `api.minimax.io.attacker.test`
    # enthaelt den Text, ist aber nicht der MiniMax-Host → unknown (vorher: minimax).
    ("https://api.minimax.io.attacker.test/v1", "MiniMax-M3", "unknown"),
    # CodeQL #750 — kein Path-False-Positive: `api.minimax.io` im Path eines
    # anderen Hosts → openai (vorher: minimax via Substring).
    ("https://api.openai.com/proxy/api.minimax.io", "MiniMax-M3", "openai"),
    # Kein False Positive: Modellname enthaelt "minimax", Base-URL aber nicht.
    ("https://api.openai.com/v1", "minimax-mock", "openai"),
]


@pytest.mark.parametrize(("base_url", "model", "expected"), HTTP_CASES)
def test_detect_provider_http(base_url, model, expected):
    assert detect_provider(base_url, model, mode="http") == expected


def test_http_is_default_mode():
    assert detect_provider("http://localhost:11434/v1", "qwen2.5:32b") == "ollama"


# ---------------------------------------------------------------------------
# mode="oasis" — Verhalten von scripts/_sim_common.py::detect_oasis_platform
# (testfixiert in tests/scripts/test_oasis_provider_dispatch.py)
# ---------------------------------------------------------------------------

OASIS_CASES = [
    # (base_url, model, expected)
    (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-3-flash-preview",
        "google",
    ),
    ("", "gemini-2.5-flash", "google"),  # Modell-Prefix reicht
    ("https://api.example.com/v1", "gemini-2.0-flash-lite", "google"),
    ("http://localhost:11434", "gemini-2.5-pro", "google"),  # Prefix schlaegt Ollama-URL
    ("https://ollama.com/api", "llama3.2:latest", "ollama"),
    ("https://ollama.com", "qwen3-coder-next:cloud", "ollama"),
    ("http://localhost:11434", "qwen3:8b", "ollama"),
    ("http://127.0.0.1:11434/v1", "qwen3:8b", "ollama"),
    ("", "llama3:latest", "ollama"),
    ("https://any-compat-gateway.example.com", "qwen3-coder-next:cloud", "ollama"),
    ("https://api.openai.com/v1", "gpt-5-nano", "openai"),
    ("", "gpt-4o-mini", "openai"),
    ("http://host:114340/v1", "foo", "openai"),  # Regex matcht NUR exakten Port
    (None, None, "openai"),  # Default-Fallback: OpenAI-Compat-Gateway
    # Issue #670 — Prod-Cloud-Tag muss als Ollama erkannt werden, damit das
    # think/num_ctx-Gate feuert. Live: model=gpt-oss:20b-cloud @ :11435.
    ("http://100.71.152.44:11435/v1", "gpt-oss:20b-cloud", "ollama"),
    ("http://100.71.152.44:11435/v1", "gpt-oss:120b-cloud", "ollama"),
    # Kein False Positive: `-cloud` ohne `:`-Tag bleibt OpenAI-Compat.
    ("https://api.openai.com/v1", "mistral-large-cloud", "openai"),
    # Kein False Positive: `-cloud`-Tag ohne Groessenpraefix bleibt OpenAI-Compat.
    ("https://api.example.com/v1", "custom:experimental-cloud", "openai"),
]


@pytest.mark.parametrize(("base_url", "model", "expected"), OASIS_CASES)
def test_detect_provider_oasis(base_url, model, expected):
    assert detect_provider(base_url, model, mode="oasis") == expected


# ---------------------------------------------------------------------------
# Dokumentierte Divergenzen — gleiche Inputs, unterschiedliche Modi.
# Diese Tests schreiben die BEWUSSTE Nicht-Vereinheitlichung fest (#591):
# beide Verhalten sind durch Bestandstests fixiert; eine stille Angleichung
# waere eine Verhaltensaenderung.
# ---------------------------------------------------------------------------

DIVERGENT_CASES = [
    # (base_url, model, expected_http, expected_oasis)
    ("https://ollama.com/v1", "gemini-2.5-pro", "cloud", "google"),
    ("http://localhost:11434", "gemini-2.5-pro", "ollama", "google"),
    ("https://example.com/v1", "some-model", "unknown", "openai"),
    ("", "llama3:latest", "unknown", "ollama"),  # :latest nur im OASIS-Modus ein Signal
    ("http://host:114340/v1", "foo", "ollama", "openai"),  # Substring vs. Port-Regex
    # MiniMax: HTTP erkennt explizit ("minimax"); OASIS faellt auf
    # OpenAI-Compat-Fallback zurueck (CAMEL-Dispatcher kennt kein
    # "minimax"-PlatformType, OpenAI-Compat-Endpoint funktioniert).
    ("https://api.minimax.io/v1", "MiniMax-M3", "minimax", "openai"),
]


@pytest.mark.parametrize(("base_url", "model", "expected_http", "expected_oasis"), DIVERGENT_CASES)
def test_documented_divergences(base_url, model, expected_http, expected_oasis):
    assert detect_provider(base_url, model, mode="http") == expected_http
    assert detect_provider(base_url, model, mode="oasis") == expected_oasis


# ---------------------------------------------------------------------------
# detect_embedding_provider — Embeddings-API-Shape (Issue #671), vormals
# ``EmbeddingService._detect_provider`` (app/storage/embedding_service.py).
# Bewusst eigenes Vokabular/eigene Logik statt Delegation an detect_provider
# (mode="http"): unterschiedlicher Zweck (Request/Response-Shape der
# Embeddings-API vs. Chat-Adapter-Dispatch) und unterschiedliche Signale
# (z. B. reicht ein blosses "/v1"-Suffix hier fuer "openai", waehrend
# mode="http" dafuer "unknown" liefert).
# ---------------------------------------------------------------------------

EMBEDDING_CASES = [
    # (base_url, model, expected)
    ("http://localhost:11434/v1", "nomic-embed-text", "openai"),  # /v1-Suffix
    ("http://localhost:11434/v1/", "nomic-embed-text", "openai"),  # /v1/-Suffix
    ("https://api.openai.com", "some-model", "openai"),  # Host api.openai.com
    ("http://localhost:11434", "text-embedding-3-small", "openai"),  # Modell-Prefix
    ("http://localhost:11434", "nomic-embed-text", "ollama"),  # Default-Fallback
    ("https://ollama.com", "qwen3-embedding:4b", "ollama"),
    # Lookalike-Hosts duerfen NICHT auf die OpenAI-Shape (Bearer + /v1/embeddings)
    # fallen — exakter Host-Match statt Substring (CodeQL #370, PR #783).
    ("https://api.openai.com.evil.com", "some-model", "ollama"),
    ("https://notapi.openai.com", "some-model", "ollama"),
]


@pytest.mark.parametrize(("base_url", "model", "expected"), EMBEDDING_CASES)
def test_detect_embedding_provider(base_url, model, expected):
    assert detect_embedding_provider(base_url, model) == expected


# ---------------------------------------------------------------------------
# is_ollama_compatible_provider / resolve_ollama_tags_url — Helpers, die
# entscheiden ob /api/tags probet werden darf. Verhindert 404-Spam im Log,
# wenn der aktive Provider MiniMax/OpenAI/Google ist (Issues: MiniMax
# ``/api/tags`` -> 404; OpenAI /api/tags -> 404; Google -> 404).
# ---------------------------------------------------------------------------


def test_is_ollama_compatible_provider_true_for_local_ollama():
    from app.llm.providers.registry import is_ollama_compatible_provider

    assert is_ollama_compatible_provider("http://localhost:11434/v1", "qwen2.5:32b") is True
    assert is_ollama_compatible_provider("http://127.0.0.1:11434", "llama3") is True


def test_is_ollama_compatible_provider_true_for_ollama_cloud():
    from app.llm.providers.registry import is_ollama_compatible_provider

    assert is_ollama_compatible_provider("https://ollama.com/v1", "qwen3-coder-next:cloud") is True
    assert is_ollama_compatible_provider("https://OLLAMA.COM/v1", "x") is True


def test_is_ollama_compatible_provider_false_for_cloud_providers():
    """MiniMax/OpenAI/Google dürfen NICHT als Ollama-kompatibel zählen."""
    from app.llm.providers.registry import is_ollama_compatible_provider

    # MiniMax
    assert is_ollama_compatible_provider("https://api.minimax.io/v1", "MiniMax-M3") is False
    # OpenAI
    assert is_ollama_compatible_provider("https://api.openai.com/v1", "gpt-4") is False
    # Google Gemini
    assert is_ollama_compatible_provider(
        "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-3"
    ) is False
    # Unknown
    assert is_ollama_compatible_provider("https://example.com/v1", "foo") is False


def test_resolve_ollama_tags_url_returns_none_for_minimax():
    """Regression: MiniMax-Provider darf KEIN Probe auf /api/tags auslösen."""
    from app.llm.providers.registry import resolve_ollama_tags_url

    assert resolve_ollama_tags_url("https://api.minimax.io/v1", "MiniMax-M3") is None


def test_resolve_ollama_tags_url_returns_none_for_openai():
    from app.llm.providers.registry import resolve_ollama_tags_url

    assert resolve_ollama_tags_url("https://api.openai.com/v1", "gpt-4") is None


def test_resolve_ollama_tags_url_returns_base_for_local_ollama():
    from app.llm.providers.registry import resolve_ollama_tags_url

    # Default-Setup: LLM_BASE_URL=http://localhost:11434/v1
    # Erwartet: http://localhost:11434 (ohne /v1-Suffix)
    assert resolve_ollama_tags_url("http://localhost:11434/v1", "qwen2.5:32b") == "http://localhost:11434"
    assert resolve_ollama_tags_url("http://localhost:11434/v1/", "qwen2.5:32b") == "http://localhost:11434"
    assert resolve_ollama_tags_url("http://localhost:11434", "qwen2.5:32b") == "http://localhost:11434"


def test_resolve_ollama_tags_url_prefers_explicit_env(monkeypatch):
    """``OLLAMA_BASE_URL`` schlägt ``LLM_BASE_URL`` — Operator kann den Probe
    auf einen separaten Ollama-Host umleiten, ohne den aktiven Provider zu
    ändern."""
    from app.llm.providers.registry import resolve_ollama_tags_url

    # Active provider is Ollama (11434); explicit env points elsewhere
    result = resolve_ollama_tags_url(
        "http://localhost:11434/v1",
        "qwen2.5:32b",
        explicit_base_url="http://ollama.internal.lan:9999",
    )
    assert result == "http://ollama.internal.lan:9999"


def test_resolve_ollama_tags_url_explicit_env_strips_trailing_slash():
    from app.llm.providers.registry import resolve_ollama_tags_url

    result = resolve_ollama_tags_url(
        "http://localhost:11434/v1",
        "qwen2.5:32b",
        explicit_base_url="http://ollama.internal.lan:9999/",
    )
    assert result == "http://ollama.internal.lan:9999"


def test_resolve_ollama_tags_url_explicit_env_wins_over_non_ollama_chat_provider():
    """``OLLAMA_BASE_URL`` schlägt das Provider-Gate.

    Reales Setup: Chat läuft über MiniMax-M3, Embeddings über ein lokales
    Ollama. Würde das Provider-Gate vor der Env greifen, verschwände der
    erreichbare Ollama-Server aus dem Status, sobald der Chat-Provider
    wechselt. Der Probe geht dabei an die Ollama-URL, niemals an MiniMax.
    """
    from app.llm.providers.registry import resolve_ollama_tags_url

    resolved = resolve_ollama_tags_url(
        "https://api.minimax.io/v1",
        "MiniMax-M3",
        explicit_base_url="http://localhost:11434",
    )
    assert resolved == "http://localhost:11434"
    assert "minimax" not in resolved


def test_resolve_ollama_tags_url_returns_none_when_non_ollama_without_env():
    """Ohne ``OLLAMA_BASE_URL`` bleibt das Provider-Gate hart — kein
    ``/api/tags`` gegen MiniMax."""
    from app.llm.providers.registry import resolve_ollama_tags_url

    assert (
        resolve_ollama_tags_url(
            "https://api.minimax.io/v1",
            "MiniMax-M3",
            explicit_base_url=None,
        )
        is None
    )
    assert (
        resolve_ollama_tags_url(
            "https://api.minimax.io/v1",
            "MiniMax-M3",
            explicit_base_url="   ",
        )
        is None
    )


# ---------------------------------------------------------------------------
# Review-Findings PR #955 — /v1-Normalisierung und Custom-Port-Ollama.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("explicit", "expected"),
    [
        ("http://localhost:11434", "http://localhost:11434"),
        ("http://localhost:11434/", "http://localhost:11434"),
        # CodeRabbit-Finding: OLLAMA_BASE_URL im selben Format wie
        # LLM_BASE_URL gesetzt. Ohne Normalisierung entsteht
        # ".../v1/api/tags" → 404, exakt die Fehlerklasse dieses Fixes.
        ("http://localhost:11434/v1", "http://localhost:11434"),
        ("http://localhost:11434/v1/", "http://localhost:11434"),
        ("  http://localhost:11434/v1  ", "http://localhost:11434"),
    ],
)
def test_resolve_ollama_tags_url_normalises_explicit_env(explicit, expected):
    """Beide Zweige strippen ``/v1`` identisch — kein ``/v1/api/tags``."""
    from app.llm.providers.registry import resolve_ollama_tags_url

    resolved = resolve_ollama_tags_url(
        "https://api.minimax.io/v1", "MiniMax-M3", explicit_base_url=explicit
    )
    assert resolved == expected
    assert not resolved.endswith("/v1")


def test_resolve_ollama_tags_url_probes_unknown_provider():
    """Codex-Finding: selbstgehostetes Ollama auf Nicht-Standard-Port.

    ``http://ollama.internal:11435/v1`` fällt in ``detect_provider`` auf
    ``"unknown"`` zurück, bedient ``/api/tags`` aber sehr wohl. Diesen
    Endpoint zu überspringen wäre eine Regression: die Liste der installierten
    Modelle verschwände und der Dienst würde als ungeprüft gemeldet.
    """
    from app.llm.providers.registry import (
        detect_provider,
        resolve_ollama_tags_url,
    )

    base = "http://ollama.internal:11435/v1"
    assert detect_provider(base, "llama3", mode="http") == "unknown"
    assert resolve_ollama_tags_url(base, "llama3") == "http://ollama.internal:11435"


@pytest.mark.parametrize("provider_url", [
    "https://api.minimax.io/v1",
    "https://api.openai.com/v1",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
])
def test_resolve_ollama_tags_url_still_skips_known_cloud_providers(provider_url):
    """Der eigentliche Bugfix bleibt scharf: kein /api/tags gegen Cloud-APIs."""
    from app.llm.providers.registry import resolve_ollama_tags_url

    assert resolve_ollama_tags_url(provider_url, "some-model") is None
