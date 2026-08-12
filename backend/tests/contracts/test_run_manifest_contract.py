"""Tests für RunManifest-Contract (Issue #763)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.run_manifest_contract import (
    ManifestInputs,
    ManifestPrompts,
    ManifestRouting,
    ManifestRuntime,
    ManifestSeeds,
    ManifestStatus,
    ManifestVersions,
    PromptSnapshot,
    ReplayOverrides,
    ReplayRequest,
    ReplayResponse,
    RunManifest,
    StageRoute,
)


class TestRunManifest:
    """S1: RunManifest — valide Instanziierung, Serialisierung, JSON-Schema."""

    def test_minimal_draft_manifest(self):
        """Ein Draft-Manifest mit Pflichtfeldern ist valide."""
        manifest = RunManifest(
            schema_version=1,
            run_id="run_abc123def456",
            captured_at=datetime.now(timezone.utc),
            inputs=ManifestInputs(
                seed_document_hash="sha256:abc123",
                seed_document_filename="testfall.md",
                simulation_config_hash="sha256:def456",
                graph_id="graph_001",
            ),
            versions=ManifestVersions(
                agora_version="0.9.5",
                schema_version="1.0.0",
            ),
            routing=ManifestRouting(stages={}),
            prompts=ManifestPrompts(entries={}),
            seeds=ManifestSeeds(random_seed=42, simulation_id_seed="sim_abc123"),
            status="draft",
        )
        assert manifest.run_id == "run_abc123def456"
        assert manifest.status == "draft"
        assert manifest.replayed_from_run_id is None

    def test_full_final_manifest(self):
        """Ein finales Manifest mit allen optionalen Feldern ist valide."""
        manifest = RunManifest(
            schema_version=1,
            run_id="run_full123456",
            replayed_from_run_id="run_orig000000",
            captured_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
            inputs=ManifestInputs(
                seed_document_hash="sha256:abc123",
                seed_document_filename="testfall.md",
                simulation_config_hash="sha256:def456",
                graph_id="graph_001",
                graph_version="v2",
                embedding_version="emb_v1",
            ),
            versions=ManifestVersions(
                agora_version="0.9.5",
                schema_version="1.0.0",
            ),
            routing=ManifestRouting(
                stages={
                    "persona_generation": StageRoute(
                        model="gemini-2.5-flash",
                        provider="google",
                        base_url="https://generativelanguage.googleapis.com",
                    ),
                }
            ),
            prompts=ManifestPrompts(
                entries={
                    "section_prompt": PromptSnapshot(
                        content="Du bist ein Analyse-Agent...",
                        source_file="sections.py:200",
                    ),
                }
            ),
            seeds=ManifestSeeds(random_seed=42, simulation_id_seed="sim_abc123"),
            runtime=ManifestRuntime(
                started_at=datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 8, 12, 10, 30, tzinfo=timezone.utc),
                duration_seconds=1800,
                rounds_completed=10,
                termination_reason="completed",
            ),
            status="final",
        )
        assert manifest.status == "final"
        assert manifest.replayed_from_run_id == "run_orig000000"
        assert manifest.runtime is not None
        assert manifest.runtime.duration_seconds == 1800
        assert manifest.routing.stages["persona_generation"].model == "gemini-2.5-flash"

    def test_serialization_roundtrip(self):
        """Manifest überlebt dict-Roundtrip."""
        manifest = RunManifest(
            schema_version=1,
            run_id="run_abc123def456",
            captured_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
            inputs=ManifestInputs(
                seed_document_hash="sha256:abc123",
                seed_document_filename="testfall.md",
                simulation_config_hash="sha256:def456",
                graph_id="graph_001",
            ),
            versions=ManifestVersions(
                agora_version="0.9.5",
                schema_version="1.0.0",
            ),
            routing=ManifestRouting(stages={}),
            prompts=ManifestPrompts(entries={}),
            seeds=ManifestSeeds(random_seed=42, simulation_id_seed="sim_abc123"),
            status="draft",
        )
        data = manifest.model_dump()
        restored = RunManifest(**data)
        assert restored.run_id == manifest.run_id
        assert restored.status == manifest.status

    def test_rejects_invalid_status(self):
        """Ungültiger Status wird abgelehnt."""
        with pytest.raises(ValidationError):
            RunManifest(
                schema_version=1,
                run_id="run_abc123def456",
                captured_at=datetime.now(timezone.utc),
                inputs=ManifestInputs(
                    seed_document_hash="sha256:abc123",
                    seed_document_filename="testfall.md",
                    simulation_config_hash="sha256:def456",
                    graph_id="graph_001",
                ),
                versions=ManifestVersions(
                    agora_version="0.9.5",
                    schema_version="1.0.0",
                ),
                routing=ManifestRouting(stages={}),
                prompts=ManifestPrompts(entries={}),
                seeds=ManifestSeeds(random_seed=42, simulation_id_seed="sim_abc123"),
                status="invalid_status",  # type: ignore[arg-type]
            )

    def test_rejects_extra_fields(self):
        """Unbekannte Felder werden abgelehnt (extra="forbid")."""
        with pytest.raises(ValidationError):
            RunManifest(
                schema_version=1,
                run_id="run_abc123def456",
                captured_at=datetime.now(timezone.utc),
                inputs=ManifestInputs(
                    seed_document_hash="sha256:abc123",
                    seed_document_filename="testfall.md",
                    simulation_config_hash="sha256:def456",
                    graph_id="graph_001",
                ),
                versions=ManifestVersions(
                    agora_version="0.9.5",
                    schema_version="1.0.0",
                ),
                routing=ManifestRouting(stages={}),
                prompts=ManifestPrompts(entries={}),
                seeds=ManifestSeeds(random_seed=42, simulation_id_seed="sim_abc123"),
                status="draft",
                geheim_feld="sollte_nicht_drin_sein",  # type: ignore[call-arg]
            )


class TestReplayRequest:
    """S2: ReplayRequest — valide/invalide Overrides."""

    def test_empty_overrides(self):
        """Leere Overrides = identisches Replay."""
        req = ReplayRequest()
        assert req.overrides is None

    def test_seed_document_override(self):
        """Nur Seed-Dokument überschreiben."""
        req = ReplayRequest(overrides=ReplayOverrides(seed_document_id="doc_123"))
        assert req.overrides is not None
        assert req.overrides.seed_document_id == "doc_123"
        assert req.overrides.random_seed is None

    def test_full_overrides(self):
        """Alle Overrides auf einmal."""
        req = ReplayRequest(
            overrides=ReplayOverrides(
                seed_document_id="doc_456",
                random_seed=12345,
                ai_model_ref={
                    "provider_connection_id": "conn_1",
                    "model_id": "gemini-2.5-pro",
                },
            )
        )
        assert req.overrides is not None
        assert req.overrides.random_seed == 12345

    def test_rejects_unknown_override_key(self):
        """Unbekannte Override-Keys werden abgelehnt (extra=forbid)."""
        with pytest.raises(ValidationError):
            ReplayOverrides(geheim_override="value")  # type: ignore[call-arg]


class TestReplayResponse:
    """S3: ReplayResponse — Grundstruktur."""

    def test_basic_response(self):
        resp = ReplayResponse(run_id="run_new123456", status="pending")
        assert resp.run_id == "run_new123456"
        assert resp.status == "pending"

    def test_serialization(self):
        resp = ReplayResponse(run_id="run_new123456", status="pending")
        data = resp.model_dump()
        assert data == {"run_id": "run_new123456", "status": "pending"}
