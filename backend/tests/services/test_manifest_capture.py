"""Tests für ManifestCapture (Issue #763, Ticket 2)."""

import hashlib
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

    def test_legacy_captured_at_is_timezone_aware(self, run_dir):
        """Bug_015: naive started_at-Strings dürfen kein naives captured_at
        erzeugen — sonst crasht der Vergleich mit tz-aware Draft-Manifesten."""
        ManifestCapture.migrate_legacy(
            run_id="run_legacy_tz",
            run_dir=run_dir,
            run_metadata={"started_at": "2026-01-15T10:00:00"},
            agora_version="0.9.0",
            schema_version="1.0.0",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        # tz-aware Serialisierung trägt einen Offset (+00:00 oder Z).
        captured_at = data["captured_at"]
        assert captured_at.endswith("+00:00") or captured_at.endswith("Z")

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
        # Nicht rekonstruierbare Felder: None statt fabrizierter Platzhalter
        # (Issue #1274 Punkt 4/6) — "unknown" bleibt nur für Pflicht-Strings
        # wie simulation_config_hash.
        assert data["inputs"]["seed_document_hash"] is None
        assert data["inputs"]["simulation_config_hash"] == "unknown"
        assert data["seeds"]["random_seed"] is None

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


class TestManifestCaptureLegacyReconstruction:
    """Issue #1274 Punkt 4: migrate_legacy übernimmt completed_at/status/
    llm_model/llm_provider statt sie stillschweigend zu ignorieren."""

    @pytest.fixture
    def run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield tmp

    def test_reconstructs_runtime_from_completed_at_and_status(self, run_dir):
        ManifestCapture.migrate_legacy(
            run_id="run_legacy_rt",
            run_dir=run_dir,
            run_metadata={
                "started_at": "2026-01-15T10:00:00",
                "completed_at": "2026-01-15T10:30:00",
                "status": "completed",
            },
            agora_version="0.9.0",
            schema_version="1.0.0",
        )
        with open(os.path.join(run_dir, "manifest.json")) as f:
            data = json.load(f)

        assert data["runtime"] is not None
        assert data["runtime"]["termination_reason"] == "completed"
        assert data["runtime"]["completed_at"] is not None
        # RunManifest bleibt validierbar (AwareDatetime etc.)
        RunManifest(**data)

    def test_no_started_at_leaves_runtime_none(self, run_dir):
        """Ohne echten Start-Zeitpunkt darf runtime.started_at nicht auf
        "jetzt" fabriziert werden — dann bleibt runtime komplett None."""
        ManifestCapture.migrate_legacy(
            run_id="run_legacy_no_start",
            run_dir=run_dir,
            run_metadata={"completed_at": "2026-01-15T10:30:00", "status": "completed"},
            agora_version="0.9.0",
            schema_version="1.0.0",
        )
        with open(os.path.join(run_dir, "manifest.json")) as f:
            data = json.load(f)

        assert data["runtime"] is None

    def test_reconstructs_stage_route_from_llm_model_and_provider(self, run_dir):
        ManifestCapture.migrate_legacy(
            run_id="run_legacy_route",
            run_dir=run_dir,
            run_metadata={
                "started_at": "2026-01-15T10:00:00",
                "llm_model": "gemini-2.5-flash",
                "llm_provider": "google",
            },
            agora_version="0.9.0",
            schema_version="1.0.0",
        )
        with open(os.path.join(run_dir, "manifest.json")) as f:
            data = json.load(f)

        stage = data["routing"]["stages"]["simulation_rounds"]
        assert stage["model"] == "gemini-2.5-flash"
        assert stage["provider"] == "google"
        assert stage["base_url"] is None

    def test_omits_stage_route_when_provider_unknown(self, run_dir):
        """Nur model ODER nur provider bekannt reicht nicht für einen
        gültigen StageRoute-Eintrag — dann bleibt die Stage-Tabelle leer,
        statt eine erfundene provider-Zeichenkette einzusetzen."""
        ManifestCapture.migrate_legacy(
            run_id="run_legacy_partial",
            run_dir=run_dir,
            run_metadata={"started_at": "2026-01-15T10:00:00", "llm_model": "gemini-2.5-flash"},
            agora_version="0.9.0",
            schema_version="1.0.0",
        )
        with open(os.path.join(run_dir, "manifest.json")) as f:
            data = json.load(f)

        assert data["routing"]["stages"] == {}

    def test_simulation_id_seed_from_metadata(self, run_dir):
        ManifestCapture.migrate_legacy(
            run_id="run_legacy_seed",
            run_dir=run_dir,
            run_metadata={"started_at": "2026-01-15T10:00:00", "simulation_id": "sim_old"},
            agora_version="0.9.0",
            schema_version="1.0.0",
        )
        with open(os.path.join(run_dir, "manifest.json")) as f:
            data = json.load(f)

        assert data["seeds"]["simulation_id_seed"] == "sim_old"

    def test_simulation_id_seed_none_when_unknown(self, run_dir):
        """Kein fabriziertes "legacy" mehr, wenn die simulation_id nicht in
        den Run-Metadaten steht."""
        ManifestCapture.migrate_legacy(
            run_id="run_legacy_no_seed",
            run_dir=run_dir,
            run_metadata={"started_at": "2026-01-15T10:00:00"},
            agora_version="0.9.0",
            schema_version="1.0.0",
        )
        with open(os.path.join(run_dir, "manifest.json")) as f:
            data = json.load(f)

        assert data["seeds"]["simulation_id_seed"] is None


class TestManifestCaptureDraftRoutingAndReplay:
    """Issue #1274 Punkt 2/3/5: ai_route_snapshot, Prompt-Snapshots,
    Simulationsparameter und Deviations in capture_draft."""

    @pytest.fixture
    def run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield tmp

    def _draft_kwargs(self, run_dir, **overrides):
        base = dict(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=None,
            simulation_id_seed="sim_test",
        )
        base.update(overrides)
        return base

    def test_routing_dict_accepts_ai_route_snapshot(self, run_dir):
        ManifestCapture.capture_draft(
            **self._draft_kwargs(
                run_dir,
                routing={
                    "simulation_rounds": {
                        "model": "gemini-2.5-flash",
                        "provider": "google",
                        "base_url": "https://generativelanguage.googleapis.com",
                        "ai_route_snapshot": {
                            "provider_connection_id": "conn-google",
                            "model_id": "gemini-2.5-flash",
                            "source": "workspace",
                            "temperature": 0.7,
                            "provider_options": {},
                        },
                    }
                },
            )
        )
        with open(os.path.join(run_dir, "manifest.json")) as f:
            data = json.load(f)

        snapshot = data["routing"]["stages"]["simulation_rounds"]["ai_route_snapshot"]
        assert snapshot["source"] == "workspace"
        assert snapshot["temperature"] == 0.7
        RunManifest(**data)

    def test_writes_prompt_snapshots(self, run_dir):
        ManifestCapture.capture_draft(
            **self._draft_kwargs(
                run_dir,
                prompts={
                    "oasis_user_system_message": {
                        "content": "# OBJECTIVE\n...",
                        "source_file": "camel-oasis==0.2.5:oasis/social_platform/config/user.py",
                    }
                },
            )
        )
        with open(os.path.join(run_dir, "manifest.json")) as f:
            data = json.load(f)

        entry = data["prompts"]["entries"]["oasis_user_system_message"]
        assert entry["content"] == "# OBJECTIVE\n..."

    def test_builds_simulation_params_when_platform_and_flag_given(self, run_dir):
        ManifestCapture.capture_draft(
            **self._draft_kwargs(
                run_dir,
                platform="twitter",
                max_rounds=5,
                enable_graph_memory_update=True,
                memory_update_graph_id="graph_mem_001",
            )
        )
        with open(os.path.join(run_dir, "manifest.json")) as f:
            data = json.load(f)

        assert data["simulation"] == {
            "platform": "twitter",
            "max_rounds": 5,
            "enable_graph_memory_update": True,
            "memory_update_graph_id": "graph_mem_001",
        }

    def test_simulation_stays_none_without_platform(self, run_dir):
        """Ohne platform/enable_graph_memory_update bleibt simulation None,
        statt mit fabrizierten Defaults befüllt zu werden."""
        ManifestCapture.capture_draft(**self._draft_kwargs(run_dir))
        with open(os.path.join(run_dir, "manifest.json")) as f:
            data = json.load(f)

        assert data["simulation"] is None

    def test_writes_deviations_and_replayed_from_run_id(self, run_dir):
        ManifestCapture.capture_draft(
            **self._draft_kwargs(
                run_dir,
                replayed_from_run_id="run_original123",
                deviations=[
                    {"field": "model_id", "original": "gpt-4o", "replay": "gemini-2.5-pro"}
                ],
            )
        )
        with open(os.path.join(run_dir, "manifest.json")) as f:
            data = json.load(f)

        assert data["replayed_from_run_id"] == "run_original123"
        assert data["deviations"] == [
            {"field": "model_id", "original": "gpt-4o", "replay": "gemini-2.5-pro"}
        ]


class TestManifestCaptureSeedDocumentSnapshot:
    """Issue #1274 Punkt 6: echter Hash/Dateiname statt "unknown"."""

    def test_none_project_id_returns_none_tuple(self):
        assert ManifestCapture.seed_document_snapshot(None) == (None, None)

    def test_hashes_extracted_text_and_reads_filenames(self, monkeypatch):
        from app.models.project import ProjectManager

        monkeypatch.setattr(
            ProjectManager, "get_extracted_text", classmethod(lambda cls, pid: "hello world")
        )

        class _Entry:
            filename = "quelle.md"

        class _Manifest:
            documents = [_Entry()]

        monkeypatch.setattr(
            ProjectManager, "get_document_manifest", classmethod(lambda cls, pid: _Manifest())
        )

        digest, filename = ManifestCapture.seed_document_snapshot("proj_1")
        assert digest == (
            "sha256:" + hashlib.sha256(b"hello world").hexdigest()
        )
        assert filename == "quelle.md"

    def test_missing_text_returns_none_hash(self, monkeypatch):
        from app.models.project import ProjectManager

        monkeypatch.setattr(
            ProjectManager, "get_extracted_text", classmethod(lambda cls, pid: None)
        )
        monkeypatch.setattr(
            ProjectManager, "get_document_manifest", classmethod(lambda cls, pid: None)
        )

        digest, filename = ManifestCapture.seed_document_snapshot("proj_1")
        assert digest is None
        assert filename is None


class TestManifestCaptureOasisPromptSnapshot:
    """Issue #1274 Punkt 5: byte-genauer Snapshot des OASIS-System-Prompts."""

    def test_returns_installed_package_source(self):
        snapshots = ManifestCapture.oasis_prompt_snapshots()
        assert "oasis_user_system_message" in snapshots
        entry = snapshots["oasis_user_system_message"]
        assert "to_system_message" in entry["content"] or "OBJECTIVE" in entry["content"]
        assert entry["source_file"].startswith("camel-oasis==")

    def test_missing_distribution_returns_empty_dict(self, monkeypatch):
        import importlib.metadata as metadata_module

        def _boom(name):
            raise metadata_module.PackageNotFoundError(name)

        monkeypatch.setattr(
            "app.services.manifest_capture.importlib.metadata.distribution", _boom
        )
        assert ManifestCapture.oasis_prompt_snapshots() == {}


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


class TestManifestAtomicWrite:
    """CodeRabbit-Fund: Manifest-Writes liefen über ``open(..., "w")``.

    Das trunkiert die Zieldatei bereits beim Öffnen — bricht der Dump danach
    ab, bleibt statt eines gültigen Manifests eine Ruine zurück. Parallele
    Leser (``GET /manifest``, ZIP-Export) konnten außerdem halbfertiges JSON
    erwischen.
    """

    @pytest.fixture
    def run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield tmp

    def _draft(self, run_dir, *, graph_id="graph_001"):
        ManifestCapture.capture_draft(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id=graph_id,
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

    def test_failed_write_leaves_previous_manifest_intact(self, run_dir, monkeypatch):
        self._draft(run_dir, graph_id="graph_original")
        manifest_path = os.path.join(run_dir, "manifest.json")

        def _boom(*args, **kwargs):
            raise OSError("Disk voll")

        monkeypatch.setattr("app.services.manifest_capture.json.dump", _boom)

        with pytest.raises(OSError):
            self._draft(run_dir, graph_id="graph_neu")

        with open(manifest_path) as f:
            data = json.load(f)
        assert data["inputs"]["graph_id"] == "graph_original"
        assert RunManifest(**data).status == "draft"

    def test_failed_write_leaves_no_temp_file_behind(self, run_dir, monkeypatch):
        self._draft(run_dir)

        def _boom(*args, **kwargs):
            raise OSError("Disk voll")

        monkeypatch.setattr("app.services.manifest_capture.json.dump", _boom)

        with pytest.raises(OSError):
            self._draft(run_dir, graph_id="graph_neu")

        assert os.listdir(run_dir) == ["manifest.json"]
