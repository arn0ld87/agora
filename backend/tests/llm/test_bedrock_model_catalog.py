"""Bedrock-Presets muessen ueber die Default-Region wirklich chatten (#1282).

Hintergrund (Defekt vom 2026-08-13). Der Bedrock-Connection-Eintrag stand auf
``bedrock-mantle.eu-central-1.api.aws/v1``, die sechs Modell-Presets waren aber
gegen ``us-east-1`` kuratiert. Zwei Schichten lagen uebereinander:

1. Regionaler Katalog. eu-central-1 fuehrt 33 Modelle, us-east-1 fuehrt 55.
   Fuenf der sechs Presets existierten in der Default-Region nicht, jeder
   Chat-Call endete in ``404 The model 'openai.gpt-5.6-luna' does not exist``.
2. Katalog-Praesenz ist nicht Chat-Faehigkeit. Nach Umstellung auf us-east-1
   existierten alle sechs IDs — und schlugen trotzdem fehl, mit ``400 The model
   '<id>' does not support the '/v1/chat/completions' API``. Der mantle-Pfad
   bedient in us-east-1 nur 38 seiner 55 Modelle ueber Chat-Completions; die
   gesamte ``anthropic.*``-Familie und alle ``openai.gpt-5.x`` lehnen sowohl
   ``/v1/chat/completions`` als auch ``/v1/responses`` ab. Sie sind ueber den
   OpenAI-kompatiblen Pfad prinzipiell unerreichbar und brauchen die native
   Converse/InvokeModel-API mit SigV4.

Auth, Base-URL-Kanonisierung, Adapter-Routing und ``GET /v1/models`` waren die
ganze Zeit korrekt — der Defekt sass ausschliesslich in der Modell-Liste.

Zwei Seams, weil keiner allein reicht:

* :func:`test_presets_match_registry_fallback_models` haelt die beiden
  handgepflegten Listen (``Config.LLM_MODEL_PRESETS`` und
  ``ProviderConnectionDefinition.fallback_models``) deckungsgleich. Laeuft
  offline, faengt aber nur Drift ZWISCHEN den Listen.
* :func:`test_presets_are_chat_capable_in_default_region` ist der eigentliche
  Riegel. Er probt jedes Preset mit einem echten Chat-Call gegen die
  Default-Region. Ein reiner Katalog-Abgleich haette Schicht 2 durchgelassen,
  und ``GET /v1/models`` liefert kein Capability-Feld, das man offline
  auswerten koennte — die Faehigkeit ist nur beobachtbar, nicht ableitbar.
  Deshalb ``@pytest.mark.llm`` (``pytest -m llm``) und Skip ohne Credential.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import pytest

from app.config import Config
from app.services.llm_provider_registry import (
    LlmProviderRegistry,
    ProviderConnectionDefinition,
)

BEDROCK_PROVIDER_ID = "bedrock"

# Statuscodes, die nichts ueber die Chat-Faehigkeit des Modells aussagen und
# deshalb einen zweiten Versuch bekommen. 5xx wird zusaetzlich generisch
# behandelt (siehe :func:`_chat_probe`).
_TRANSIENT_STATUS = frozenset({408, 429})


def _bedrock_definition() -> ProviderConnectionDefinition:
    definition = LlmProviderRegistry.connection_definition(BEDROCK_PROVIDER_ID)
    assert definition is not None, "Bedrock-Provider fehlt in der Connection-Matrix"
    return definition


def _preset_ids() -> set[str]:
    return {
        preset["name"]
        for preset in (Config.LLM_MODEL_PRESETS or [])
        if preset.get("kind") == BEDROCK_PROVIDER_ID
    }


def test_presets_match_registry_fallback_models() -> None:
    """Beide handgepflegten Bedrock-Modell-Listen bleiben deckungsgleich."""
    descriptor = _bedrock_definition()
    assert _preset_ids() == set(descriptor.fallback_models or ()), (
        "Config.LLM_MODEL_PRESETS (kind=bedrock) und die fallback_models des "
        "Bedrock-Connection-Eintrags sind auseinandergelaufen. Beide Listen "
        "sind an die Default-Region gekoppelt und werden gemeinsam gepflegt."
    )


def _chat_probe(base_url: str, api_key: str, model: str, *, attempts: int = 2) -> str | None:
    """Minimaler Chat-Call. Gibt ``None`` bei Erfolg zurueck, sonst den Fehler.

    Drei Klassen, bewusst unterschiedlich behandelt:

    * **Capability-Fehler** (``404`` Modell existiert nicht, ``400`` Route wird
      nicht bedient) — die gesuchte Fehlerklasse. Sofort melden, nicht
      wiederholen; ein Retry wuerde den Testlauf nur verlangsamen.
    * **Transiente Serverantworten** (``429`` Throttling, ``5xx``) — hier laufen
      sechs Probes gleichzeitig, Throttling ist realistisch. Wiederholen: sonst
      meldet der Test ein gedrosseltes Modell als „nicht chat-faehig“ und
      erzeugt exakt den falschen Befund, den er verhindern soll.
    * **Transport-Timeouts** — meist Cold-Start des Modells auf mantle.
      Wiederholen, damit der Test nicht an Anlaufzeit scheitert statt an einem
      echten Defekt.
    """
    body = json.dumps(
        {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
    ).encode()
    last_error = "nicht ausgefuehrt"
    for _ in range(attempts):
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60):  # noqa: S310
                return None
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read())["error"]["message"]
            except Exception:  # noqa: BLE001 — Fehlertext ist best effort
                detail = f"HTTP {exc.code}"
            message = f"HTTP {exc.code}: {detail}"
            if exc.code not in _TRANSIENT_STATUS and exc.code < 500:
                return message
            last_error = message
        except Exception as exc:  # noqa: BLE001 — Netzfehler ist Testergebnis
            last_error = f"{type(exc).__name__}: {exc}"
    return last_error


@pytest.mark.llm
def test_presets_are_chat_capable_in_default_region() -> None:
    """Jedes Preset beantwortet einen echten Chat-Call in der Default-Region.

    Der Test, der den Defekt trifft, und zwar in beiden Schichten: gegen die
    urspruengliche Kombination (eu-central-1 + us-east-1-Presets) faellt er mit
    ``404 does not exist``, gegen us-east-1 mit denselben Presets mit ``400 does
    not support the '/v1/chat/completions' API``. Ein reiner Katalog-Abgleich
    haette nur die erste Schicht gesehen.
    """
    # Nur aus dem Env: ``conftest.py`` zeigt ``AGORA_DATA_DIR`` je Test auf
    # ``tmp_path``, der echte Secrets-Store ist unter pytest also nie sichtbar.
    api_key = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    if not api_key:
        pytest.skip("Kein AWS_BEARER_TOKEN_BEDROCK im Env gesetzt")

    base_url = _bedrock_definition().default_base_url
    assert base_url, "Bedrock-Eintrag ohne default_base_url"

    presets = sorted(_preset_ids())
    probe = partial(_chat_probe, base_url, api_key)
    with ThreadPoolExecutor(max_workers=len(presets)) as pool:
        errors = {
            model: error
            for model, error in zip(presets, pool.map(probe, presets))
            if error
        }

    assert not errors, (
        f"Diese Presets sind ueber {base_url} nicht chat-faehig:\n"
        + "\n".join(f"  {model}: {error}" for model, error in sorted(errors.items()))
        + "\nEntweder die Default-Region oder die Preset-Liste ist falsch. "
        "Beachte: im Katalog stehen heisst nicht, dass /v1/chat/completions "
        "bedient wird — anthropic.* und openai.gpt-5.x tun es nie."
    )
