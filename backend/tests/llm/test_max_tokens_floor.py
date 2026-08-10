"""Zentraler Token-Boden — app.llm.tokens.

Der Boden hebt generative Calls an, ohne die zwei Grenzen zu verletzen, an
denen ein pauschal hohes ``max_tokens`` bricht: das Ausgabelimit des Modells
(``400`` bei OpenAI) und Ollamas gemeinsames Prompt/Ausgabe-Fenster.
"""
from __future__ import annotations

import pytest

from app.llm.tokens import (
    DEFAULT_MAX_TOKENS_FLOOR,
    PROMPT_HEADROOM_TOKENS,
    model_output_limit,
    resolve_max_tokens,
    resolve_max_tokens_floor,
    resolve_num_ctx_for_output,
)
from app.utils.llm_client import LLMClient


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kein Leck aus der Umgebung des Entwicklers in die Erwartungen."""
    for key in (
        "LLM_MAX_TOKENS_FLOOR",
        "LLM_MODEL_OUTPUT_LIMITS_JSON",
        "LLM_MODEL_CONTEXT_LIMITS_JSON",
        "LLM_CONTEXT_LIMIT",
        "OLLAMA_NUM_CTX",
    ):
        monkeypatch.delenv(key, raising=False)


class TestFloor:
    @pytest.mark.parametrize("requested", [256, 800, 1024, 4096, 16384])
    def test_generative_call_is_raised_to_the_floor(self, requested: int) -> None:
        """Genau der Defekt: 4096 für eine Report-Section reicht nicht."""
        assert (
            resolve_max_tokens(requested, model="qwen3:32b")
            == DEFAULT_MAX_TOKENS_FLOOR
        )

    def test_higher_request_survives_the_floor(self) -> None:
        assert resolve_max_tokens(65536, model="qwen3:32b") == 65536

    def test_opt_out_keeps_the_narrow_limit(self) -> None:
        """Klassifikations-Calls behalten ihr enges Limit."""
        assert (
            resolve_max_tokens(256, model="qwen3:32b", enforce_floor=False) == 256
        )

    def test_floor_is_configurable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_MAX_TOKENS_FLOOR", "8192")
        assert resolve_max_tokens(4096, model="qwen3:32b") == 8192

    def test_floor_zero_restores_old_behaviour(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MAX_TOKENS_FLOOR", "0")
        assert resolve_max_tokens(4096, model="qwen3:32b") == 4096

    def test_garbage_floor_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MAX_TOKENS_FLOOR", "viel")
        assert resolve_max_tokens_floor() == DEFAULT_MAX_TOKENS_FLOOR


class TestOutputLimitCap:
    def test_model_below_the_floor_is_capped(self) -> None:
        """gpt-4o nimmt 128k entgegen, gibt aber nur 16.384 zurück."""
        assert resolve_max_tokens(4096, model="gpt-4o-mini") == 16_384

    def test_cap_applies_even_without_the_floor(self) -> None:
        """Ein Aufrufer, der von sich aus zu viel fordert, bekäme sonst 400."""
        assert (
            resolve_max_tokens(32768, model="gpt-4o", enforce_floor=False) == 16_384
        )

    def test_unknown_model_has_no_cap(self) -> None:
        assert model_output_limit("mein-eigenes-modell:7b") is None
        assert (
            resolve_max_tokens(4096, model="mein-eigenes-modell:7b")
            == DEFAULT_MAX_TOKENS_FLOOR
        )

    def test_env_override_wins_over_the_table(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_OUTPUT_LIMITS_JSON", '{"gpt-4o": 2048}')
        assert resolve_max_tokens(4096, model="gpt-4o") == 2048

    def test_broken_env_override_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_OUTPUT_LIMITS_JSON", "{kein json")
        assert resolve_max_tokens(4096, model="gpt-4o") == 16_384

    def test_result_is_never_zero_or_negative(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_OUTPUT_LIMITS_JSON", '{"gpt-4o": 0}')
        assert resolve_max_tokens(4096, model="gpt-4o") == 1


class TestNumCtxFollows:
    """Ollama: max_tokens ist num_predict und teilt das Fenster mit dem Prompt."""

    def test_num_ctx_is_raised_for_a_large_output(self) -> None:
        result = resolve_num_ctx_for_output(8192, 32768, model="qwen3:32b")
        assert result == 32768 + PROMPT_HEADROOM_TOKENS

    def test_num_ctx_is_capped_at_the_model_context_window(self) -> None:
        """qwen3 fasst 131.072 Tokens — mehr anzufordern hilft nicht."""
        result = resolve_num_ctx_for_output(8192, 262_144, model="qwen3:32b")
        assert result == 131_072

    def test_capped_max_tokens_needs_only_the_smaller_window(self) -> None:
        """Zusammenspiel: gemini-2.0-flash gibt höchstens 8192 Tokens aus."""
        max_tokens = resolve_max_tokens(4096, model="gemini-2.0-flash")
        assert max_tokens == 8192
        assert (
            resolve_num_ctx_for_output(8192, max_tokens, model="gemini-2.0-flash")
            == 8192 + PROMPT_HEADROOM_TOKENS
        )

    def test_larger_num_ctx_stays_untouched(self) -> None:
        assert resolve_num_ctx_for_output(131072, 32768, model="qwen3:32b") == 131072

    @pytest.mark.parametrize("num_ctx", [None, 0])
    def test_unset_num_ctx_is_left_alone(self, num_ctx) -> None:
        """Ohne num_ctx entscheidet der Aufrufer bewusst nichts — nicht überschreiben."""
        assert resolve_num_ctx_for_output(num_ctx, 32768, model="qwen3:32b") == num_ctx

    def test_unknown_model_gets_the_full_headroom(self) -> None:
        result = resolve_num_ctx_for_output(8192, 32768, model="unbekannt:1b")
        assert result == 32768 + PROMPT_HEADROOM_TOKENS


class _FakeCompletions:
    def __init__(self) -> None:
        self.captured_kwargs = None
        #: Antworttext des Fakes. ``chat_json`` braucht gueltiges JSON.
        self.content = "ok"

    def create(self, **kwargs):
        self.captured_kwargs = kwargs
        # ``tool_calls`` liest der Tool-Call-Pfad; ohne Tool-Aufruf ist None die
        # korrekte Antwort und fuer die uebrigen Pfade folgenlos.
        message = type("_Msg", (), {"content": self.content, "tool_calls": None})()
        choice = type("_Choice", (), {"message": message, "finish_reason": "stop"})()
        return type("_Resp", (), {"choices": [choice], "usage": None})()


class _FakeOpenAI:
    def __init__(self) -> None:
        self.chat = type("_Chat", (), {"completions": _FakeCompletions()})()


@pytest.fixture()
def fake_client(monkeypatch: pytest.MonkeyPatch):
    """LLMClient ohne echten OpenAI-Init — nur der Request-Aufbau zählt."""
    obj = LLMClient.__new__(LLMClient)
    obj._max_retries = 0
    obj._retry_initial_delay = 0.0
    obj._retry_max_delay = 0.0
    obj._num_ctx = 8192
    obj._think = False
    obj.api_key = "test"
    obj.base_url = "http://localhost:11434/v1"
    obj.model = "qwen3:32b"
    obj.client = _FakeOpenAI()
    monkeypatch.setenv("LLM_FORCE_STREAM", "false")
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
    return obj


class TestClientAppliesTheFloor:
    """Der eigentliche Defekt: die Report-Sections gingen mit 4096 raus."""

    def test_chat_raises_a_low_request_to_the_floor(self, fake_client) -> None:
        fake_client.chat(messages=[{"role": "user", "content": "hi"}], max_tokens=4096)

        captured = fake_client.client.chat.completions.captured_kwargs
        assert captured["max_tokens"] == DEFAULT_MAX_TOKENS_FLOOR

    def test_ollama_num_ctx_follows_the_raised_limit(self, fake_client) -> None:
        """Ohne mitziehendes num_ctx verdrängt num_predict den Prompt."""
        fake_client.chat(messages=[{"role": "user", "content": "hi"}], max_tokens=4096)

        captured = fake_client.client.chat.completions.captured_kwargs
        assert captured["extra_body"]["options"]["num_ctx"] == (
            DEFAULT_MAX_TOKENS_FLOOR + PROMPT_HEADROOM_TOKENS
        )

    def test_opt_out_reaches_the_provider_unchanged(self, fake_client) -> None:
        fake_client.chat(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=256,
            enforce_token_floor=False,
        )

        captured = fake_client.client.chat.completions.captured_kwargs
        assert captured["max_tokens"] == 256

    def test_cap_beats_the_floor_for_a_small_output_model(self, fake_client) -> None:
        fake_client.model = "gpt-4o-mini"
        fake_client.base_url = "https://api.openai.com/v1"
        fake_client.chat(messages=[{"role": "user", "content": "hi"}], max_tokens=4096)

        captured = fake_client.client.chat.completions.captured_kwargs
        assert captured["max_tokens"] == 16_384


class TestChatJsonAppliesTheFloor:
    """``chat_json`` setzt den Boden selbst, nicht erst ueber ``chat``.

    Der native Ollama-Schema-Pfad umgeht ``chat`` vollstaendig. Wuerde der
    Boden nur in ``chat`` sitzen, saehen die beiden Pfade unterschiedliche
    Limits — und der Entailment-Judge, der hier als einziger Aufrufer
    ausdruecklich aussteigt, haette sein Opt-out nur auf einem davon.
    """

    def test_chat_json_raises_a_low_request_to_the_floor(self, fake_client) -> None:
        fake_client.client.chat.completions.content = '{"ok": true}'
        fake_client.chat_json(messages=[{"role": "user", "content": "hi"}], max_tokens=4096)

        captured = fake_client.client.chat.completions.captured_kwargs
        assert captured["max_tokens"] == DEFAULT_MAX_TOKENS_FLOOR

    def test_chat_json_opt_out_keeps_the_narrow_limit(self, fake_client) -> None:
        fake_client.client.chat.completions.content = '{"ok": true}'
        fake_client.chat_json(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=256,
            enforce_token_floor=False,
        )

        captured = fake_client.client.chat.completions.captured_kwargs
        assert captured["max_tokens"] == 256


class TestDescribeImageAppliesTheFloor:
    """Vision lief mit 1024 Tokens — zu wenig fuer eine brauchbare Beschreibung."""

    def test_vision_request_is_raised_to_the_floor(self, fake_client) -> None:
        fake_client.describe_image(image_b64="AA==", prompt="Was ist zu sehen?")

        captured = fake_client.client.chat.completions.captured_kwargs
        assert captured["max_tokens"] == DEFAULT_MAX_TOKENS_FLOOR

    def test_vision_num_ctx_follows_the_raised_limit(self, fake_client) -> None:
        fake_client.describe_image(image_b64="AA==", prompt="Was ist zu sehen?")

        captured = fake_client.client.chat.completions.captured_kwargs
        assert captured["extra_body"]["options"]["num_ctx"] == (
            DEFAULT_MAX_TOKENS_FLOOR + PROMPT_HEADROOM_TOKENS
        )

    def test_vision_num_ctx_never_falls_below_the_documented_minimum(
        self, fake_client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ohne Boden bleibt die alte Untergrenze von 8192 stehen.

        ``describe_image`` klammert ``num_ctx`` mit ``max(..., 8192)``. Faellt
        der Boden weg (``LLM_MAX_TOKENS_FLOOR=0``), darf das Vision-Fenster
        nicht auf den Wert eines 1024-Token-Requests zusammenschrumpfen.
        """
        monkeypatch.setenv("LLM_MAX_TOKENS_FLOOR", "0")
        fake_client.describe_image(image_b64="AA==", prompt="Was ist zu sehen?")

        captured = fake_client.client.chat.completions.captured_kwargs
        assert captured["max_tokens"] == 1024
        assert captured["extra_body"]["options"]["num_ctx"] >= 8192


class TestToolCallsApplyTheFloor:
    """Der Tool-Pfad hat kein Opt-out — dort gilt der Boden immer."""

    _TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "noop",
                "description": "tut nichts",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    def test_tool_request_is_raised_to_the_floor(self, fake_client) -> None:
        fake_client.chat_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=self._TOOLS,
            max_tokens=4096,
        )

        captured = fake_client.client.chat.completions.captured_kwargs
        assert captured["max_tokens"] == DEFAULT_MAX_TOKENS_FLOOR

    def test_tool_num_ctx_follows_the_raised_limit(self, fake_client) -> None:
        fake_client.chat_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=self._TOOLS,
            max_tokens=4096,
        )

        captured = fake_client.client.chat.completions.captured_kwargs
        assert captured["extra_body"]["options"]["num_ctx"] == (
            DEFAULT_MAX_TOKENS_FLOOR + PROMPT_HEADROOM_TOKENS
        )


class TestNarrowLimitCallSitesOptOut:
    """Zwei Aufrufer bleiben absichtlich eng — das darf nicht stillschweigend kippen.

    Ein verlorenes ``enforce_token_floor=False`` faellt sonst nirgends auf: das
    Ergebnis bliebe fachlich korrekt, nur wuerde ein Label-Urteil statt mit 256
    mit 32768 Tokens angefordert. Bei lokalen Modellen kostet das Laufzeit und
    laedt zu Geschwafel ein, ohne dass ein Test rot wird.
    """

    def test_entailment_judge_opts_out(self) -> None:
        from app.services.llm_entailment_judge import (
            EntailmentJudgeVerdict,
            EntailmentVerdict,
            build_llm_judge,
        )

        captured: dict = {}

        class _Stub:
            def chat_json(self, **kwargs):
                captured.update(kwargs)
                return EntailmentJudgeVerdict(
                    verdict=EntailmentVerdict.RELATED_ONLY, reason="test"
                ).model_dump()

        build_llm_judge(_Stub())("Ein Claim.", "Eine Evidence.")  # type: ignore[arg-type]

        assert captured["enforce_token_floor"] is False
        assert captured["max_tokens"] == 256

    def test_graph_interview_summary_opts_out(self) -> None:
        from types import SimpleNamespace

        from app.services.graph_tools import GraphToolsService

        captured: dict = {}

        class _Stub:
            def chat(self, **kwargs):
                captured.update(kwargs)
                return "Zusammenfassung"

        service = GraphToolsService.__new__(GraphToolsService)
        # ``llm`` ist eine lazy Property ohne Setter — das Backing-Feld
        # vorbelegen verhindert, dass ein echter LLMClient gebaut wird.
        service._llm_client = _Stub()  # type: ignore[assignment]
        interview = SimpleNamespace(agent_name="A", agent_role="R", response="Text")

        service._generate_interview_summary([interview], "Thema")  # type: ignore[arg-type]

        assert captured["enforce_token_floor"] is False
        assert captured["max_tokens"] == 800
