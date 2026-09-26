"""Regressionstests für die ZIP-Export-Allowlist (Issue #1680, Folge #1274 Punkt 7).

``GET /api/runs/<run_id>/export`` darf nur explizit allowlistete Artefakte
ausliefern. Diese Tests sichern die drei Akzeptanzkriterien des Issues:

1. Secret-Sentinel: Nicht-allowlistete Dateien (``.env``, ``secrets.json``,
   beliebige andere Namen) landen NICHT im ZIP — ZIP-Listing exakt geprüft.
2. Alle erlaubten Artefakte (inkl. ``stages/``) werden weiter exportiert.
3. Symlinks auf Dateien außerhalb des Run-Verzeichnisses werden nie
   exportiert — auch nicht unter einem allowlisteten Namen.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Any

import pytest
from flask import Flask

from app.api import runs_bp
from app.config import Config
from app.services.artifact_store import InMemoryArtifactStore
from app.services.manifest_capture import ManifestCapture
from app.services.run_registry import RunRegistry


SENTINEL = "ago-test-sentinel-1680-do-not-leak"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Flask-Test-App mit RunRegistry, Run-Verzeichnis unter tmp_path."""
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(upload_root / "run_registry"))
    monkeypatch.setenv("AGORA_INSTANCE_DIR", str(tmp_path))
    RunRegistry._instance = None
    os.makedirs(RunRegistry.REGISTRY_DIR, exist_ok=True)

    app = Flask(__name__)
    app.extensions = {"artifact_store": InMemoryArtifactStore()}
    app.register_blueprint(runs_bp, url_prefix="/api/runs")

    registry = RunRegistry()

    yield {
        "app": app,
        "client": app.test_client(),
        "registry": registry,
        "tmp_path": tmp_path,
    }

    RunRegistry._instance = None


def _create_run_with_manifest(registry: RunRegistry, tmp_path: Any) -> tuple[str, str]:
    """Erzeugt einen Run mit Manifest; liefert (run_id, run_dir)."""
    run = registry.create_run(
        run_type="simulation_run",
        entity_id="sim_test",
        status="completed",
        message="Test run",
        linked_ids={"simulation_id": "sim_test", "project_id": "proj_test"},
        metadata={},
    )
    run_id = run["run_id"]
    run_dir = str(tmp_path / "runs" / run_id)
    ManifestCapture.capture_draft(
        run_id=run_id,
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
    return run_id, run_dir


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _export_zip(client: Any, run_id: str) -> zipfile.ZipFile:
    resp = client.get(f"/api/runs/{run_id}/export")
    assert resp.status_code == 200, resp.get_json() if resp.status_code != 200 else None
    return zipfile.ZipFile(io.BytesIO(resp.data))


def _export_report(zf: zipfile.ZipFile) -> dict[str, Any]:
    return json.loads(zf.read("export-report.json").decode("utf-8"))


def _skipped_paths(report: dict[str, Any], reason: str) -> set[str]:
    return {
        entry["path"] for entry in report["skipped"] if entry["reason"] == reason
    }


def test_export_excludes_non_allowlisted_files_and_reports_them(env):
    """Akzeptanz 1: Nicht-allowlistete Dateien (inkl. Secret-Sentinel) landen
    nicht im ZIP; das Listing wird exakt geprüft, das Weglassen ist im
    export-report.json sichtbar gemeldet."""
    run_id, run_dir = _create_run_with_manifest(env["registry"], env["tmp_path"])
    _write(os.path.join(run_dir, ".env"), f"API_KEY={SENTINEL}\n")
    _write(os.path.join(run_dir, "secrets.json"), json.dumps({"token": SENTINEL}))
    _write(os.path.join(run_dir, "stray_notes.txt"), f"note {SENTINEL}")

    zf = _export_zip(env["client"], run_id)

    assert set(zf.namelist()) == {"manifest.json", "export-report.json"}
    for content in [zf.read(name) for name in zf.namelist()]:
        assert SENTINEL.encode("utf-8") not in content

    report = _export_report(zf)
    assert report["run_id"] == run_id
    assert report["exported"] == ["manifest.json"]
    assert _skipped_paths(report, "not_in_allowlist") == {
        ".env",
        "secrets.json",
        "stray_notes.txt",
    }


def test_export_includes_all_allowed_artifacts(env):
    """Akzeptanz 2: Jedes Allowlist-Muster wird weiterhin exportiert — auch
    die stages/-Snapshots (Bug_019 bleibt gesichert); transiente Writer-Tmp-
    Dateien und unbenannte stages-Dateien bleiben draußen."""
    run_id, run_dir = _create_run_with_manifest(env["registry"], env["tmp_path"])
    _write(os.path.join(run_dir, "runtime_llm_routing.json"), "{}")
    _write(os.path.join(run_dir, "llm_call_events.jsonl"), "{}\n")
    _write(os.path.join(run_dir, "usage_summary.json"), "{}")
    _write(os.path.join(run_dir, "budget_warnings.json"), "[]")
    _write(os.path.join(run_dir, "stages", "graph_ingestion_llm_route_snapshot.json"), "{}")
    _write(
        os.path.join(run_dir, "stages", "persona_generation_ai_route_snapshot.json"), "{}"
    )
    # Bewusst nicht erlauben: unbekannte stages-Datei und Writer-Tmp-Datei.
    _write(os.path.join(run_dir, "stages", "unexpected.json"), "{}")
    _write(os.path.join(run_dir, "usage_summary.json.tmp"), "{}")

    zf = _export_zip(env["client"], run_id)

    assert set(zf.namelist()) == {
        "manifest.json",
        "export-report.json",
        "runtime_llm_routing.json",
        "llm_call_events.jsonl",
        "usage_summary.json",
        "budget_warnings.json",
        "stages/graph_ingestion_llm_route_snapshot.json",
        "stages/persona_generation_ai_route_snapshot.json",
    }
    report = _export_report(zf)
    assert report["exported"] == sorted(set(zf.namelist()) - {"export-report.json"})
    assert _skipped_paths(report, "not_in_allowlist") == {
        "stages/unexpected.json",
        "usage_summary.json.tmp",
    }


def test_export_never_follows_symlinks_outside_run_dir(env):
    """Akzeptanz 3: Symlinks auf Dateien außerhalb des Run-Verzeichnisses
    werden nie exportiert — selbst dann nicht, wenn ihr Name die Allowlist
    matcht (TOCTOU: das Ziel könnte außerhalb liegen oder wechseln)."""
    run_id, run_dir = _create_run_with_manifest(env["registry"], env["tmp_path"])
    outside_path = str(env["tmp_path"] / "outside_secret.txt")
    _write(outside_path, SENTINEL)

    os.symlink(outside_path, os.path.join(run_dir, ".env"))
    os.makedirs(os.path.join(run_dir, "stages"), exist_ok=True)
    os.symlink(
        outside_path,
        os.path.join(run_dir, "stages", "fake_llm_route_snapshot.json"),
    )

    resp = env["client"].get(f"/api/runs/{run_id}/export")
    assert resp.status_code == 200
    assert SENTINEL.encode("utf-8") not in resp.data

    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    names = set(zf.namelist())
    assert ".env" not in names
    assert "stages/fake_llm_route_snapshot.json" not in names
    assert names == {"manifest.json", "export-report.json"}

    report = _export_report(zf)
    assert _skipped_paths(report, "symlink") == {
        ".env",
        "stages/fake_llm_route_snapshot.json",
    }
    assert report["exported"] == ["manifest.json"]
