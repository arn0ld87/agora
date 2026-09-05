"""Regressionstests für zwei stille Provider-Vertauschungen im Prepare-/OASIS-Pfad.

Beide Defekte teilen ein Fehlerbild: der in der UI konfigurierte Provider
erreicht den Konsumenten nicht, und niemand sagt es.

**Defekt A — der Store wird ignoriert.**
``LlmProviderRegistry.get_providers()`` liefert laut eigenem Docstring
ausschliesslich *statische, secret-freie* Metadaten: den hartkodierten
``definition.default_base_url``. ``build_route_subprocess_env`` fiel direkt
darauf zurueck, sobald die Route selbst keine ``base_url_sanitized`` trug — der
Legacy-/Workspace-Default-Pfad ohne ``ai_model_ref`` erzeugt genau solche
Routen. Eine in der UI gepflegte abweichende Base-URL landete zwar in
``provider_connections.json``, aber nie im OASIS-Subprozess. Aus Nutzersicht:
das Eingabefeld nimmt die Korrektur an und der Lauf ignoriert sie.

**Defekt C — die Halb-Uebergabe.**
``_resolve_llm_connection`` gab bei nicht aufloesbarer Route ``(None, None)``
zurueck, waehrend ``model_name`` aus der Route weitergereicht wurde.
``OasisProfileGenerator.__init__`` fuellte die Luecke aus ``Config.LLM_BASE_URL``
und ``Config.LLM_API_KEY``. Ergebnis war Modell aus der Route, Endpoint und Key
aus der ``.env`` — beobachtet als ``deepseek-v4-flash:0731`` gegen
``https://api.minimax.io/v1`` mit HTTP 401. Der Lauf meldete trotzdem
"30 Personas erfolgreich generiert", weil jeder Einzelfehler still auf
``rule-based generation`` zurueckfiel.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.contracts.llm_routing_contract import ResolvedRoute
from app.services import llm_routing_seed
from app.services.prepare_service import _resolve_llm_connection


def _route(provider_id: str, *, base_url: str | None = None) -> ResolvedRoute:
    """Route wie im Legacy-/Workspace-Default-Pfad: provider_id ohne base_url."""
    return ResolvedRoute(
        stage="persona_generation",
        provider_id=provider_id,
        model="deepseek-v4-flash:0731",
        base_url_sanitized=base_url,
        routing_version=1,
    )


class _StubConnection:
    """Minimaler Stand-in fuer ``ProviderConnection``.

    Bewusst kein echtes Contract-Objekt: ``ProviderConnection`` validiert
    ``base_url`` provider-abhaengig, was hier nur Rauschen waere. Getestet wird
    die Praezedenz in ``build_route_subprocess_env``, nicht die Store-Validierung.
    """

    def __init__(
        self, connection_id: str, provider_kind: str, base_url: str | None, enabled: bool = True
    ) -> None:
        self.id = connection_id
        self.provider_kind = provider_kind
        self.base_url = base_url
        self.enabled = enabled


def _patch_store(monkeypatch: pytest.MonkeyPatch, connections: list[Any]) -> None:
    class _StubStore:
        def list_connections(self) -> list[Any]:
            return connections

    monkeypatch.setattr(llm_routing_seed, "ProviderConnectionStore", _StubStore)


class TestStoreBaseUrlBeatsRegistryDefault:
    """Defekt A: die gepflegte Connection-URL schlaegt den hartkodierten Default."""

    def test_store_base_url_wins_over_registry_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Der Kern des Defekts: Registry-Default ``https://ollama.com``, Store
        ``https://ollama.com/v1`` — im Subprozess-Env muss der Store-Wert stehen.
        """
        _patch_store(
            monkeypatch,
            [_StubConnection("ollama_cloud", "ollama_cloud", "https://ollama.com/v1")],
        )

        env = llm_routing_seed.build_route_subprocess_env(
            _route("ollama_cloud"), api_key="k"
        )

        assert env["LLM_BASE_URL"] == "https://ollama.com/v1"
        assert env["OPENAI_BASE_URL"] == "https://ollama.com/v1"

    def test_route_base_url_still_wins_over_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Praezedenz bleibt Route > Store > Registry-Default.

        Eine Route mit eigener ``base_url_sanitized`` stammt aus einem
        expliziten ``ai_model_ref`` und ist spezifischer als der Store-Default
        des Providers — dieser Vorrang darf durch Fix A nicht kippen.
        """
        _patch_store(
            monkeypatch,
            [_StubConnection("ollama_cloud", "ollama_cloud", "https://store.example/v1")],
        )

        env = llm_routing_seed.build_route_subprocess_env(
            _route("ollama_cloud", base_url="https://route.example/v1"), api_key="k"
        )

        assert env["LLM_BASE_URL"] == "https://route.example/v1"

    def test_disabled_connection_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Eine deaktivierte Connection darf keine Base-URL beisteuern."""
        _patch_store(
            monkeypatch,
            [
                _StubConnection(
                    "ollama_cloud", "ollama_cloud", "https://disabled.example/v1", enabled=False
                )
            ],
        )

        env = llm_routing_seed.build_route_subprocess_env(
            _route("ollama_cloud"), api_key="k"
        )

        assert env.get("LLM_BASE_URL") != "https://disabled.example/v1"

    def test_store_failure_does_not_break_the_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ein unlesbarer Store degradiert auf den Registry-Default statt zu werfen."""

        class _ExplodingStore:
            def list_connections(self) -> list[Any]:
                raise OSError("store unreadable")

        monkeypatch.setattr(llm_routing_seed, "ProviderConnectionStore", _ExplodingStore)

        env = llm_routing_seed.build_route_subprocess_env(
            _route("ollama_cloud"), api_key="k"
        )

        assert env["LLM_MODEL_NAME"] == "deepseek-v4-flash:0731"


class TestResolvedRouteFromAiRouteFillsBaseUrlFromStore:
    """#1104: ``workspace_llm_routing.json`` persistiert pro Route nur
    ``provider_id``/``model`` — keine ``base_url`` (die gehoert zur
    Provider-Connection). Ohne Store-Lookup blieb ``base_url_sanitized``
    ``None``, und ``OasisProfileGenerator`` fuellte die Luecke mit
    ``Config.LLM_BASE_URL`` (.env-Endpoint), waehrend Modell und Key aus der
    Route stammten — Nachfolge-Defekt von #1101/#1102, die nur den
    ``LLMClient``-Konstruktor fixten, nicht diesen kanonischen Routing-Pfad.
    """

    def test_store_base_url_fills_resolved_route(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_store(
            monkeypatch,
            [_StubConnection("openai", "openai", "https://store.example/openai/v1")],
        )
        from app.contracts.ai_provider_contract import AiRoute
        from app.services.stage_model_router import StageModelRouter

        route = AiRoute(
            provider_connection_id="openai",
            model_id="gpt-5.6-luna",
            source="workspace",
        )

        resolved = StageModelRouter(run_id="run-1")._resolved_route_from_ai_route(
            "persona_generation", route, 1
        )

        assert resolved.base_url_sanitized == "https://store.example/openai/v1"

    def test_route_provider_options_base_url_still_wins_over_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Praezedenz bleibt Route-Option > Store, analog zu Defekt A."""
        _patch_store(
            monkeypatch,
            [_StubConnection("openai", "openai", "https://store.example/openai/v1")],
        )
        from app.contracts.ai_provider_contract import AiRoute
        from app.services.stage_model_router import StageModelRouter

        route = AiRoute(
            provider_connection_id="openai",
            model_id="gpt-5.6-luna",
            source="workspace",
            provider_options={"base_url": "https://explicit.example/v1"},
        )

        resolved = StageModelRouter(run_id="run-1")._resolved_route_from_ai_route(
            "persona_generation", route, 1
        )

        assert resolved.base_url_sanitized == "https://explicit.example/v1"


class TestPrepareRequiresResolvedRoute:
    """Defekt C: keine Route → lauter Abbruch statt stiller ``.env``-Uebernahme."""

    def test_missing_route_raises_instead_of_returning_none(self) -> None:
        """Der Kern des Defekts: ``(None, None)`` war die Eintrittskarte fuer den
        ``.env``-Fallback im Generator-Konstruktor.
        """
        with pytest.raises(ValueError, match="kein LLM-Provider aufgelöst"):
            _resolve_llm_connection(None)

    def test_disabled_runtime_override_raises(self) -> None:
        """``provider="default"`` heisst "kein Override" — nicht "nimm die .env"."""
        from app.services.llm_runtime import RuntimeLlmConfig

        with pytest.raises(ValueError, match="kein LLM-Provider aufgelöst"):
            _resolve_llm_connection(RuntimeLlmConfig(provider="default"))

    def test_opt_out_returns_none_without_raising(self) -> None:
        """``use_llm_for_profiles=False`` ist ein legitimer Wunsch nach
        regelbasierter Generierung und darf nicht als Fehlkonfiguration gelten.
        """
        assert _resolve_llm_connection(None, require=False) == (None, None, None)

    def test_resolved_route_passes_through(self) -> None:
        """Der Normalfall bleibt unveraendert: Route liefert Key und Endpoint."""
        route = _route("ollama_cloud", base_url="https://ollama.com/v1")

        _, base_url, _ = _resolve_llm_connection(route)

        assert base_url == "https://ollama.com/v1"

    def test_resolved_route_without_base_url_raises(self) -> None:
        """#1104, zweite Verteidigungslinie: findet auch der Store-Lookup in
        ``StageModelRouter`` keine base_url (z. B. geloeschte/deaktivierte
        Connection), darf ``_resolve_llm_connection`` niemals still
        ``(key, None)`` zurueckgeben — das war die Eintrittskarte fuer den
        ``.env``-Fallback im Generator-Konstruktor.
        """
        route = _route("openai", base_url=None)

        with pytest.raises(ValueError, match="kein Endpoint"):
            _resolve_llm_connection(route)

    def test_resolved_route_without_base_url_and_require_false_does_not_raise(
        self,
    ) -> None:
        """``require=False`` bleibt wie bisher: kein Abbruch, nur kein Endpoint."""
        route = _route("openai", base_url=None)

        _, base_url, _ = _resolve_llm_connection(route, require=False)

        assert base_url is None


class TestResolveLlmConnectionCliTransport:
    """Defekt D (Issue #1418): ``codex_cli`` (transport="cli", #1405) hat by
    design weder ``base_url`` noch ``api_key`` — der #1104-Guard oben durfte
    das nie als "nicht aufgeloest" lesen, sonst greift exakt derselbe
    ``.env``-Fallback wie bei Defekt C, nur fuer einen Provider ohne
    HTTP-Endpoint (beobachtet: ``gpt-5.6-luna`` an ``https://api.minimax.io/v1``
    → HTTP 400 statt an den lokal eingeloggten ``codex``-Subprozess).
    """

    def test_resolved_route_cli_transport_without_base_url_does_not_raise(
        self,
    ) -> None:
        route = _route("codex_cli", base_url=None)

        api_key, base_url, provider_type = _resolve_llm_connection(route)

        assert base_url is None
        assert provider_type == "codex_cli"

    def test_resolved_route_http_transport_without_base_url_still_raises(
        self,
    ) -> None:
        """Gegenprobe: ein HTTP-Provider ohne base_url bleibt ein Fehler —
        die CLI-Ausnahme darf nicht versehentlich auf alle Provider zutreffen.
        """
        route = _route("openai", base_url=None)

        with pytest.raises(ValueError, match="kein Endpoint"):
            _resolve_llm_connection(route)

    def test_bridged_runtime_config_for_codex_cli_carries_provider_type(self) -> None:
        """Der Restart-/Legacy-Pfad bridged eine ``ResolvedRoute`` vorher in
        ``RuntimeLlmConfig`` (``build_runtime_llm_config``). Ohne einen
        eigenen ``_ROUTE_TO_RUNTIME_PROVIDER``-Eintrag fuer codex_cli landete
        die Route im generischen "custom_openai"-Bucket und der
        Provider-Typ ging in genau diesem Zweig verloren.
        """
        from app.services.llm_routing_seed import build_runtime_llm_config

        route = _route("codex_cli", base_url=None)
        runtime = build_runtime_llm_config(route, api_key=None)

        api_key, base_url, provider_type = _resolve_llm_connection(runtime)

        assert base_url is None
        assert provider_type == "codex_cli"
