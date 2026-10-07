"""Fachregeln des ``GraphDuplicateService`` (Issue #1808, Etappe 8, ADR-0022 §6).

Der Fake-Speicher führt kein Cypher aus. Er bildet nach, was der Dienst vom
``Neo4jDuplicateMixin`` erwartet (Paging nach UUID, ``MERGE`` auf der UUID,
Zeilenzahl als Rückgabe, Fehler bei fehlendem Endpunkt), damit Reihenfolge,
UUID-Abbildung und Rollback des Dienstes sichtbar werden. Die Cypher-Semantik
selbst prüft nur eine echte Neo4j-Instanz.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional

import pytest

from app.contracts.document_manifest_contract import DocumentManifest, DocumentManifestEntry
from app.contracts.graph_edit_contract import GraphDuplicateRequest
from app.contracts.project_contract import ProjectStatus
from app.contracts.simulation_record_contract import SimulationRecord
from app.models.project import ProjectManager
from app.services import graph_duplicate_service as module
from app.services.graph_duplicate_service import (
    GraphDuplicateService,
    GraphDuplicateSourceNotFound,
    GraphDuplicateSourceStateError,
    mapped_uuid,
)
from app.services.graph_edit_service import EmbeddingMigrationRunningError
from app.services.graph_lock import get_graph_lock_state
from app.storage.neo4j_duplicate import GraphDuplicateWriteError

SRC = "11111111-1111-4111-8111-111111111111"
REQ = "cccccccc-cccc-4ccc-8ccc-ccccccccccc1"
REQ2 = "cccccccc-cccc-4ccc-8ccc-ccccccccccc2"
NOW = "2026-10-07T10:00:00+00:00"
E = [f"00000000-0000-4000-8000-00000000000{i}" for i in range(1, 6)]
R = ["rrrrrrrr-0000-4000-8000-000000000001", "rrrrrrrr-0000-4000-8000-000000000002"]
EP = ["eeeeeeee-0000-4000-8000-000000000001", "eeeeeeee-0000-4000-8000-000000000002"]


# ── Fakes ───────────────────────────────────────────────────────────────


class FakeStorage:
    def __init__(self) -> None:
        self.graphs: Dict[str, Dict[str, Any]] = {}
        self.entities: Dict[str, Dict[str, Any]] = {}
        self.episodes: Dict[str, Dict[str, Any]] = {}
        self.relations: Dict[str, Dict[str, Any]] = {}
        self.calls: List[str] = []
        self.fail_on: Optional[str] = None
        self.delete_error: Optional[Exception] = None
        self.count_override: Optional[Dict[str, int]] = None

    def _maybe_fail(self, what: str) -> None:
        self.calls.append(what)
        if self.fail_on == what:
            raise RuntimeError(f"Verbindung weg bei {what}")

    # lesen
    def duplicate_read_graph(self, graph_id):
        graph = self.graphs.get(graph_id)
        return dict(graph) if graph is not None else None

    def duplicate_count(self, graph_id):
        if self.count_override is not None and graph_id != SRC:
            return dict(self.count_override)
        return {
            "entities": sum(1 for e in self.entities.values() if e["props"]["graph_id"] == graph_id),
            "relations": sum(1 for r in self.relations.values() if r["props"]["graph_id"] == graph_id),
            "episodes": sum(1 for e in self.episodes.values() if e["props"]["graph_id"] == graph_id),
        }

    def duplicate_read_entities(self, graph_id, after_uuid, limit):
        self._maybe_fail("read_entities")
        rows = sorted(
            (e for e in self.entities.values() if e["props"]["graph_id"] == graph_id),
            key=lambda e: e["props"]["uuid"],
        )
        return [deepcopy(e) for e in rows if e["props"]["uuid"] > after_uuid][:limit]

    def duplicate_read_episodes(self, graph_id, after_uuid, limit):
        rows = sorted(
            (e for e in self.episodes.values() if e["props"]["graph_id"] == graph_id),
            key=lambda e: e["props"]["uuid"],
        )
        return [deepcopy(e) for e in rows if e["props"]["uuid"] > after_uuid][:limit]

    def duplicate_read_relations(self, graph_id, source_uuids):
        return [
            deepcopy(r)
            for r in self.relations.values()
            if r["props"]["graph_id"] == graph_id and r["source"] in source_uuids
        ]

    # schreiben
    def duplicate_create_graph(self, *, graph_id, name, description, ontology_json, now):
        self._maybe_fail("create_graph")
        self.graphs.setdefault(
            graph_id,
            {
                "graph_id": graph_id,
                "name": name,
                "description": description,
                "ontology_json": ontology_json,
                "created_at": now,
                "status": "building",
            },
        )

    def duplicate_write_entities(self, rows):
        self._maybe_fail("write_entities")
        for row in rows:
            self.entities.setdefault(
                row["uuid"], {"props": deepcopy(row["props"]), "labels": list(row["labels"])}
            )
        return len(rows)

    def duplicate_write_episodes(self, rows):
        self._maybe_fail("write_episodes")
        for row in rows:
            self.episodes.setdefault(row["uuid"], {"props": deepcopy(row["props"])})
        return len(rows)

    def duplicate_write_relations(self, rows):
        self._maybe_fail("write_relations")
        written = 0
        for row in rows:
            if row["source"] in self.entities and row["target"] in self.entities:
                self.relations.setdefault(
                    row["uuid"],
                    {
                        "props": deepcopy(row["props"]),
                        "source": row["source"],
                        "target": row["target"],
                    },
                )
                written += 1
        if written != len(rows):
            raise GraphDuplicateWriteError(f"Beziehungen: {written} von {len(rows)} Zeilen geschrieben")
        return written

    def mark_graph_completed(self, graph_id):
        self._maybe_fail("mark_completed")
        self.graphs[graph_id]["status"] = "completed"

    def mark_graph_incomplete(self, graph_id, reason=None):
        self.graphs[graph_id]["status"] = "incomplete"
        self.graphs[graph_id]["incomplete_reason"] = reason

    def delete_graph(self, graph_id):
        self.calls.append("delete_graph")
        if self.delete_error is not None:
            raise self.delete_error
        self.graphs.pop(graph_id, None)
        for store in (self.entities, self.episodes, self.relations):
            for key in [k for k, v in store.items() if v["props"]["graph_id"] == graph_id]:
                del store[key]


class FakeRegistry:
    def __init__(self) -> None:
        self.runs: Dict[str, Dict[str, Any]] = {}

    def create_run(self, run_type, entity_id, *, run_id=None, status="pending", progress=0,
                   message="", linked_ids=None, metadata=None, **_):
        run = {
            "run_id": run_id, "run_type": run_type, "entity_id": entity_id, "status": status,
            "progress": progress, "message": message, "error": None,
            "linked_ids": linked_ids or {}, "metadata": metadata or {},
        }
        self.runs[run_id] = run
        return deepcopy(run)

    def get_run(self, run_id):
        return deepcopy(self.runs[run_id]) if run_id in self.runs else None

    def update_run(self, run_id, **updates):
        self.runs[run_id].update(updates)
        return deepcopy(self.runs[run_id])


class Jobs:
    """Fängt ``enqueue`` ab; ``run_all`` führt die Jobs synchron aus."""

    def __init__(self) -> None:
        self.queued: List[tuple[str, Callable[..., Any], tuple[Any, ...], Dict[str, Any]]] = []
        self.error: Optional[Exception] = None

    def __call__(self, job_name, target, *args, **kwargs):
        if self.error is not None:
            raise self.error
        self.queued.append((job_name, target, args, kwargs))
        return "job_000000000001"

    def run_all(self) -> None:
        for _name, target, args, kwargs in self.queued:
            kwargs = {k: v for k, v in kwargs.items() if k != "run_id"}
            target(*args, **kwargs)
        self.queued.clear()


# ── Fixtures ────────────────────────────────────────────────────────────


def _entity(uuid_: str, name: str, **extra: Any) -> Dict[str, Any]:
    return {
        "props": {
            "uuid": uuid_, "graph_id": SRC, "name": name, "name_lower": name.lower(),
            "entity_type": "Person", "summary": f"{name} (Person)", "attributes_json": "{}",
            "created_at": NOW, "embedding": [0.25, -0.5, 0.125], **extra,
        },
        "labels": ["Entity", "Person"],
    }


def _relation(uuid_: str, source: str, target: str, **extra: Any) -> Dict[str, Any]:
    return {
        "props": {
            "uuid": uuid_, "graph_id": SRC, "name": "KENNT", "fact": "A kennt B.",
            "fact_embedding": [0.5, 0.5], "episode_ids": [EP[0]], "created_at": NOW, **extra,
        },
        "source": source,
        "target": target,
    }


@pytest.fixture
def storage() -> FakeStorage:
    fake = FakeStorage()
    fake.graphs[SRC] = {
        "graph_id": SRC, "name": "Quelle", "description": "Beschreibung",
        "ontology_json": json.dumps({"entity_types": [{"name": "Person"}]}),
        "created_at": NOW, "status": "completed",
    }
    for index, uuid_ in enumerate(E):
        extra: Dict[str, Any] = {}
        if index == 1:
            extra = {"origin": "manual", "origin_changed_at": NOW}
        fake.entities[uuid_] = _entity(uuid_, f"Person {index}", **extra)
    fake.relations[R[0]] = _relation(R[0], E[0], E[4], origin="manual", origin_changed_at=NOW)
    fake.relations[R[1]] = _relation(R[1], E[4], E[1], episode_ids=[EP[0], EP[1]])
    for uuid_ in EP:
        fake.episodes[uuid_] = {
            "props": {"uuid": uuid_, "graph_id": SRC, "data": "Text", "processed": True,
                      "created_at": NOW, "document_id": "a", "chunk_id": "a#0"}
        }
    return fake


@pytest.fixture(autouse=True)
def projects(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(module, "PAGE_SIZE", 2)  # Seiten erzwingen: 5 Entitäten, 2 Episoden


@pytest.fixture
def source_project(projects):
    project = ProjectManager.create_project("Quellprojekt")
    files_dir = ProjectManager._get_project_files_dir(project.project_id)
    with open(os.path.join(files_dir, "abc12345.txt"), "w", encoding="utf-8") as handle:
        handle.write("Dateiinhalt")
    project.status = ProjectStatus.GRAPH_COMPLETED
    project.graph_id = SRC
    project.ontology = {"entity_types": [{"name": "Person"}], "edge_types": []}
    project.files = [{
        "original_filename": "a.txt", "saved_filename": "abc12345.txt",
        "path": os.path.join(files_dir, "abc12345.txt"), "size": 11,
    }]
    project.total_text_length = 11
    project.simulation_requirement = "Wie reagieren Stadtwerke?"
    project.chunk_size = 321
    ProjectManager.save_project(project)
    ProjectManager.save_extracted_text(project.project_id, "Extrahierter Text")
    ProjectManager.save_document_manifest(
        project.project_id,
        DocumentManifest(documents=[
            DocumentManifestEntry(document_id="a", filename="a.txt", start_offset=0, end_offset=17)
        ]),
    )
    return project


def _make(storage, *, migrating=False):
    registry = FakeRegistry()
    jobs = Jobs()
    service =GraphDuplicateService(
        storage, migration_active=lambda: migrating, registry=registry, enqueue=jobs,
        clock=lambda: NOW,
    )
    return service, registry, jobs


def _request(request_id: str = REQ, name: str = "Meine Kopie") -> GraphDuplicateRequest:
    return GraphDuplicateRequest(client_request_id=request_id, name=name)


def _all_projects():
    return ProjectManager.list_projects(limit=1000)


# ── Erfolg ──────────────────────────────────────────────────────────────


def test_start_returns_pending_job_with_final_ids(storage, source_project):
    service, registry, jobs = _make(storage)

    job = service.start(SRC, _request())

    assert job.status == "pending"
    assert job.source_graph_id == SRC
    assert job.graph_id != SRC
    assert job.run_id.startswith("run_")
    target = ProjectManager.get_project(job.project_id)
    assert target is not None
    assert target.graph_id == job.graph_id
    assert target.name == "Meine Kopie"
    assert target.status == ProjectStatus.GRAPH_BUILDING
    run = registry.get_run(job.run_id)
    assert run["run_type"] == "graph_duplicate"
    assert run["linked_ids"]["project_id"] == job.project_id
    assert len(jobs.queued) == 1
    assert jobs.queued[0][3]["run_id"] == job.run_id


def test_run_copies_graph_with_new_ids_and_keeps_provenance(storage, source_project):
    service, registry, jobs = _make(storage)
    job = service.start(SRC, _request())

    jobs.run_all()

    run = registry.get_run(job.run_id)
    assert (run["status"], run["progress"], run["error"]) == ("completed", 100, None)
    target = storage.graphs[job.graph_id]
    assert (target["name"], target["status"]) == ("Meine Kopie", "completed")
    assert target["description"] == "Beschreibung"
    assert target["ontology_json"] == storage.graphs[SRC]["ontology_json"]

    copied = {k: v for k, v in storage.entities.items() if v["props"]["graph_id"] == job.graph_id}
    assert len(copied) == 5
    assert not set(copied) & set(E)
    assert set(copied) == {mapped_uuid(job.graph_id, "entity", old) for old in E}
    for old in E:
        new = copied[mapped_uuid(job.graph_id, "entity", old)]
        assert new["props"]["uuid"] == mapped_uuid(job.graph_id, "entity", old)
        assert new["props"]["embedding"] == storage.entities[old]["props"]["embedding"]
        assert new["labels"] == ["Entity", "Person"]
    manual = copied[mapped_uuid(job.graph_id, "entity", E[1])]["props"]
    assert (manual["origin"], manual["origin_changed_at"]) == ("manual", NOW)

    relations = {k: v for k, v in storage.relations.items() if v["props"]["graph_id"] == job.graph_id}
    assert len(relations) == 2
    first = relations[mapped_uuid(job.graph_id, "relation", R[0])]
    assert first["source"] == mapped_uuid(job.graph_id, "entity", E[0])
    assert first["target"] == mapped_uuid(job.graph_id, "entity", E[4])
    assert first["props"]["origin"] == "manual"
    assert first["props"]["fact_embedding"] == [0.5, 0.5]
    second = relations[mapped_uuid(job.graph_id, "relation", R[1])]
    assert second["props"]["episode_ids"] == [
        mapped_uuid(job.graph_id, "episode", EP[0]), mapped_uuid(job.graph_id, "episode", EP[1])
    ]

    episodes = {k: v for k, v in storage.episodes.items() if v["props"]["graph_id"] == job.graph_id}
    assert set(episodes) == {mapped_uuid(job.graph_id, "episode", old) for old in EP}
    assert all(e["props"]["document_id"] == "a" for e in episodes.values())

    # Quelle unverändert
    assert len([e for e in storage.entities.values() if e["props"]["graph_id"] == SRC]) == 5
    assert storage.graphs[SRC]["status"] == "completed"


def test_run_copies_project_files_text_manifest_and_fields(storage, source_project):
    service, registry, jobs = _make(storage)
    job = service.start(SRC, _request())

    jobs.run_all()

    target = ProjectManager.get_project(job.project_id)
    assert target is not None
    assert target.status == ProjectStatus.GRAPH_COMPLETED
    assert target.graph_id == job.graph_id
    assert target.ontology == source_project.ontology
    assert target.simulation_requirement == "Wie reagieren Stadtwerke?"
    assert target.chunk_size == 321
    assert target.total_text_length == 11
    target_files = ProjectManager._get_project_files_dir(job.project_id)
    assert target.files[0]["path"] == os.path.join(target_files, "abc12345.txt")
    assert target.files[0]["original_filename"] == "a.txt"
    with open(target.files[0]["path"], encoding="utf-8") as handle:
        assert handle.read() == "Dateiinhalt"
    assert ProjectManager.get_extracted_text(job.project_id) == "Extrahierter Text"
    manifest = ProjectManager.get_document_manifest(job.project_id)
    assert manifest is not None and manifest.documents[0].filename == "a.txt"
    assert not [n for n in os.listdir(target_files) if ".tmp-" in n]
    # Quellprojekt unverändert
    assert ProjectManager.get_project(source_project.project_id).graph_id == SRC  # type: ignore[union-attr]


def test_incomplete_source_stays_incomplete(storage, source_project):
    storage.graphs[SRC]["status"] = "incomplete"
    storage.graphs[SRC]["incomplete_reason"] = "user_cancel"
    service, registry, jobs = _make(storage)
    job = service.start(SRC, _request())

    jobs.run_all()

    assert storage.graphs[job.graph_id]["status"] == "incomplete"
    assert storage.graphs[job.graph_id]["incomplete_reason"] == "user_cancel"
    assert ProjectManager.get_project(job.project_id).status == ProjectStatus.GRAPH_INCOMPLETE  # type: ignore[union-attr]


def test_source_without_project_copies_graph_and_takes_ontology_from_graph(storage):
    service, registry, jobs = _make(storage)
    job = service.start(SRC, _request())

    jobs.run_all()

    assert registry.get_run(job.run_id)["status"] == "completed"
    target = ProjectManager.get_project(job.project_id)
    assert target is not None
    assert target.ontology == {"entity_types": [{"name": "Person"}]}
    assert target.files == []
    assert ProjectManager.get_extracted_text(job.project_id) is None


# ── Wiederholbarkeit ────────────────────────────────────────────────────


def test_same_client_request_id_returns_same_job_and_creates_no_second_copy(storage, source_project):
    service, registry, jobs = _make(storage)

    first = service.start(SRC, _request())
    second = service.start(SRC, _request(name="Anderer Name"))

    assert second.run_id == first.run_id
    assert (second.graph_id, second.project_id) == (first.graph_id, first.project_id)
    assert len(jobs.queued) == 1
    assert len(_all_projects()) == 2  # Quellprojekt + eine Kopie
    jobs.run_all()
    third = service.start(SRC, _request())
    assert third.status == "completed"
    assert third.graph_id == first.graph_id
    assert len([g for g in storage.graphs if g != SRC]) == 1
    assert len(_all_projects()) == 2


def test_same_client_request_id_after_failure_returns_the_failed_job(storage, source_project):
    storage.fail_on = "write_relations"
    service, registry, jobs = _make(storage)
    first = service.start(SRC, _request())
    jobs.run_all()

    again = service.start(SRC, _request())

    assert again.run_id == first.run_id
    assert again.status == "failed"
    assert len(jobs.queued) == 0


def test_new_client_request_id_makes_a_new_copy(storage, source_project):
    service, registry, jobs = _make(storage)

    first = service.start(SRC, _request(REQ))
    second = service.start(SRC, _request(REQ2))

    assert second.run_id != first.run_id
    assert second.graph_id != first.graph_id
    assert second.project_id != first.project_id


def test_replayed_write_of_a_page_does_not_duplicate(storage, source_project):
    """Lost-commit-Retry: dieselben Zeilen zweimal schreiben ändert nichts (MERGE auf der UUID)."""
    service, registry, jobs = _make(storage)
    job = service.start(SRC, _request())
    jobs.run_all()
    before = len(storage.entities)

    rows = [{"uuid": k, "props": v["props"], "labels": v["labels"]}
            for k, v in storage.entities.items() if v["props"]["graph_id"] == job.graph_id]
    assert storage.duplicate_write_entities(rows) == len(rows)

    assert len(storage.entities) == before


# ── Sperre und Migration ────────────────────────────────────────────────


def test_locked_source_can_be_duplicated_and_copy_is_not_locked(storage, source_project):
    records = [SimulationRecord(simulation_id="sim_aaaaaaaaaaaa", project_id=source_project.project_id,
                                graph_id=SRC, status="running")]

    class _Repo:
        def list(self, project_id=None):
            return list(records)

    assert get_graph_lock_state(SRC, repository=_Repo(), project_lister=_all_projects).locked is True
    service, registry, jobs = _make(storage)

    job = service.start(SRC, _request())
    jobs.run_all()

    assert registry.get_run(job.run_id)["status"] == "completed"
    state = get_graph_lock_state(job.graph_id, repository=_Repo(), project_lister=_all_projects)
    assert state.locked is False


def test_embedding_migration_rejects_start_without_side_effects(storage, source_project):
    service, registry, jobs = _make(storage, migrating=True)

    with pytest.raises(EmbeddingMigrationRunningError):
        service.start(SRC, _request())

    assert registry.runs == {}
    assert jobs.queued == []
    assert len(_all_projects()) == 1


def test_missing_source_is_not_found(storage):
    service, registry, jobs = _make(storage)

    with pytest.raises(GraphDuplicateSourceNotFound):
        service.start("99999999-9999-4999-8999-999999999999", _request())

    assert registry.runs == {}
    assert _all_projects() == []


@pytest.mark.parametrize("status", ["building", "failed"])
def test_uncopyable_source_status_is_rejected(storage, status):
    storage.graphs[SRC]["status"] = status
    service, registry, jobs = _make(storage)

    with pytest.raises(GraphDuplicateSourceStateError) as info:
        service.start(SRC, _request())

    assert info.value.status == status
    assert registry.runs == {}
    assert _all_projects() == []


# ── Rollback ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("stage", ["write_episodes", "write_entities", "write_relations", "mark_completed"])
def test_failure_removes_partial_copy_and_fails_the_job(storage, source_project, stage):
    storage.fail_on = stage
    service, registry, jobs = _make(storage)
    job = service.start(SRC, _request())

    jobs.run_all()

    run = registry.get_run(job.run_id)
    assert run["status"] == "failed"
    assert run["error"] == "RuntimeError"
    assert run["termination_reason"] == "error"
    assert job.graph_id not in storage.graphs
    assert not [v for v in storage.entities.values() if v["props"]["graph_id"] == job.graph_id]
    assert not [v for v in storage.episodes.values() if v["props"]["graph_id"] == job.graph_id]
    assert ProjectManager.get_project(job.project_id) is None
    assert not os.path.exists(ProjectManager._get_project_dir(job.project_id))
    assert [p.project_id for p in _all_projects()] == [source_project.project_id]


def test_failure_in_project_copy_rolls_back_and_hides_paths(storage, source_project, monkeypatch):
    def broken_copy(source, target):
        raise OSError(f"Platte voll: {target}")

    monkeypatch.setattr(module, "_copy_file_atomic", broken_copy)
    service, registry, jobs = _make(storage)
    job = service.start(SRC, _request())

    jobs.run_all()

    run = registry.get_run(job.run_id)
    assert (run["status"], run["error"]) == ("failed", "OSError")
    assert job.graph_id not in storage.graphs
    assert ProjectManager.get_project(job.project_id) is None


def test_count_mismatch_after_write_fails_the_job(storage, source_project):
    storage.count_override = {"entities": 4, "relations": 2, "episodes": 2}
    service, registry, jobs = _make(storage)
    job = service.start(SRC, _request())

    jobs.run_all()

    run = registry.get_run(job.run_id)
    assert run["status"] == "failed"
    assert "Entitäten 4 von 5" in run["error"]
    assert job.graph_id not in storage.graphs


def test_failed_cleanup_is_reported_in_the_job_error(storage, source_project):
    storage.fail_on = "write_relations"
    storage.delete_error = RuntimeError("Neo4j nicht erreichbar")
    service, registry, jobs = _make(storage)
    job = service.start(SRC, _request())

    jobs.run_all()

    run = registry.get_run(job.run_id)
    assert run["status"] == "failed"
    assert "Aufräumen unvollständig: Zielgraph" in run["error"]
    assert ProjectManager.get_project(job.project_id) is None  # das Projekt wurde trotzdem entfernt


def test_enqueue_failure_removes_project_and_fails_the_run(storage, source_project):
    service, registry, jobs = _make(storage)
    jobs.error = RuntimeError("Thread-Start fehlgeschlagen")

    with pytest.raises(RuntimeError):
        service.start(SRC, _request())

    (run,) = registry.runs.values()
    assert run["status"] == "failed"
    assert [p.project_id for p in _all_projects()] == [source_project.project_id]


def test_mapped_uuid_is_stable_and_depends_on_graph_kind_and_source():
    a = mapped_uuid("g1", "entity", E[0])
    assert a == mapped_uuid("g1", "entity", E[0])
    assert len({a, mapped_uuid("g2", "entity", E[0]), mapped_uuid("g1", "relation", E[0]),
                mapped_uuid("g1", "entity", E[1])}) == 4
