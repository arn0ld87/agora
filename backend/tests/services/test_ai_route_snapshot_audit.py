import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.contracts.ai_provider_contract import AiRoute
from app.contracts.llm_routing_contract import ResolvedRoute
from app.services.ai_route_audit import AiRouteAudit
from app.services.runtime_run_config import RuntimeRunConfig
from app.services.stage_model_router import StageModelRouter


@pytest.fixture
def runtime(tmp_path):
    run_dir = tmp_path / "runs" / "run-snapshot"
    run_dir.mkdir(parents=True)
    with patch(
        "app.utils.artifact_locator.ArtifactLocator.run_dir",
        return_value=str(run_dir),
    ):
        yield RuntimeRunConfig("run-snapshot"), run_dir


def test_snapshot_first_writer_wins_and_loser_receives_winner(runtime):
    service, _ = runtime
    first = {"provider_id": "openai", "model": "gpt-4o"}
    second = {"provider_id": "google", "model": "gemini"}

    assert service.save_stage_snapshot("graph_build", first) == first
    assert service.save_stage_snapshot("graph_build", second) == first
    assert service.load_stage_snapshot("graph_build") == first


def test_failed_publication_is_retryable_and_never_exposes_partial_json(runtime, monkeypatch):
    service, run_dir = runtime
    real_link = os.link
    calls = 0

    def fail_once(source, target):
        nonlocal calls
        calls += 1
        if calls == 1:
            assert not os.path.exists(target)
            raise OSError("publication failed")
        return real_link(source, target)

    monkeypatch.setattr(os, "link", fail_once)
    with pytest.raises(OSError, match="publication failed"):
        service.save_stage_snapshot("graph_build", {"provider_id": "openai"})

    assert service.load_stage_snapshot("graph_build") is None
    winner = service.save_stage_snapshot("graph_build", {"provider_id": "google"})
    assert winner == {"provider_id": "google"}
    assert not list((run_dir / "stages").glob("*.tmp"))


def test_concurrent_snapshot_writers_observe_same_stored_winner(runtime):
    service, _ = runtime
    candidates = [{"provider_id": f"provider-{index}"} for index in range(8)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda candidate: service.save_stage_snapshot("graph_build", candidate),
                candidates,
            )
        )

    stored = service.load_stage_snapshot("graph_build")
    assert stored in candidates
    assert results == [stored] * len(candidates)


def test_ai_route_helpers_read_canonical_and_legacy_snapshots(runtime):
    service, _ = runtime
    canonical = AiRoute(
        stage="graph_build",
        provider_connection_id="connection-1",
        model_id="gpt-4o",
        source="stage_override",
    )
    assert service.save_ai_route_snapshot("graph_build", canonical) == canonical
    assert service.load_ai_route_snapshot("graph_build") == canonical

    legacy = {
        "stage": "simulation_rounds",
        "provider_id": "openai",
        "model": "gpt-4o-mini",
        "routing_version": 3,
    }
    service.save_stage_snapshot("simulation_rounds", legacy)
    converted = service.load_ai_route_snapshot("simulation_rounds")
    assert converted is not None
    assert converted.provider_connection_id == "openai"
    assert converted.model_id == "gpt-4o-mini"
    assert converted.source == "legacy"


def test_canonical_snapshot_is_read_through_resolved_route_adapter(runtime):
    service, _ = runtime
    service.save_ai_route_snapshot(
        "graph_build",
        AiRoute(
            stage="graph_build",
            provider_connection_id="connection-1",
            model_id="gpt-4o",
            source="stage_override",
            resolved_at=datetime(2026, 7, 13, 8, tzinfo=timezone.utc),
        ),
    )

    resolved = StageModelRouter("run-snapshot").resolve("graph_build")

    assert isinstance(resolved, ResolvedRoute)
    assert resolved.provider_id == "connection-1"
    assert resolved.model == "gpt-4o"
    assert resolved.started_at == "2026-07-13T08:00:00+00:00"


def test_routing_audit_is_idempotent_utc_and_secret_free(runtime):
    _, run_dir = runtime
    audit = AiRouteAudit("run-snapshot")
    route = AiRoute(
        stage="graph_build",
        provider_connection_id="connection-1",
        model_id="gpt-4o",
        source="default",
        provider_options={"base_url": "https://example.test/v1"},
    )

    first = audit.record_routing_resolved(
        "graph_build", route, fallback_reason="workspace route unavailable"
    )
    second = audit.record_routing_resolved(
        "graph_build", route, fallback_reason="must not overwrite"
    )

    assert second == first
    assert first["resolved_at"].endswith("+00:00")
    assert first["source"] == "default"
    assert first["fallback_reason"] == "workspace route unavailable"
    serialized = json.dumps(first).lower()
    assert "provider_options" not in serialized
    assert "base_url" not in serialized
    assert "example.test" not in serialized
    audit_files = list((run_dir / "stages").glob("*_routing_resolved.json"))
    assert len(audit_files) == 1
