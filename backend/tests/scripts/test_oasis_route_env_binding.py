"""Regressionstest für den OASIS-404 ``model 'MiniMax-M3' not found`` (Folge
von #852): Eine aufgelöste Route, die nur eine Registry-``provider_id`` trägt
(Legacy-/Workspace-Default-Pfad ohne ``ai_model_ref``), darf im
OASIS-Subprozess NICHT auf ein stale ``LLM_BASE_URL`` aus dem Parent-Env
zurückfallen. ``build_route_subprocess_env`` muss die Base-URL derselben
``provider_id`` aus der Provider-Registry auflösen — symmetrisch zur
Key-Auflösung in ``resolve_route_api_key`` und zum HTTP-Pfad
(``LLMClient.from_route``).

Seam (vorab freigegeben): der reale OASIS/CAMEL-Provider-Completion-Pfad mit
einer aufgelösten Route — ``build_route_subprocess_env`` → Env-Merge wie in
``process_manager.start_simulation`` → ``create_model`` →
``preflight_model_probe``. CAMEL führt einen echten HTTP-Roundtrip gegen
lokale Stub-Server aus; ``ModelFactory`` wird nicht gemockt.

Die Eingabe-Route entspricht exakt dem gelockten Snapshot des realen
Fehlerruns (``run_739d2293df07``): ``provider_id`` gesetzt,
``base_url_sanitized=None``, ``provider_options={}``.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Iterator

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
_TESTS_DIR = Path(__file__).resolve().parent
for _p in (_SCRIPTS_DIR, _TESTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from app.contracts.llm_routing_contract import ResolvedRoute  # noqa: E402
from app.services.llm_routing_seed import build_route_subprocess_env  # noqa: E402
from app.services.sim.process_manager import SAFE_ENV_KEYS  # noqa: E402
from _crash_skip import skipif_py314_aarch64  # noqa: E402

MODEL_ID = "MiniMax-M3"


class _StubHandler(BaseHTTPRequestHandler):
    """OpenAI-kompatibler Chat-Completions-Stub.

    ``server.mode == "stale"`` antwortet wie der falsche Endpoint des
    Prod-Fehlers (Ollama-404 ``model not found``), ``"provider"`` wie der
    korrekte Provider-Endpoint (200 mit gültiger Completion).
    """

    def do_POST(self) -> None:  # noqa: N802 — http.server-API
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        self.server.hits += 1  # type: ignore[attr-defined]
        if self.server.mode == "stale":  # type: ignore[attr-defined]
            body = json.dumps(
                {
                    "error": {
                        "message": f"model '{MODEL_ID}' not found",
                        "type": "not_found_error",
                        "param": None,
                        "code": None,
                    }
                }
            ).encode()
            self.send_response(404)
        else:
            body = json.dumps(
                {
                    "id": "chatcmpl-stub-1",
                    "object": "chat.completion",
                    "created": 0,
                    "model": MODEL_ID,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "OK"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                }
            ).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # noqa: D102 — still
        pass


@pytest.fixture()
def stub_servers() -> Iterator[tuple[HTTPServer, HTTPServer]]:
    """Startet die beiden Stub-Server (stale + provider) auf freien Ports."""
    servers = []
    for mode in ("stale", "provider"):
        server = HTTPServer(("127.0.0.1", 0), _StubHandler)
        server.mode = mode  # type: ignore[attr-defined]
        server.hits = 0  # type: ignore[attr-defined]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
    yield servers[0], servers[1]
    for server in servers:
        server.shutdown()
        server.server_close()


@skipif_py314_aarch64
def test_registry_provider_route_reaches_provider_endpoint_not_stale_env(
    stub_servers: tuple[HTTPServer, HTTPServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route mit Registry-``provider_id`` ohne ``base_url_sanitized`` muss den
    Registry-Endpoint der Provider-ID treffen — nicht das geerbte
    ``LLM_BASE_URL`` des Backend-Prozesses (Root Cause des Prod-404)."""
    stale, provider = stub_servers
    stale_url = f"http://127.0.0.1:{stale.server_address[1]}/v1"
    provider_url = f"http://127.0.0.1:{provider.server_address[1]}/v1"

    # Registry-Descriptor der provider_id — Konfigurationsquelle des Tests,
    # analog zu den Store-Mocks in test_llm_routing_seed.py.
    class _Descriptor:
        id = "stub-prov"
        type = "openai_compatible"
        base_url = provider_url
        api_key_ref = None

    class _Registry:
        def get_providers(self) -> list[_Descriptor]:
            return [_Descriptor()]

    monkeypatch.setattr(
        "app.services.llm_routing_seed.LlmProviderRegistry", _Registry
    )

    # Route exakt wie der gelockte Prod-Snapshot: provider_id, kein base_url.
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="stub-prov",
        model=MODEL_ID,
        base_url_sanitized=None,
        routing_version=1,
    )
    runtime_env = build_route_subprocess_env(
        route, "unit-test-dummy-value", run_id="run_env_binding_test"
    )

    # Parent-Env des Backend-Containers: stale LLM_BASE_URL aus .env.
    parent_env = {"LLM_BASE_URL": stale_url, "LLM_MODEL_NAME": "gpt-oss:20b-cloud"}
    # Merge exakt wie process_manager.start_simulation: Whitelist-Parent-Env,
    # dann runtime_env (nur nicht-leere Werte) darüber.
    merged = {k: v for k, v in parent_env.items() if k in SAFE_ENV_KEYS}
    merged.update({k: v for k, v in runtime_env.items() if v})

    for key in (
        "LLM_BASE_URL",
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
        "OPENAI_API_BASE_URL",
        "LLM_MODEL_NAME",
        "LLM_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in merged.items():
        monkeypatch.setenv(key, value)

    from _sim_common import preflight_model_probe
    from run_parallel_simulation import create_model

    model = create_model({"llm_model": MODEL_ID}, use_boost=False)

    # Realer CAMEL-HTTP-Roundtrip: Vor dem Fix trifft er den stale-Stub und
    # der Preflight lehnt mit dem Prod-404 ab; nach dem Fix antwortet der
    # Provider-Stub mit 200.
    preflight_model_probe(model, max_retries=0)

    assert provider.hits == 1, (  # type: ignore[attr-defined]
        "Der Completion-Call muss den Endpoint der Registry-provider_id treffen"
    )
    assert stale.hits == 0, (  # type: ignore[attr-defined]
        "Der Completion-Call darf nicht auf das stale Parent-LLM_BASE_URL "
        "zurückfallen (Root Cause des OASIS-404)"
    )
