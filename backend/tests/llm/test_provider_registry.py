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
