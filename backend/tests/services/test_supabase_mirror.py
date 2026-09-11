"""Supabase-Mirror-Service (Phase 1): Unit-Tests mit Fake-Client.

Kein Live-Supabase: Der Transport wird gefaket, die Tests beweisen
Mapping, Idempotenz-Params, Delta-Logik, Non-Fatal-Garantie und
Rebuild-aus-Wahrheit.
"""
from __future__ import annotations

import json
import threading
import time
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
    MAX_PENDING_MIRROR_JOBS,
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

    def delete(self, url, headers=None, timeout=None):
        self.calls.append(("DELETE", url))
        self.kwargs.append({"headers": headers, "timeout": timeout})
        return FakeResponse(self.status_code, "err" if self.status_code >= 300 else "")

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url))
        self.kwargs.append({"headers": headers, "timeout": timeout})
        return FakeResponse(self.status_code)


class FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.upserts: List[Tuple[str, List[Dict[str, Any]], Tuple[str, ...]]] = []
        self.deletes: List[Tuple[str, str]] = []

    def upsert(self, table, rows, *, on_conflict):
        if self.fail:
            raise SupabaseMirrorError("boom")
        self.upserts.append((table, rows, tuple(on_conflict)))

    def delete_stale(self, table, *, mirrored_before):
        if self.fail:
            raise SupabaseMirrorError("boom")
        self.deletes.append((table, mirrored_before))


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
        mirror.mirror_report({"report_id": "rep_1", "status": "completed"})
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
                "status": "incomplete",
                "has_evidence": True,
                "evidence_sections": 3,
            }
        )

        row = fake.upserts[0][1][0]
        assert fake.upserts[0][2] == ("report_id",)
        assert row["artifact_path"] == "reports/rep_1"
        assert row["evidence_ok"] is True
        assert row["status"] == "incomplete"

    def test_report_without_id_is_skipped(self, enabled):
        fake = FakeClient()
        enabled._client = fake

        enabled._mirror_report_sync({"status": "completed"})

        assert fake.upserts == []

    @pytest.mark.parametrize("status", ["unknown", None, "COMPLETED"])
    def test_status_outside_report_contract_is_skipped(self, enabled, status):
        # Regression: der Mirror setzte frueher "unknown" ein und schrieb
        # damit einen Statuswert nach agora.report_index, den der
        # ReportStatus-Vertrag nicht kennt.
        fake = FakeClient()
        enabled._client = fake

        enabled._mirror_report_sync({"report_id": "rep_1", "status": status})

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


def _truth_dirs(tmp_path, monkeypatch, *, projects=()):
    """Verdrahtet Run-Registry, Report-Ordner und Projekt-Verzeichnis auf tmp."""
    from app.models.project import ProjectManager
    from app.services.run_registry import RunRegistry

    runs_dir = tmp_path / "run_registry"
    runs_dir.mkdir()
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(runs_dir))
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))

    for project_id in projects:
        project_dir = projects_dir / project_id
        project_dir.mkdir()
        (project_dir / "project.json").write_text(
            json.dumps(
                {
                    "project_id": project_id,
                    "name": project_id,
                    "status": "created",
                    "created_at": "2026-09-11T10:00:00",
                    "updated_at": "2026-09-11T10:00:00",
                }
            )
        )
        (project_dir / "extracted_documents.json").write_text(
            json.dumps(
                {
                    "documents": [
                        {
                            "document_id": "doc",
                            "filename": "doc.md",
                            "start_offset": 0,
                            "end_offset": 5,
                        }
                    ]
                }
            )
        )
    return runs_dir


class TestRebuild:
    def test_rebuild_disabled_raises(self, mirror, monkeypatch):
        monkeypatch.setattr(Config, "SUPABASE_ENABLED", False)
        with pytest.raises(SupabaseMirrorError):
            mirror.rebuild_index()

    def test_rebuild_restores_index_from_truth(self, enabled, tmp_path, monkeypatch):
        fake = FakeClient()
        enabled._client = fake

        runs_dir = _truth_dirs(tmp_path, monkeypatch)
        (runs_dir / "run_a.json").write_text(json.dumps(_manifest(events=2)))
        (runs_dir / "run_b.json").write_text(json.dumps(_manifest(events=0)))
        (runs_dir / ".tmp-json-x.json").write_text("{}")  # Tempfile wird uebersprungen

        reports_dir = tmp_path / "reports"
        (reports_dir / "rep_1").mkdir(parents=True)
        (reports_dir / "rep_1" / "meta.json").write_text(
            json.dumps({"report_id": "rep_1", "status": "completed", "has_evidence": True,
                        "evidence_sections": 2})
        )

        counts = enabled.rebuild_index()

        assert counts == {"runs": 2, "run_events": 2, "reports": 1, "documents": 0}
        tables = {table for table, _, _ in fake.upserts}
        assert tables == {"runs", "run_events", "report_index"}

    def test_rebuild_sweeps_rows_the_truth_no_longer_has(
        self, enabled, tmp_path, monkeypatch
    ):
        # Ohne Sweep bliebe die Zeile eines lokal geloeschten Runs fuer
        # immer im Spiegel stehen — auch ein zweiter Rebuild raeumte sie nicht.
        fake = FakeClient()
        enabled._client = fake

        runs_dir = _truth_dirs(tmp_path, monkeypatch)
        (runs_dir / "run_a.json").write_text(json.dumps(_manifest(events=2)))

        enabled.rebuild_index()

        assert [table for table, _ in fake.deletes] == [
            "runs",
            "run_events",
            "report_index",
            "documents",
        ]
        sweep_stamps = {stamp for _, stamp in fake.deletes}
        assert len(sweep_stamps) == 1
        sweep_stamp = sweep_stamps.pop()
        # Jede geschriebene Zeile traegt genau den Sweep-Stempel, ueberlebt
        # das anschliessende delete_stale(< stamp) also.
        written = [row for _, rows, _ in fake.upserts for row in rows]
        assert written
        assert {row["mirrored_at"] for row in written} == {sweep_stamp}

    def test_rebuild_mirrors_all_events_despite_delta_state(
        self, enabled, tmp_path, monkeypatch
    ):
        # Der Delta-Tracker darf den Rebuild nicht aushebeln: Events, die er
        # ueberspringt, traegen keinen Sweep-Stempel und wuerden geloescht.
        fake = FakeClient()
        enabled._client = fake
        enabled._mirror_run_sync(_manifest(events=2))
        fake.upserts.clear()

        runs_dir = _truth_dirs(tmp_path, monkeypatch)
        (runs_dir / "run_a.json").write_text(json.dumps(_manifest(events=2)))

        enabled.rebuild_index()

        event_rows = [
            row for table, rows, _ in fake.upserts if table == "run_events" for row in rows
        ]
        assert [row["seq"] for row in event_rows] == [0, 1]

    def test_rebuild_covers_more_projects_than_the_list_limit(
        self, enabled, tmp_path, monkeypatch
    ):
        # list_projects(limit=1000) schnitt den Rebuild stillschweigend ab und
        # meldete ihn trotzdem als vollstaendig.
        fake = FakeClient()
        enabled._client = fake
        project_ids = [f"proj_{i:05d}" for i in range(1001)]

        _truth_dirs(tmp_path, monkeypatch, projects=project_ids)

        counts = enabled.rebuild_index()

        assert counts["documents"] == 1001
        mirrored = {
            row["project_id"]
            for table, rows, _ in fake.upserts
            if table == "documents"
            for row in rows
        }
        assert mirrored == set(project_ids)


class TestPendingJobQueue:
    """Der Rueckstau darf nicht unbegrenzt wachsen (Speicher des Backends)."""

    @staticmethod
    def _drain(mirror, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        while mirror._pending and time.monotonic() < deadline:
            time.sleep(0.01)

    def test_updates_of_one_entity_are_coalesced_to_the_newest(self, enabled):
        entered = threading.Event()
        release = threading.Event()
        run_messages: List[str] = []

        class BlockingClient:
            def upsert(self, table, rows, *, on_conflict):
                if table == "runs":
                    run_messages.append(rows[0]["message"])
                    entered.set()
                    release.wait(10)

        enabled._client = BlockingClient()

        first = _manifest(events=1)
        first["message"] = "update 0"
        enabled.mirror_run(first)
        assert entered.wait(10)  # Worker haengt jetzt im ersten Upsert

        for i in range(1, 501):
            update = _manifest(events=1)
            update["message"] = f"update {i}"
            enabled.mirror_run(update)

        # 500 Updates derselben run_id -> genau ein wartender Snapshot
        assert len(enabled._pending) == 1

        release.set()
        self._drain(enabled)

        assert enabled._pending == {}
        # Der wartende Platz traegt den neuesten Stand, nicht den aeltesten.
        assert run_messages[-1] == "update 500"

    def test_backlog_is_capped_across_distinct_entities(self, enabled):
        entered = threading.Event()
        release = threading.Event()

        class BlockingClient:
            def upsert(self, table, rows, *, on_conflict):
                entered.set()
                release.wait(10)

        enabled._client = BlockingClient()
        enabled.mirror_run(_manifest(events=0))
        assert entered.wait(10)

        for i in range(MAX_PENDING_MIRROR_JOBS + 50):
            update = _manifest(events=0)
            update["run_id"] = f"run_{i:05d}"
            enabled.mirror_run(update)

        assert len(enabled._pending) <= MAX_PENDING_MIRROR_JOBS

        release.set()
        self._drain(enabled)
        assert enabled._pending == {}

    def test_disabled_mirror_queues_nothing(self, mirror, monkeypatch):
        monkeypatch.setattr(Config, "SUPABASE_ENABLED", False)

        mirror.mirror_run(_manifest())

        assert mirror._pending == {}


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

    def test_upsert_transport_error_becomes_mirror_error(self):
        # Regression: requests.RequestException lief ungefangen durch —
        # rebuild.main() faengt nur SupabaseMirrorError und quittierte den
        # Ausfall mit einem Traceback statt Exit 1.
        class DeadSession:
            def post(self, *a, **kw):
                raise requests.ConnectionError("kong down")

        client = SupabaseRestClient("http://kong:8000", "svc-key", session=DeadSession())

        with pytest.raises(SupabaseMirrorError) as excinfo:
            client.upsert("runs", [{"run_id": "a"}], on_conflict=["run_id"])

        assert isinstance(excinfo.value.__cause__, requests.RequestException)

    def test_delete_stale_request_shape(self):
        session = FakeSession()
        client = SupabaseRestClient(
            "http://kong:8000", "svc-key", schema="agora", session=session
        )

        client.delete_stale("runs", mirrored_before="2026-09-11T10:00:00+00:00")

        method, url = session.calls[0]
        assert method == "DELETE"
        assert url == (
            "http://kong:8000/rest/v1/runs"
            "?mirrored_at=lt.2026-09-11T10%3A00%3A00%2B00%3A00"
        )
        headers = session.kwargs[0]["headers"]
        assert headers["Content-Profile"] == "agora"
        assert "merge-duplicates" not in headers["Prefer"]

    def test_delete_stale_failure_raises_mirror_error(self):
        class DeadSession:
            def delete(self, *a, **kw):
                raise requests.ConnectionError("kong down")

        dead = SupabaseRestClient("http://kong:8000", "svc-key", session=DeadSession())
        with pytest.raises(SupabaseMirrorError):
            dead.delete_stale("runs", mirrored_before="2026-09-11T10:00:00+00:00")

        http_500 = SupabaseRestClient(
            "http://kong:8000", "svc-key", session=FakeSession(status_code=500)
        )
        with pytest.raises(SupabaseMirrorError):
            http_500.delete_stale("runs", mirrored_before="2026-09-11T10:00:00+00:00")

    def test_upsert_requires_conflict_columns(self):
        client = SupabaseRestClient("http://kong:8000", "svc-key", session=FakeSession())
        with pytest.raises(SupabaseMirrorError):
            client.upsert("runs", [{"run_id": "a"}], on_conflict=[])

    def test_healthcheck_true_on_2xx_false_on_network_error(self):
        session = FakeSession()
        client = SupabaseRestClient(
            "http://kong:8000", "svc-key", schema="agora", session=session
        )
        assert client.healthcheck() is True
        # Gegen eine Mirror-Tabelle mit Accept-Profile: nur so faellt ein
        # nicht exponiertes Schema (PGRST106) vor dem ersten Write auf.
        assert session.calls[0] == (
            "GET",
            "http://kong:8000/rest/v1/runs?select=count&limit=1",
        )
        assert session.kwargs[0]["headers"]["Accept-Profile"] == "agora"

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


class TestRebuildCli:
    """CLI-Meldungen gehen durch den Logger, nicht durch print() (AGENTS.md)."""

    @staticmethod
    def _collect_rebuild_logs(monkeypatch):
        """Sammelt Records der CLI und legt alle agora-Stream-Handler still.

        Die agora-Logger binden ihren StreamHandler beim ersten get_logger()
        an das damals aktive sys.stdout — unter capsys ist das ein laengst
        geschlossener Testcapture-Stream. Ohne dieses Stilllegen schreibt
        logging seinen eigenen Fehlerreport nach stderr und die
        "kein print()"-Zusicherung wuerde daran scheitern statt an einem print.
        """
        import logging

        from app.services.supabase_mirror import rebuild as rebuild_cli

        for name, candidate in list(logging.root.manager.loggerDict.items()):
            if isinstance(candidate, logging.Logger) and (
                name == "agora" or name.startswith("agora.")
            ):
                monkeypatch.setattr(candidate, "handlers", [])

        collected: List[Any] = []

        class Collector(logging.Handler):
            def emit(self, record):
                collected.append(record)

        monkeypatch.setattr(rebuild_cli.logger, "handlers", [Collector()])
        monkeypatch.setattr(rebuild_cli.logger, "level", logging.DEBUG)
        return rebuild_cli, collected

    def test_disabled_mirror_exits_1_via_logger(self, mirror, monkeypatch):
        rebuild_cli, records = self._collect_rebuild_logs(monkeypatch)
        monkeypatch.setattr(Config, "SUPABASE_ENABLED", False)

        assert rebuild_cli.main([]) == 1

        assert any(
            record.levelname == "ERROR"
            and "Supabase mirror is disabled" in record.getMessage()
            for record in records
        )

    def test_unreachable_supabase_exits_1_before_any_write(self, enabled, monkeypatch):
        rebuild_cli, records = self._collect_rebuild_logs(monkeypatch)

        class DeadSession:
            def get(self, *a, **kw):
                raise requests.ConnectionError("kong down")

        enabled._client = SupabaseRestClient(
            "http://kong:8000", "svc-key", session=DeadSession()
        )
        rebuilt: List[int] = []
        monkeypatch.setattr(
            type(enabled), "rebuild_index", lambda self: rebuilt.append(1)
        )

        assert rebuild_cli.main([]) == 1

        assert rebuilt == []  # kein Write-Versuch bei unerreichbarem Endpoint
        assert any(
            record.levelname == "ERROR"
            and "Supabase unreachable" in record.getMessage()
            for record in records
        )


    def test_cli_module_has_no_print_calls(self):
        # AGENTS.md verbietet print() in backend/app/** — der Logger ist der
        # einzige Ausgabekanal, die Exit-Codes bleiben das CLI-Interface.
        import inspect

        from app.services.supabase_mirror import rebuild as rebuild_cli

        assert "print(" not in inspect.getsource(rebuild_cli)


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
