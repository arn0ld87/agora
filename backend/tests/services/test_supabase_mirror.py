"""Supabase-Mirror-Service (Phase 1): Unit-Tests mit Fake-Client.

Kein Live-Supabase: Der Transport wird gefaket, die Tests beweisen
Mapping, Idempotenz-Params, Delta-Logik, Non-Fatal-Garantie und
Rebuild-aus-Wahrheit.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import pytest
import requests

from app.config import Config
from app.contracts.document_manifest_contract import DocumentManifestEntry
from app.services.supabase_mirror.client import (
    SupabaseMirrorError,
    SupabaseRestClient,
)
from app.services.supabase_mirror.mirror import (
    _build_event_rows,
    _build_run_record,
    get_supabase_mirror,
)


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: List[Tuple[str, str]] = []
        self.kwargs: List[Dict[str, Any]] = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url))
        self.kwargs.append({"json": json, "headers": headers, "timeout": timeout})
        return FakeResponse(self.status_code, "err" if self.status_code >= 300 else "")

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url))
        self.kwargs.append({"headers": headers, "timeout": timeout})
        return FakeResponse(self.status_code)


class FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.upserts: List[Tuple[str, List[Dict[str, Any]], Tuple[str, ...]]] = []

    def upsert(self, table, rows, *, on_conflict):
        if self.fail:
            raise SupabaseMirrorError("boom")
        self.upserts.append((table, rows, tuple(on_conflict)))


def _manifest(events: int = 2, status: str = "processing") -> Dict[str, Any]:
    return {
        "run_id": "run_abc123",
        "run_type": "simulation",
        "entity_id": "sim_1",
        "parent_run_id": None,
        "status": status,
        "progress": 40,
        "message": "working",
        "error": None,
        "started_at": "2026-09-11T10:00:00",
        "updated_at": "2026-09-11T10:01:00",
        "completed_at": None,
        "branch_label": None,
        "termination_reason": None,
        "linked_ids": {"project_id": "proj_1", "simulation_id": "sim_1"},
        "metadata": {},
        "events": [
            {
                "timestamp": f"2026-09-11T10:00:{i:02d}",
                "type": "updated",
                "status": status,
                "progress": 10 * i,
                "message": f"step {i}",
                "error": None,
                "details": {"internal": "never-mirrored"},
            }
            for i in range(events)
        ],
    }


@pytest.fixture()
def mirror():
    instance = get_supabase_mirror()
    instance.reset_for_tests()
    yield instance
    instance.reset_for_tests()


@pytest.fixture()
def enabled(mirror, monkeypatch):
    monkeypatch.setattr(Config, "SUPABASE_ENABLED", True)
    monkeypatch.setattr(Config, "SUPABASE_URL", "http://supabase-kong:8000")
    monkeypatch.setattr(Config, "SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    return mirror


class TestDisabled:
    def test_disabled_mirror_never_creates_client_or_sends(self, mirror, monkeypatch):
        monkeypatch.setattr(Config, "SUPABASE_ENABLED", False)
        fake = FakeClient()
        mirror._client = fake  # wuerde bei enabled sofort genutzt

        mirror.mirror_run(_manifest())
        mirror.mirror_report({"report_id": "rep_1", "status": "COMPLETED"})
        mirror.mirror_documents("proj_1", [])

        assert fake.upserts == []
        assert mirror._client is fake  # nie ersetzt — kein Netzwerk-Pfad aktiv


class TestRunMirror:
    def test_upserts_run_and_all_events_on_first_contact(self, enabled):
        fake = FakeClient()
        enabled._client = fake

        enabled._mirror_run_sync(_manifest(events=2))

        tables = [table for table, _, _ in fake.upserts]
        assert tables == ["runs", "run_events"]
        run_row = fake.upserts[0][1][0]
        assert run_row["run_id"] == "run_abc123"
        assert run_row["project_id"] == "proj_1"
        assert fake.upserts[1][2] == ("run_id", "seq")
        assert len(fake.upserts[1][1]) == 2
        # Payload-Guard: details werden nie gespiegelt
        assert "details" not in fake.upserts[1][1][0]

    def test_delta_semantics_send_only_new_events(self, enabled):
        fake = FakeClient()
        enabled._client = fake

        enabled._mirror_run_sync(_manifest(events=2))
        manifest = _manifest(events=3)
        enabled._mirror_run_sync(manifest)

        second_run_events = fake.upserts[-1]
        assert second_run_events[2] == ("run_id", "seq")
        assert len(second_run_events[1]) == 1
        assert second_run_events[1][0]["seq"] == 2

    def test_invalid_status_record_is_skipped_silently(self, enabled):
        fake = FakeClient()
        enabled._client = fake

        enabled._mirror_run_sync(_manifest(status="bogus-status"))

        assert fake.upserts == []

    def test_progress_clamped_into_contract_bounds(self):
        manifest = _manifest()
        manifest["progress"] = 150
        record = _build_run_record(manifest)
        assert record is not None
        assert record.progress == 100

    def test_long_event_message_truncated(self):
        manifest = _manifest(events=1)
        manifest["events"][0]["message"] = "x" * 5000
        rows = _build_event_rows(manifest)
        assert len(rows[0].message) == 1000

    def test_transport_failure_is_non_fatal_in_guarded_path(self, enabled):
        enabled._client = FakeClient(fail=True)

        enabled._guarded(lambda: enabled._mirror_run_sync(_manifest()))

        # Nichts propagiert — _guarded hat geschluckt und geloggt.


class TestReportMirror:
    def test_report_index_mapping(self, enabled):
        fake = FakeClient()
        enabled._client = fake

        enabled._mirror_report_sync(
            {
                "report_id": "rep_1",
                "status": "INCOMPLETE",
                "has_evidence": True,
                "evidence_sections": 3,
            }
        )

        row = fake.upserts[0][1][0]
        assert fake.upserts[0][2] == ("report_id",)
        assert row["artifact_path"] == "reports/rep_1"
        assert row["evidence_ok"] is True
        assert row["status"] == "INCOMPLETE"

    def test_report_without_id_is_skipped(self, enabled):
        fake = FakeClient()
        enabled._client = fake

        enabled._mirror_report_sync({"status": "COMPLETED"})

        assert fake.upserts == []


class TestDocumentMirror:
    def test_enrichment_with_file_path(self, enabled, tmp_path):
        fake = FakeClient()
        enabled._client = fake
        doc_file = tmp_path / "doc.md"
        doc_file.write_bytes(b"agora" * 100)

        enabled._mirror_documents_sync(
            "proj_1",
            [DocumentManifestEntry(document_id="doc", filename="doc.md", start_offset=0, end_offset=5)],
            {"doc": str(doc_file)},
        )

        row = fake.upserts[0][1][0]
        assert fake.upserts[0][2] == ("project_id", "document_id")
        assert row["size_bytes"] == 500
        assert len(row["sha256"]) == 64

    def test_without_path_derived_columns_are_omitted(self, enabled):
        fake = FakeClient()
        enabled._client = fake

        enabled._mirror_documents_sync(
            "proj_1",
            [DocumentManifestEntry(document_id="doc", filename="doc.md", start_offset=0, end_offset=5)],
            {},
        )

        row = fake.upserts[0][1][0]
        assert "size_bytes" not in row  # PostgREST überschreibt nur gelieferte Spalten
        assert "sha256" not in row


class TestRebuild:
    def test_rebuild_disabled_raises(self, mirror, monkeypatch):
        monkeypatch.setattr(Config, "SUPABASE_ENABLED", False)
        with pytest.raises(SupabaseMirrorError):
            mirror.rebuild_index()

    def test_rebuild_restores_index_from_truth(self, enabled, tmp_path, monkeypatch):
        from app.services.run_registry import RunRegistry

        fake = FakeClient()
        enabled._client = fake

        runs_dir = tmp_path / "run_registry"
        runs_dir.mkdir()
        (runs_dir / "run_a.json").write_text(json.dumps(_manifest(events=2)))
        (runs_dir / "run_b.json").write_text(json.dumps(_manifest(events=0)))
        (runs_dir / ".tmp-json-x.json").write_text("{}")  # Tempfile wird uebersprungen

        reports_dir = tmp_path / "reports"
        (reports_dir / "rep_1").mkdir(parents=True)
        (reports_dir / "rep_1" / "meta.json").write_text(
            json.dumps({"report_id": "rep_1", "status": "COMPLETED", "has_evidence": True,
                        "evidence_sections": 2})
        )

        monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(runs_dir))
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

        from app.models.project import ProjectManager

        monkeypatch.setattr(ProjectManager, "list_projects", lambda *a, **kw: [])

        counts = enabled.rebuild_index()

        assert counts == {"runs": 2, "run_events": 2, "reports": 1, "documents": 0}
        tables = {table for table, _, _ in fake.upserts}
        assert tables == {"runs", "run_events", "report_index"}


class TestRestClient:
    def test_upsert_request_shape_uses_service_role_and_schema(self):
        session = FakeSession()
        client = SupabaseRestClient(
            "http://kong:8000/",
            "svc-key",
            schema="agora",
            timeout_seconds=1.0,
            session=session,
        )

        client.upsert("runs", [{"run_id": "a"}], on_conflict=["run_id"])

        method, url = session.calls[0]
        assert method == "POST"
        assert url == "http://kong:8000/rest/v1/runs?on_conflict=run_id"
        headers = session.kwargs[0]["headers"]
        assert headers["apikey"] == "svc-key"
        assert headers["Authorization"] == "Bearer svc-key"
        assert headers["Content-Profile"] == "agora"
        assert "resolution=merge-duplicates" in headers["Prefer"]
        assert session.kwargs[0]["timeout"] == 1.0

    def test_upsert_failure_raises_mirror_error(self):
        client = SupabaseRestClient(
            "http://kong:8000",
            "svc-key",
            session=FakeSession(status_code=500),
        )
        with pytest.raises(SupabaseMirrorError):
            client.upsert("runs", [{"run_id": "a"}], on_conflict=["run_id"])

    def test_upsert_requires_conflict_columns(self):
        client = SupabaseRestClient("http://kong:8000", "svc-key", session=FakeSession())
        with pytest.raises(SupabaseMirrorError):
            client.upsert("runs", [{"run_id": "a"}], on_conflict=[])

    def test_healthcheck_true_on_2xx_false_on_network_error(self):
        client = SupabaseRestClient("http://kong:8000", "svc-key", session=FakeSession())
        assert client.healthcheck() is True

        class DeadSession:
            def get(self, *a, **kw):
                raise requests.RequestException("down")

        dead = SupabaseRestClient("http://kong:8000", "svc-key", session=DeadSession())
        assert dead.healthcheck() is False

    def test_requires_base_url_and_key(self):
        with pytest.raises(SupabaseMirrorError):
            SupabaseRestClient("", "svc-key")
        with pytest.raises(SupabaseMirrorError):
            SupabaseRestClient("http://kong:8000", "")


class TestRunRegistryHook:
    def test_write_run_submits_manifest_to_mirror(self, tmp_path, monkeypatch):
        from app.services import supabase_mirror as supabase_mirror_pkg
        from app.services.run_registry import RunRegistry

        monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(tmp_path))
        RunRegistry._instance = None
        registry = RunRegistry()

        submitted: list[Dict[str, Any]] = []

        class SpyMirror:
            def mirror_run(self, manifest):
                submitted.append(dict(manifest))

        # Hook importiert zur Laufzeit aus dem Paket — dort patchen.
        monkeypatch.setattr(supabase_mirror_pkg, "get_supabase_mirror", lambda: SpyMirror())

        manifest = registry.create_run("simulation", "sim_1")

        assert len(submitted) == 1
        assert submitted[0]["run_id"] == manifest["run_id"]
        assert submitted[0]["status"] == "pending"

    def test_write_run_survives_broken_mirror(self, tmp_path, monkeypatch):
        from app.services import supabase_mirror as supabase_mirror_pkg
        from app.services.run_registry import RunRegistry

        monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(tmp_path))
        RunRegistry._instance = None
        registry = RunRegistry()

        class BrokenMirror:
            def mirror_run(self, manifest):
                raise RuntimeError("mirror down")

        monkeypatch.setattr(supabase_mirror_pkg, "get_supabase_mirror", lambda: BrokenMirror())

        manifest = registry.create_run("simulation", "sim_1")

        # Datei-Wahrheit ist trotz Mirror-Fehler intakt
        assert (tmp_path / f"{manifest['run_id']}.json").is_file()
        assert registry.get_run(manifest["run_id"]) is not None


class TestConfigValidation:
    def test_enabled_requires_url_and_service_key(self, monkeypatch):
        monkeypatch.setattr(Config, "SUPABASE_ENABLED", True)
        monkeypatch.setattr(Config, "SUPABASE_URL", "")
        monkeypatch.setattr(Config, "SUPABASE_SERVICE_ROLE_KEY", "")

        errors = Config.validate()

        assert any("SUPABASE_ENABLED=true requires SUPABASE_URL" in e for e in errors)
        assert any(
            "SUPABASE_ENABLED=true requires SUPABASE_SERVICE_ROLE_KEY" in e for e in errors
        )

    def test_disabled_needs_no_supabase_settings(self, monkeypatch):
        monkeypatch.setattr(Config, "SUPABASE_ENABLED", False)
        monkeypatch.setattr(Config, "SUPABASE_URL", "")
        monkeypatch.setattr(Config, "SUPABASE_SERVICE_ROLE_KEY", "")

        errors = Config.validate()

        assert not any("SUPABASE_ENABLED=true requires" in e for e in errors)
