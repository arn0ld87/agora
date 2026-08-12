"""Tests für ManifestCapture (Issue #763, Ticket 2)."""

import json
import os
import tempfile
from datetime import datetime, timezone

import pytest

from app.contracts.run_manifest_contract import RunManifest
from app.services.manifest_capture import ManifestCapture


class TestManifestCaptureDraft:
    """S1-S3: ManifestCapture.capture_draft() — Draft-Manifest schreiben."""

    @pytest.fixture
    def run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield tmp

    def test_writes_draft_manifest(self, run_dir):
        """S1: capture_draft schreibt manifest.json mit status draft."""
        ManifestCapture.capture_draft(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        assert os.path.exists(manifest_path), "manifest.json wurde nicht geschrieben"

        with open(manifest_path) as f:
            data = json.load(f)

        assert data["status"] == "draft"
        assert data["run_id"] == "run_test123456"
        assert data["schema_version"] == 1

    def test_manifest_is_valid_pydantic(self, run_dir):
        """S2: Geschriebenes Manifest ist als RunManifest validierbar."""
        ManifestCapture.capture_draft(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        manifest = RunManifest(**data)
        assert manifest.status == "draft"
        assert manifest.run_id == "run_test123456"
        assert manifest.inputs.seed_document_hash == "sha256:abc"
        assert manifest.seeds.random_seed == 42

    def test_captured_at_is_utc_datetime(self, run_dir):
        """S2: captured_at ist ein UTC-Datetime-String."""
        ManifestCapture.capture_draft(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        captured_at = data["captured_at"]
        assert "T" in captured_at or "+" in captured_at or "Z" in captured_at

    def test_optional_fields_are_null_when_missing(self, run_dir):
        """S3: Optionale Felder sind null wenn nicht übergeben."""
        ManifestCapture.capture_draft(
            run_id="run_minimal123",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        assert data["replayed_from_run_id"] is None
        assert data["runtime"] is None
        assert data["inputs"]["graph_version"] is None
        assert data["inputs"]["embedding_version"] is None

    def test_accepts_optional_routing_dict(self, run_dir):
        """S9 (Ticket 9): capture_draft nimmt optional Stage-Routing-Snapshots an."""
        ManifestCapture.capture_draft(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
            routing={
                "simulation_rounds": {
                    "model": "gemini-2.5-flash",
                    "provider": "google",
                    "base_url": "https://generativelanguage.googleapis.com",
                }
            },
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        assert data["routing"]["stages"]["simulation_rounds"]["model"] == "gemini-2.5-flash"


class TestManifestCaptureFinal:
    """S4-S6: ManifestCapture.capture_final() — Draft → Final."""

    @pytest.fixture
    def run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield tmp

    @pytest.fixture
    def draft_manifest(self, run_dir):
        """Schreibt ein Draft-Manifest als Ausgangspunkt."""
        ManifestCapture.capture_draft(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )
        return run_dir

    def test_finalizes_draft_to_final(self, draft_manifest):
        """S4: capture_final setzt status auf final und schreibt Runtime."""
        ManifestCapture.capture_final(
            run_id="run_test123456",
            run_dir=draft_manifest,
            started_at=datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 8, 12, 10, 30, tzinfo=timezone.utc),
            duration_seconds=1800,
            rounds_completed=10,
            termination_reason="completed",
        )

        manifest_path = os.path.join(draft_manifest, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        assert data["status"] == "final"
        assert data["runtime"]["duration_seconds"] == 1800
        assert data["runtime"]["rounds_completed"] == 10
        assert data["runtime"]["termination_reason"] == "completed"

    def test_final_preserves_draft_fields(self, draft_manifest):
        """S4: capture_final behält alle Draft-Felder unverändert."""
        ManifestCapture.capture_final(
            run_id="run_test123456",
            run_dir=draft_manifest,
            started_at=datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 8, 12, 10, 30, tzinfo=timezone.utc),
            duration_seconds=1800,
            rounds_completed=10,
            termination_reason="completed",
        )

        manifest_path = os.path.join(draft_manifest, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        assert data["run_id"] == "run_test123456"
        assert data["inputs"]["seed_document_hash"] == "sha256:abc"
        assert data["seeds"]["random_seed"] == 42
        assert data["versions"]["agora_version"] == "0.9.5"

    def test_final_manifest_is_valid_pydantic(self, draft_manifest):
        """S4: Finales Manifest ist als RunManifest validierbar."""
        ManifestCapture.capture_final(
            run_id="run_test123456",
            run_dir=draft_manifest,
            started_at=datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 8, 12, 10, 30, tzinfo=timezone.utc),
            duration_seconds=1800,
            rounds_completed=10,
            termination_reason="completed",
        )

        manifest_path = os.path.join(draft_manifest, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        manifest = RunManifest(**data)
        assert manifest.status == "final"
        assert manifest.runtime is not None
        assert manifest.runtime.duration_seconds == 1800

    def test_raises_when_no_draft_exists(self, run_dir):
        """S5: capture_final wirft Fehler wenn kein Draft-Manifest existiert."""
        with pytest.raises(FileNotFoundError):
            ManifestCapture.capture_final(
                run_id="run_nonexistent",
                run_dir=run_dir,
                started_at=datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 8, 12, 10, 30, tzinfo=timezone.utc),
                duration_seconds=1800,
                rounds_completed=10,
                termination_reason="completed",
            )


class TestManifestCaptureLegacy:
    """S7-S9: ManifestCapture.migrate_legacy() — Legacy-Manifest für Alt-Runs."""

    @pytest.fixture
    def run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield tmp

    def test_creates_legacy_manifest(self, run_dir):
        """S7: migrate_legacy schreibt Manifest mit status legacy."""
        ManifestCapture.migrate_legacy(
            run_id="run_legacy123",
            run_dir=run_dir,
            run_metadata={
                "started_at": "2026-01-15T10:00:00",
                "completed_at": "2026-01-15T10:30:00",
                "status": "completed",
                "llm_model": "gemini-2.5-flash",
                "graph_id": "graph_001",
            },
            agora_version="0.9.0",
            schema_version="1.0.0",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        assert os.path.exists(manifest_path)

        with open(manifest_path) as f:
            data = json.load(f)

        assert data["status"] == "legacy"
        assert data["run_id"] == "run_legacy123"

    def test_legacy_fills_known_fields(self, run_dir):
        """S8: Bekannte Felder sind gefüllt, unbekannte null."""
        ManifestCapture.migrate_legacy(
            run_id="run_legacy123",
            run_dir=run_dir,
            run_metadata={
                "started_at": "2026-01-15T10:00:00",
                "status": "completed",
                "llm_model": "gemini-2.5-flash",
                "graph_id": "graph_001",
            },
            agora_version="0.9.0",
            schema_version="1.0.0",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        # Bekannte Felder
        assert data["versions"]["agora_version"] == "0.9.0"
        assert data["inputs"]["graph_id"] == "graph_001"
        # Nicht rekonstruierbare Felder
        assert data["inputs"]["seed_document_hash"] == "unknown"
        assert data["inputs"]["simulation_config_hash"] == "unknown"
        assert data["seeds"]["random_seed"] == 0

    def test_legacy_is_valid_pydantic(self, run_dir):
        """S8: Legacy-Manifest ist als RunManifest validierbar."""
        ManifestCapture.migrate_legacy(
            run_id="run_legacy123",
            run_dir=run_dir,
            run_metadata={
                "started_at": "2026-01-15T10:00:00",
                "status": "completed",
            },
            agora_version="0.9.0",
            schema_version="1.0.0",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        manifest = RunManifest(**data)
        assert manifest.status == "legacy"

    def test_does_not_overwrite_existing_manifest(self, run_dir):
        """S9: Überschreibt kein vorhandenes Manifest."""
        # Erst ein Draft schreiben
        ManifestCapture.capture_draft(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

        # Migration sollte das Draft nicht überschreiben
        ManifestCapture.migrate_legacy(
            run_id="run_test123456",
            run_dir=run_dir,
            run_metadata={"status": "completed"},
            agora_version="0.9.0",
            schema_version="1.0.0",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        # Sollte immer noch das Draft sein
        assert data["status"] == "draft"
        assert data["seeds"]["random_seed"] == 42


class TestManifestCaptureBestEffort:
    """S10-S13: Best-Effort-Wrapper — dürfen niemals einen Run zum Scheitern bringen."""

    @pytest.fixture
    def run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield tmp

    def test_best_effort_draft_writes_manifest(self, run_dir):
        """S10: capture_draft_best_effort schreibt bei gültigen Daten normal."""
        ManifestCapture.capture_draft_best_effort(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        assert os.path.exists(manifest_path)

    def test_best_effort_draft_swallows_errors(self, run_dir, monkeypatch):
        """S11: Ein interner Fehler beim Schreiben darf nicht propagieren."""
        def _boom(*args, **kwargs):
            raise OSError("Disk voll")

        monkeypatch.setattr("app.services.manifest_capture.ManifestCapture.capture_draft", _boom)

        # Darf NICHT werfen — best-effort.
        ManifestCapture.capture_draft_best_effort(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

    def test_best_effort_final_swallows_missing_draft(self, run_dir):
        """S12: Fehlendes Draft-Manifest darf capture_final_best_effort nicht crashen lassen."""
        # Kein vorheriges capture_draft — Datei existiert nicht.
        ManifestCapture.capture_final_best_effort(
            run_id="run_nonexistent",
            run_dir=run_dir,
            started_at=datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 8, 12, 10, 30, tzinfo=timezone.utc),
            duration_seconds=1800,
            rounds_completed=10,
            termination_reason="completed",
        )
        # Kein Assert nötig — der Test besteht, wenn keine Exception fliegt.

    def test_best_effort_final_writes_when_draft_exists(self, run_dir):
        """S13: Bei vorhandenem Draft finalisiert der Best-Effort-Wrapper normal."""
        ManifestCapture.capture_draft(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

        ManifestCapture.capture_final_best_effort(
            run_id="run_test123456",
            run_dir=run_dir,
            started_at=datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 8, 12, 10, 30, tzinfo=timezone.utc),
            duration_seconds=1800,
            rounds_completed=10,
            termination_reason="completed",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)
        assert data["status"] == "final"
