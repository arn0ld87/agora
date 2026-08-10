"""Issue #1176 — ein registrierter Run bleibt nie auf ``pending`` stehen.

`POST /api/simulation/start` legt in Phase 5 (`_register_start_run`) einen
Run-Record mit `status="pending"` an. Bricht der Handler danach ab, ohne den
Record auf einen Endzustand zu bringen, entsteht ein Phantom-Run: er steht
dauerhaft in der Run-Liste, das Frontend zeigt weiter „Bereit", und
`POST /api/runs/<id>/cancel` greift bei ihm nicht — die Route ließ nur
`processing` zu. Im gemeldeten Fall hatten sich neun solcher Runs angesammelt.

#1094 hatte zwei bekannte Abbruchpfade einzeln als `failed` markiert. Das
deckte die Fehlerklasse nicht ab: `SimulationRunner.start_simulation` lag ganz
außerhalb des `try`, und jeder künftige Abbruchpfad hätte dieselbe Lücke wieder
aufgerissen.

Die Tests fahren deshalb den echten Endpunkt und lassen ihn an **verschiedenen**
Stellen nach der Registrierung scheitern. Geprüft wird, was danach in der
Run-Registry steht — nicht, wie der Handler aufgebaut ist.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp
from app.contracts.llm_routing_contract import ResolvedRoute

VALID_SIM_ID = "sim_0123456789ab"
RUN_ID = "run_1176aabbccdd"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.config["TESTING"] = True
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    with app.test_request_context(), app.test_client() as test_client:
        yield test_client


def _stub_start_infra(monkeypatch) -> MagicMock:
    """Stubbt die Sim-Infrastruktur bis einschließlich Run-Registrierung.

    Gibt die Registry-Attrappe zurück — an ihr wird geprüft, in welchem
    Zustand der Run nach dem Abbruch steht.
    """
    from app.services.simulation_manager import SimulationStatus

    state = MagicMock()
    state.status = SimulationStatus.READY
    state.project_id = "proj-x"
    state.graph_id = None
    state.branch_name = None
    state.source_simulation_id = None
    state.root_simulation_id = None
    state.branch_depth = 0
    manager = MagicMock(get_simulation=MagicMock(return_value=state))
    monkeypatch.setattr("app.api.simulation_run.SimulationManager", lambda: manager)

    registry = MagicMock()
    registry.create_run.return_value = {"run_id": RUN_ID}
    monkeypatch.setattr("app.api.simulation_run.run_registry", registry)
    monkeypatch.setattr("app.api.simulation_run.seed_run_stage_routing", MagicMock())
    monkeypatch.setattr("app.api.simulation_run._apply_budget_to_simulation", MagicMock())
    monkeypatch.setattr("app.api.simulation_run._simulation_run_artifacts", lambda _s: [])
    monkeypatch.setattr(
        "app.api.simulation_run._simulation_resume_capability",
        lambda _s, _st: {"resumable": False},
    )
    monkeypatch.setattr(
        "app.api.simulation_run.Config.PERSONA_REVIEW_ENABLED", False, raising=False
    )
    monkeypatch.setattr(
        "app.api.simulation_run._check_simulation_prepared", lambda _sid: (True, {})
    )

    resolved = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="conn-local",
        model="qwen3",
        base_url_sanitized="http://localhost:1234/v1",
        routing_version=1,
        provider_options={"base_url": "http://localhost:1234/v1"},
    )
    router = MagicMock()
    router.resolve.return_value = resolved
    router.lock_stage.return_value = resolved
    monkeypatch.setattr("app.api.simulation_run.StageModelRouter", lambda _rid: router)
    monkeypatch.setattr(
        "app.api.simulation_run.resolve_route_api_key", lambda _r, _rt: "sk-local"
    )
    monkeypatch.setattr(
        "app.api.simulation_run.build_route_subprocess_env", lambda _r, _k, _rid: {}
    )
    monkeypatch.setattr("app.api.simulation_run.get_artifact_store", lambda: MagicMock())
    monkeypatch.setattr(
        "app.api.simulation_common.get_artifact_store", lambda: MagicMock(), raising=False
    )

    runner = MagicMock()
    runner.start_simulation.return_value = MagicMock(
        to_dict=MagicMock(return_value={"simulation_id": VALID_SIM_ID})
    )
    monkeypatch.setattr("app.api.simulation_run.SimulationRunner", runner)
    return registry


def _final_status(registry: MagicMock) -> str | None:
    """Letzter an ``update_run`` übergebener Status."""
    for call in reversed(registry.update_run.call_args_list):
        if "status" in call.kwargs:
            return call.kwargs["status"]
    return None


def _start(client):
    return client.post(
        "/api/simulation/start",
        json={"simulation_id": VALID_SIM_ID, "platform": "parallel"},
    )


def test_der_normalfall_bringt_den_run_auf_processing(client, monkeypatch) -> None:
    """Gegenprobe: das Auffangnetz darf den erfolgreichen Start nicht stören."""
    registry = _stub_start_infra(monkeypatch)

    response = _start(client)

    assert response.status_code == 200, response.data
    assert _final_status(registry) == "processing"


class TestFailureAfterRegistrationEndsTheRun:
    """Der Kern von #1176 — geprüft wird die Fehlerklasse, nicht ein Pfad."""

    def test_ein_fehler_beim_prozessstart_hinterlaesst_keinen_pending_run(
        self, client, monkeypatch
    ) -> None:
        """Der Pfad, der die neun Phantom-Runs erzeugt hat.

        ``SimulationRunner.start_simulation`` lag vor diesem Slice außerhalb des
        ``try``. Eine Exception dort erreichte nur ``@handle_api_errors`` — die
        loggt und antwortet 500, lässt den Run aber auf ``pending``.
        """
        registry = _stub_start_infra(monkeypatch)
        runner = MagicMock()
        runner.start_simulation.side_effect = RuntimeError("Subprozess nicht startbar")
        monkeypatch.setattr("app.api.simulation_run.SimulationRunner", runner)

        response = _start(client)

        assert response.status_code >= 500
        assert _final_status(registry) == "failed"

    def test_ein_haengender_start_hinterlaesst_keinen_pending_run(
        self, client, monkeypatch
    ) -> None:
        """Der wahrscheinlichste Fall laut Issue: der Request hängt, statt zu
        scheitern, und der Worker bricht ihn ab.

        Ein Worker-Timeout erreicht den Handler als ``SystemExit`` — eine
        ``BaseException``, keine ``Exception``. Ein ``except Exception`` hätte
        sie durchgelassen und genau diesen Fall offen gelassen.
        """
        registry = _stub_start_infra(monkeypatch)
        runner = MagicMock()
        runner.start_simulation.side_effect = SystemExit("worker timeout")
        monkeypatch.setattr("app.api.simulation_run.SimulationRunner", runner)

        with pytest.raises(SystemExit):
            _start(client)

        assert _final_status(registry) == "failed", (
            "Ein abgewuergter Request hinterlaesst weiterhin einen Phantom-Run"
        )

    def test_ein_fehler_beim_routing_hinterlaesst_keinen_pending_run(
        self, client, monkeypatch
    ) -> None:
        registry = _stub_start_infra(monkeypatch)
        router = MagicMock()
        router.resolve.side_effect = RuntimeError("Router nicht erreichbar")
        monkeypatch.setattr("app.api.simulation_run.StageModelRouter", lambda _r: router)

        response = _start(client)

        assert response.status_code >= 500
        assert _final_status(registry) == "failed"

    def test_ein_fehlender_api_key_hinterlaesst_keinen_pending_run(
        self, client, monkeypatch
    ) -> None:
        """Der bekannte 422-Pfad aus #1094 — die Markierung liegt jetzt im Netz,
        nicht mehr einzeln in ``_resolve_start_route``."""
        registry = _stub_start_infra(monkeypatch)
        remote = ResolvedRoute(
            stage="simulation_rounds",
            provider_id="conn-openai",
            model="gpt-4o",
            base_url_sanitized="https://api.openai.com/v1",
            routing_version=1,
            provider_options={"base_url": "https://api.openai.com/v1"},
        )
        router = MagicMock()
        router.resolve.return_value = remote
        router.lock_stage.return_value = remote
        monkeypatch.setattr("app.api.simulation_run.StageModelRouter", lambda _r: router)
        monkeypatch.setattr(
            "app.api.simulation_run.resolve_route_api_key", lambda _r, _rt: None
        )

        response = _start(client)

        assert response.status_code == 422, response.data
        assert _final_status(registry) == "failed"

    def test_ein_fehler_beim_config_schreiben_hinterlaesst_keinen_pending_run(
        self, client, monkeypatch
    ) -> None:
        registry = _stub_start_infra(monkeypatch)
        monkeypatch.setattr(
            "app.api.simulation_run._apply_route_to_simulation_config",
            MagicMock(side_effect=OSError("Konfiguration nicht schreibbar")),
        )

        response = _start(client)

        assert response.status_code >= 500
        assert _final_status(registry) == "failed"


class TestPersistenzfehlerBeimMarkierenWirdSichtbar:
    def test_ein_persistenzfehler_ersetzt_die_ablehnung_durch_500(
        self, client, monkeypatch
    ) -> None:
        """Issue #844, vereinheitlicht auf die strenge Semantik.

        Früher schluckte ``_mark_run_failed`` Registry-Fehler best-effort —
        der Client bekam die reguläre Ablehnung (hier: 422), obwohl der Run
        weiter ``pending`` in der Registry stand. Jetzt gilt der Prepare-Weg
        auch beim Start: eine nicht persistierte failed-Markierung darf nicht
        wie eine sauber abgeschlossene Ablehnung aussehen — der Handler
        antwortet 500.
        """
        registry = _stub_start_infra(monkeypatch)
        registry.update_run.side_effect = OSError("Registry nicht schreibbar")
        remote = ResolvedRoute(
            stage="simulation_rounds",
            provider_id="conn-openai",
            model="gpt-4o",
            base_url_sanitized="https://api.openai.com/v1",
            routing_version=1,
            provider_options={"base_url": "https://api.openai.com/v1"},
        )
        router = MagicMock()
        router.resolve.return_value = remote
        router.lock_stage.return_value = remote
        monkeypatch.setattr("app.api.simulation_run.StageModelRouter", lambda _r: router)
        monkeypatch.setattr(
            "app.api.simulation_run.resolve_route_api_key", lambda _r, _rt: None
        )

        response = _start(client)

        assert response.status_code == 500, response.data
        registry.update_run.assert_called()
