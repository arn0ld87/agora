"""Provider-aware extra_body-Builder für CAMEL ModelFactory.create().

Regression-Cover für den `Unknown parameter: 'think'` 400 von OpenAI:
`think` ist ein Ollama-Reasoning-Toggle (gpt-oss / qwen3-thinking /
deepseek-r1). OpenAI/Anthropic/Mistral kennen den Parameter nicht und
antworten 400. Der Helper darf den Parameter ausschließlich für Ollama-
Routen einsetzen.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ liegt nicht auf dem Default-Pythonpath des Test-Runners.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _sim_common import (  # noqa: E402
    build_camel_extra_body,
    build_minimax_extra_body,
    _is_minimax_route,
    _is_ollama_route,
)


class TestBuildCamelExtraBodyOllamaLocal:
    """Lokales Ollama (base_url enthält Port 11434)."""

    def test_local_ollama_sets_think_false_by_default(self) -> None:
        body = build_camel_extra_body(
            model="qwen3-coder",
            base_url="http://localhost:11434/v1",
            num_ctx=8192,
            think=False,
        )
        assert body == {"think": False, "options": {"num_ctx": 8192}}

    def test_local_ollama_sets_think_true_when_explicit(self) -> None:
        body = build_camel_extra_body(
            model="qwen3-coder",
            base_url="http://127.0.0.1:11434/v1",
            num_ctx=16384,
            think=True,
        )
        assert body == {"think": True, "options": {"num_ctx": 16384}}

    def test_local_ollama_omits_options_when_num_ctx_none(self) -> None:
        body = build_camel_extra_body(
            model="qwen3-coder",
            base_url="http://localhost:11434/v1",
            num_ctx=None,
            think=False,
        )
        assert body == {"think": False}


class TestBuildCamelExtraBodyOllamaCloud:
    """Ollama Cloud — Modell-Suffix `:cloud`, base_url egal."""

    def test_cloud_model_sets_think_regardless_of_base_url(self) -> None:
        body = build_camel_extra_body(
            model="qwen3-coder-next:cloud",
            base_url="https://ollama.com/v1",
            num_ctx=262144,
            think=False,
        )
        assert body == {"think": False, "options": {"num_ctx": 262144}}


class TestBuildCamelExtraBodyOpenAI:
    """OpenAI-Direct — `think` darf NICHT gesetzt werden (400 sonst)."""

    def test_openai_returns_empty_dict(self) -> None:
        body = build_camel_extra_body(
            model="gpt-5.4-mini",
            base_url="https://api.openai.com/v1",
            num_ctx=128000,
            think=False,
        )
        assert body == {}

    def test_openai_drops_think_even_when_true(self) -> None:
        body = build_camel_extra_body(
            model="gpt-5.4-mini",
            base_url="https://api.openai.com/v1",
            num_ctx=None,
            think=True,
        )
        assert "think" not in body
        assert "options" not in body

    def test_unknown_provider_returns_empty_dict(self) -> None:
        # Default-Path: wenn weder Ollama-URL noch :cloud-Suffix erkennbar
        # sind, conservatively keine Ollama-Parameter senden.
        body = build_camel_extra_body(
            model="claude-opus-4-7",
            base_url="https://api.anthropic.com/v1",
            num_ctx=200000,
            think=False,
        )
        assert body == {}

    def test_empty_base_url_with_plain_model_treated_as_openai(self) -> None:
        # Bei leerer base_url nutzt CAMEL OpenAI als Default — kein Ollama.
        body = build_camel_extra_body(
            model="gpt-5.4-mini",
            base_url="",
            num_ctx=None,
            think=False,
        )
        assert body == {}


class TestBuildCamelExtraBodySSoTDelegation:
    """Issue #670 — `_is_ollama_route` delegiert an die Provider-SSoT
    (`registry.detect_provider(mode="oasis")`). Die alte lokale Heuristik
    (`:cloud`-Suffix ODER Substring `11434`) verfehlte `ollama.com/v1`-URLs
    ohne `:cloud`-Suffix sowie `:latest`-Modelle → think/num_ctx-Gate
    faelschlich aus.
    """

    def test_ollama_com_url_without_cloud_suffix_sets_think(self) -> None:
        # RED vor SSoT-Delegation: ollama.com/v1 + gpt-oss:120b (kein :cloud,
        # kein Port 11434) → alte Heuristik liefert False → leerer Body.
        # Nach der Delegation erkennt die SSoT `ollama.com` in der Base-URL.
        body = build_camel_extra_body(
            model="gpt-oss:120b",
            base_url="https://ollama.com/v1",
            num_ctx=262144,
            think=True,
        )
        assert body == {"think": True, "options": {"num_ctx": 262144}}

    def test_latest_tag_model_sets_think(self) -> None:
        # `:latest` ist ein Ollama-Signal in der SSoT (mode="oasis"), war aber
        # in der alten lokalen Heuristik kein Treffer.
        body = build_camel_extra_body(
            model="qwen3-coder:latest",
            base_url="https://ollama.com/v1",
            num_ctx=None,
            think=False,
        )
        assert body == {"think": False}

    def test_is_ollama_route_matches_ssot_oasis_vocabulary(self) -> None:
        # Duenner Wrapper: True genau dann, wenn die SSoT "ollama" liefert.
        assert _is_ollama_route("gpt-oss:120b", "https://ollama.com/v1") is True
        assert _is_ollama_route("qwen3-coder", "http://localhost:11434/v1") is True
        assert _is_ollama_route("qwen3-coder-next:cloud", "https://x/v1") is True
        assert _is_ollama_route("qwen3-coder:latest", "https://x/v1") is True
        assert _is_ollama_route("gpt-5.4-mini", "https://api.openai.com/v1") is False


class TestBuildCamelExtraBodyProdCharacterization:
    """Charakterisierung der realen Prod-Route (ALE-19 → #670-Fix, ALE-17).

    Vor #670 fror diese Klasse das Bug-Verhalten ein: `gpt-oss:20b-cloud` @
    `:11435` traegt zwar keinen `:cloud`-Suffix (Tag ist `20b-cloud`) und
    keinen Port `:11434` — die Detection lieferte `openai`, das Gate blieb aus,
    Simulationsinhalte liefen ohne `think`/`num_ctx`.

    Seit #670 (Board-Entscheidung E1 = accept-cloud) erkennt
    `_is_ollama_cloud_tag` das `:<size>-cloud`-Tag als Ollama-Cloud-Signal →
    Prod-Route ist `ollama`, das Gate feuert.
    """

    def test_prod_route_gate_now_fires(self) -> None:
        body = build_camel_extra_body(
            model="gpt-oss:20b-cloud",
            base_url="http://127.0.0.1:11435/v1",
            num_ctx=131072,
            think=True,
        )
        assert body == {"think": True, "options": {"num_ctx": 131072}}

    def test_prod_route_is_ollama_route_true(self) -> None:
        assert _is_ollama_route("gpt-oss:20b-cloud", "http://127.0.0.1:11435/v1") is True


class TestBuildCamelExtraBodyMinimaxM3:
    """Charakterisierung fuer `minimax-m3` (Ollama-Cloud-Modell, ALE-19-Kommentar
    2026-07-06). Belegt, wie die SSoT-Delegation das Modell je nach Adressierung
    einordnet — insbesondere den #670-Gewinn (bare tag @ ollama.com) und die
    Kehrseite (bare tag @ lokaler Proxy `:11435` → Gate aus, wie die eingefrorene
    Prod-Route).
    """

    def test_minimax_m3_via_ollama_com_sets_think(self) -> None:
        # #670-Fix mit realem Modell: bare `minimax-m3` (kein :cloud) @ ollama.com
        # → SSoT erkennt `ollama.com` in der URL → Gate an.
        body = build_camel_extra_body(
            model="minimax-m3",
            base_url="https://ollama.com/v1",
            num_ctx=262144,
            think=True,
        )
        assert body == {"think": True, "options": {"num_ctx": 262144}}

    def test_minimax_m3_cloud_suffix_sets_think(self) -> None:
        body = build_camel_extra_body(
            model="minimax-m3:cloud",
            base_url="http://127.0.0.1:11435/v1",
            num_ctx=262144,
            think=False,
        )
        assert body == {"think": False, "options": {"num_ctx": 262144}}

    def test_minimax_m3_bare_on_local_proxy_gate_off(self) -> None:
        # Caveat: bare `minimax-m3` @ `:11435` (weder Cloud-Tag noch :11434 noch
        # ollama.com) → SSoT liefert "openai" → Gate aus. Anders als die
        # `:<size>-cloud`-Prod-Route (seit #670 erkannt) fehlt hier jedes
        # Ollama-Signal; fuer num_ctx/think muss ein Cloud-Tag/`:11434`/`ollama.com` her.
        body = build_camel_extra_body(
            model="minimax-m3",
            base_url="http://127.0.0.1:11435/v1",
            num_ctx=262144,
            think=True,
        )
        assert body == {}


class TestBuildCamelExtraBodyOllamaCloudModelAgnostic:
    """ALE-19-Kommentar 2026-07-06: Alex' Setup ist base_url `https://ollama.com/v1`
    + `ollama pull <modell>:cloud`. Beleg, dass der #670-Fix modell-agnostisch ist:
    ueber die `ollama.com`-URL routet JEDES Cloud-Modell (unabhaengig vom Tag,
    `:cloud` wie `-cloud`) zu Ollama → Gate an. Damit greifen alle 30+ Cloud-Modelle,
    nicht nur ein einzelnes.
    """

    _OLLAMA_COM = "https://ollama.com/v1"

    @pytest.mark.parametrize(
        "model",
        [
            "minimax-m3:cloud",
            "qwen3-coder:480b-cloud",
            "deepseek-v3.1:671b-cloud",
            "kimi-k2:1t-cloud",
            "glm-4.6:cloud",
            "minimax-m3",  # bare tag — greift allein ueber die ollama.com-URL (#670)
        ],
    )
    def test_any_cloud_model_via_ollama_com_sets_think(self, model: str) -> None:
        assert _is_ollama_route(model, self._OLLAMA_COM) is True
        body = build_camel_extra_body(
            model=model, base_url=self._OLLAMA_COM, num_ctx=262144, think=True
        )
        assert body == {"think": True, "options": {"num_ctx": 262144}}


class TestBuildMinimaxExtraBody:
    """MiniMax-eigene API (`api.minimax.io`) — Thinking-Steuerung per OpenAI-
    Compat-Spec (`thinking.type` ∈ {"disabled","adaptive"}). `disabled` schaltet
    Reasoning bei MiniMax-M3 ab; M2.x ignorieren es (Thinking bleibt an, aber der
    Parameter ist gueltig → kein 400). NUR fuer MiniMax-Routen — andere
    OpenAI-Compat-Provider kennen `thinking` nicht.

    Abgrenzung: `minimax-m3` (lowercase) @ `ollama.com` ist ein via Ollama Cloud
    bereitgestelltes Modell (siehe TestBuildCamelExtraBodyMinimaxM3) — NICHT die
    hier adressierte MiniMax-Plattform `api.minimax.io`.
    """

    _MINIMAX = "https://api.minimax.io/v1"

    def test_m3_think_off_sets_disabled(self) -> None:
        body = build_minimax_extra_body(
            model="MiniMax-M3", base_url=self._MINIMAX, think=False
        )
        assert body == {"thinking": {"type": "disabled"}}

    def test_m3_think_on_sets_adaptive(self) -> None:
        """Verify that enabling thinking for MiniMax-M3 produces adaptive thinking configuration."""
        body = build_minimax_extra_body(
            model="MiniMax-M3", base_url=self._MINIMAX, think=True
        )
        assert body == {"thinking": {"type": "adaptive"}}

    def test_highspeed_m2x_still_sends_disabled_param(self) -> None:
        # M2.x ignorieren `disabled` (Thinking bleibt an), aber der Parameter ist
        # laut Spec gueltig — wir senden ihn konsistent fuer alle MiniMax-Modelle.
        body = build_minimax_extra_body(
            model="MiniMax-M2.5-highspeed", base_url=self._MINIMAX, think=False
        )
        assert body == {"thinking": {"type": "disabled"}}

    def test_non_minimax_openai_returns_empty(self) -> None:
        # OpenAI-Direct kennt `thinking` nicht → 400. Builder muss leer liefern.
        body = build_minimax_extra_body(
            model="gpt-5.4-mini", base_url="https://api.openai.com/v1", think=False
        )
        assert body == {}

    def test_ollama_route_returns_empty(self) -> None:
        body = build_minimax_extra_body(
            model="qwen3-coder", base_url="http://localhost:11434/v1", think=False
        )
        assert body == {}

    def test_is_minimax_route_matches_hostname(self) -> None:
        assert _is_minimax_route("MiniMax-M3", self._MINIMAX) is True
        assert _is_minimax_route("MiniMax-M2.5-highspeed", "https://api.minimax.io/anthropic") is True
        assert _is_minimax_route("gpt-5.4-mini", "https://api.openai.com/v1") is False
        # `minimax-m3` @ ollama.com ist Ollama-Cloud, NICHT die MiniMax-Plattform.
        assert _is_minimax_route("minimax-m3", "https://ollama.com/v1") is False
