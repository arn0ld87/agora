"""Regression fuer Issue #1072 — OpenAI-Compat-Base-URL im chat()-Pfad.

Ollama-Connections fuehren eine Base-URL an der Server-Wurzel, weil die
Modell-Discovery ``/api/tags`` direkt daran haengt. Der OpenAI-SDK-Client
braucht dagegen ``/v1``, sonst landet ``POST /chat/completions`` auf einer
Route, die Ollama nicht kennt — Antwort: Plaintext ``404 page not found``.
Genau daran sind im Lauf ``sim_d27370937936`` alle Post-Simulations-
Interviews gescheitert.

Die Kanonisierung darf ausschliesslich den SDK-Client betreffen:
``LLMClient.base_url`` speist Provider-Detection, Invocation-Log und den
nativen ``/api/chat``-Pfad und muss roh bleiben.
"""
from __future__ import annotations

import pytest

from app.llm.client import LLMClient
from app.llm.providers.registry import openai_compat_base_url

_OLLAMA_LOCAL = "http://host.docker.internal:11434"
_OLLAMA_MODEL = "deepseek-v4-flash:0731-cloud"


class TestOpenAiCompatBaseUrl:
    """Reine Funktionsebene — welche URL bekommt der OpenAI-SDK-Client?"""

    @pytest.mark.parametrize(
        "base_url, model, expected",
        [
            # Der produktive Defekt: lokaler Ollama-Port ohne /v1.
            (_OLLAMA_LOCAL, _OLLAMA_MODEL, f"{_OLLAMA_LOCAL}/v1"),
            ("http://localhost:11434", "llama3", "http://localhost:11434/v1"),
            # Ollama Cloud an der Wurzel — Registry-Default.
            ("https://ollama.com", "gpt-oss:20b-cloud", "https://ollama.com/v1"),
            # Bereits kanonisch: idempotent, kein doppeltes /v1.
            ("http://localhost:11434/v1", "llama3", "http://localhost:11434/v1"),
            ("https://ollama.com/v1", "gpt-oss:20b-cloud", "https://ollama.com/v1"),
            # Trailing Slash darf nicht zu "//v1" werden.
            ("http://localhost:11434/", "llama3", "http://localhost:11434/v1"),
        ],
    )
    def test_ollama_endpoints_get_v1(self, base_url, model, expected):
        assert openai_compat_base_url(base_url, model) == expected

    @pytest.mark.parametrize(
        "base_url, model",
        [
            # Defaults, die bereits korrekt sind — kein Anfassen.
            ("https://api.openai.com/v1", "gpt-4o"),
            ("https://api.minimax.io/v1", "MiniMax-M3"),
            ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-pro"),
            # openai_compatible an der Wurzel ist ein legitimer Fall: der
            # E2E-Mock-Server bedient /models, nicht /v1/models. Eine
            # "URL ohne Pfad bekommt /v1"-Heuristik wuerde ihn beschaedigen.
            ("http://mock-models", "any-model"),
            ("https://gateway.example/custom", "any-model"),
            # Kernfall des Codex-Reviews zu PR #1077: ein Gateway an der
            # Wurzel, das ein Ollama-Modell durchreicht (LiteLLM/vLLM tun
            # das). detect_provider() stuft das ueber den :cloud-Tag als
            # Ollama ein — die Endpunkt-Kanonisierung darf dem nicht folgen,
            # sonst zeigt jeder chat()-Call dieser Connection ins Leere.
            ("https://gateway.example", "qwen3-coder-next:cloud"),
            ("http://mock-models", "gpt-oss:20b-cloud"),
            # Host-Suffix-Falle: keine echte ollama.com-Domain.
            ("https://ollama.com.attacker.test", "llama3"),
            # Anthropic ist bewusst NICHT Teil dieses Fixes (Issue #1072):
            # kein Chat-Adapter, keine Detection, unverifiziert.
            ("https://api.anthropic.com", "claude-sonnet-4"),
        ],
    )
    def test_non_ollama_endpoints_stay_untouched(self, base_url, model):
        assert openai_compat_base_url(base_url, model) == base_url

    def test_empty_base_url_stays_empty(self):
        """``None`` heisst "SDK-Default" und darf nicht zu "/v1" werden."""
        assert openai_compat_base_url(None, "llama3") is None
        assert openai_compat_base_url("", "llama3") == ""

    @pytest.mark.parametrize(
        "base_url, model, expected",
        [
            # Issue #1282 — Bedrock mantle ohne /v1: Suffix wird angehaengt.
            (
                "https://bedrock-mantle.eu-central-1.api.aws",
                "anthropic.claude-sonnet-5",
                "https://bedrock-mantle.eu-central-1.api.aws/v1",
            ),
            # bedrock-mantle mit /v1: idempotent, kein doppeltes /v1.
            (
                "https://bedrock-mantle.eu-central-1.api.aws/v1",
                "anthropic.claude-opus-4-8",
                "https://bedrock-mantle.eu-central-1.api.aws/v1",
            ),
            # bedrock-runtime ohne /v1: Suffix wird angehaengt.
            (
                "https://bedrock-runtime.us-east-1.amazonaws.com",
                "openai.gpt-5.6-sol",
                "https://bedrock-runtime.us-east-1.amazonaws.com/v1",
            ),
            # bedrock-runtime mit /v1: idempotent.
            (
                "https://bedrock-runtime.us-east-1.amazonaws.com/v1",
                "openai.gpt-oss-120b",
                "https://bedrock-runtime.us-east-1.amazonaws.com/v1",
            ),
        ],
    )
    def test_bedrock_endpoints_get_v1(self, base_url, model, expected):
        assert openai_compat_base_url(base_url, model) == expected


class TestLlmClientAppliesCanonicalUrl:
    """Integrationsebene — der Client verdrahtet die Kanonisierung korrekt."""

    def test_ollama_client_calls_v1_but_keeps_raw_base_url(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_THINKING", raising=False)
        client = LLMClient(
            api_key="k",
            base_url=_OLLAMA_LOCAL,
            model=_OLLAMA_MODEL,
            use_active_config=False,
        )

        # Der SDK-Client spricht den OpenAI-Compat-Pfad an ...
        assert str(client.client.base_url).rstrip("/") == f"{_OLLAMA_LOCAL}/v1"
        # ... waehrend die rohe Route erhalten bleibt: Provider-Detection,
        # Invocation-Log und der native /api/chat-Pfad haengen daran.
        assert client.base_url == _OLLAMA_LOCAL

    def test_non_ollama_client_base_url_is_unchanged(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_THINKING", raising=False)
        client = LLMClient(
            api_key="k",
            base_url="https://api.minimax.io/v1",
            model="MiniMax-M3",
            use_active_config=False,
        )

        assert str(client.client.base_url).rstrip("/") == "https://api.minimax.io/v1"
        assert client.base_url == "https://api.minimax.io/v1"
