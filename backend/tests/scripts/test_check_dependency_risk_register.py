"""Contract-Tests für backend/scripts/check_dependency_risk_register.py.

Prüft CLI-Verhalten gegen temporäre JSON-Fixtures.
Aufrufe via subprocess.run — wir testen den Vertrag, nicht Internals.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPT_PATH = _REPO_ROOT / "backend" / "scripts" / "check_dependency_risk_register.py"

_VALID_ENTRY: dict = {
    "advisory_id": "CVE-2099-9999",
    "package": "example-pkg",
    "version_constraint": "==1.0.0",
    "severity": "Medium",
    "reason": "Upstream hat noch keinen Fix veröffentlicht, Pin notwendig.",
    "blocker": "https://github.com/example/example-pkg/releases",
    "target_version": "example-pkg>=1.1.0",
    "owner": "team-security",
    "deadline": "2099-12-31",
    "issue": "https://github.com/arn0ld87/agora/issues/999",
    "status": "open",
    "source": "dependency",
    "evidence": "https://github.com/advisories/GHSA-aaaa-bbbb-cccc",
    "approved_by": "arn0ld87",
}


def _write_exceptions(tmp_path: Path, entries: list[dict]) -> Path:
    data = {"exceptions": entries}
    p = tmp_path / "dependency-risk-exceptions.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _run(exceptions_file: Path, *, date: str | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT_PATH), "--exceptions-file", str(exceptions_file)]
    if date:
        cmd += ["--date", date]
    return subprocess.run(cmd, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# 1. Valide Ausnahme mit Deadline in der Zukunft → Exit 0
# ---------------------------------------------------------------------------


def test_valid_future_deadline_exits_zero(tmp_path: Path) -> None:
    p = _write_exceptions(tmp_path, [_VALID_ENTRY])
    result = _run(p, date="2026-01-01")
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "OK:" in result.stdout


# ---------------------------------------------------------------------------
# 2. Abgelaufene Deadline (today > deadline) → Exit 1, Fehlermeldung in stderr
# ---------------------------------------------------------------------------


def test_expired_deadline_exits_one(tmp_path: Path) -> None:
    expired_entry = {**_VALID_ENTRY, "deadline": "2020-01-01"}
    p = _write_exceptions(tmp_path, [expired_entry])
    result = _run(p, date="2026-06-10")
    assert result.returncode == 1, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "ABGELAUFEN" in result.stderr
    assert "CVE-2099-9999" in result.stderr


# ---------------------------------------------------------------------------
# 3. Mehrere Ausnahmen: eine abgelaufen → Exit 1, andere intakt
# ---------------------------------------------------------------------------


def test_mixed_entries_one_expired(tmp_path: Path) -> None:
    expired_entry = {**_VALID_ENTRY, "advisory_id": "CVE-2020-0001", "deadline": "2020-06-01"}
    valid_entry = {**_VALID_ENTRY, "advisory_id": "CVE-2099-0002", "deadline": "2099-01-01"}
    p = _write_exceptions(tmp_path, [expired_entry, valid_entry])
    result = _run(p, date="2026-06-10")
    assert result.returncode == 1
    assert "CVE-2020-0001" in result.stderr
    assert "CVE-2099-0002" not in result.stderr


# ---------------------------------------------------------------------------
# 4. status == "resolved" → Deadline wird nicht geprüft
# ---------------------------------------------------------------------------


def test_resolved_entry_not_deadline_checked(tmp_path: Path) -> None:
    resolved_entry = {**_VALID_ENTRY, "deadline": "2020-01-01", "status": "resolved"}
    p = _write_exceptions(tmp_path, [resolved_entry])
    result = _run(p, date="2026-06-10")
    assert result.returncode == 0, f"stderr={result.stderr!r}"


# ---------------------------------------------------------------------------
# 5. Fehlende Pflichtfelder → Exit 1, Fehlerbeschreibung in stderr
# ---------------------------------------------------------------------------


def test_missing_required_fields_exits_one(tmp_path: Path) -> None:
    incomplete = {"advisory_id": "CVE-2099-0003", "package": "missing-fields"}
    p = _write_exceptions(tmp_path, [incomplete])
    result = _run(p)
    assert result.returncode == 1
    assert "Pflichtfelder" in result.stderr


# ---------------------------------------------------------------------------
# 6. Leere exceptions-Liste → Exit 0 (kein Fehler, kein open entry)
# ---------------------------------------------------------------------------


def test_empty_exceptions_list_exits_zero(tmp_path: Path) -> None:
    p = _write_exceptions(tmp_path, [])
    result = _run(p, date="2026-06-10")
    assert result.returncode == 0
    assert "OK:" in result.stdout


# ---------------------------------------------------------------------------
# 7. Datei existiert nicht → Exit 1 mit Fehlermeldung
# ---------------------------------------------------------------------------


def test_missing_file_exits_one(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does-not-exist.json"
    result = _run(nonexistent)
    assert result.returncode == 1
    assert "nicht gefunden" in result.stderr


# ---------------------------------------------------------------------------
# 8. Ungültiges JSON → Exit 1
# ---------------------------------------------------------------------------


def test_invalid_json_exits_one(tmp_path: Path) -> None:
    p = tmp_path / "broken.json"
    p.write_text("{not valid json", encoding="utf-8")
    result = _run(p)
    assert result.returncode == 1
    assert "JSON-Fehler" in result.stderr


# ---------------------------------------------------------------------------
# 9. Ungültiges Deadline-Format → Exit 1
# ---------------------------------------------------------------------------


def test_invalid_deadline_format_exits_one(tmp_path: Path) -> None:
    bad_date_entry = {**_VALID_ENTRY, "deadline": "30.07.2026"}  # DE-Format, kein ISO
    p = _write_exceptions(tmp_path, [bad_date_entry])
    result = _run(p, date="2026-01-01")
    assert result.returncode == 1
    assert "Ungültiges Deadline-Format" in result.stderr


# ---------------------------------------------------------------------------
# 10. Deadline genau heute → noch nicht abgelaufen (Grenzbedingung)
# ---------------------------------------------------------------------------


def test_deadline_today_not_expired(tmp_path: Path) -> None:
    today_entry = {**_VALID_ENTRY, "deadline": "2026-06-10"}
    p = _write_exceptions(tmp_path, [today_entry])
    result = _run(p, date="2026-06-10")
    assert result.returncode == 0, f"stderr={result.stderr!r}"


@pytest.mark.parametrize("source", ["dependency", "code", "container"])
def test_supported_source_with_evidence_is_accepted(tmp_path: Path, source: str) -> None:
    result = _run(_write_exceptions(tmp_path, [{**_VALID_ENTRY, "source": source, "image": "supabase/postgres:17.6.1.136"}]), date="2026-01-01")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("field", ["source", "evidence", "owner", "deadline", "approved_by"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_invalid_acceptance_metadata_fails_closed(tmp_path: Path, field: str, value: object) -> None:
    entry = {**_VALID_ENTRY, field: value}
    result = _run(_write_exceptions(tmp_path, [entry]), date="2026-01-01")
    assert result.returncode == 1, result.stdout


@pytest.mark.parametrize("field", ["evidence", "owner", "deadline", "approved_by"])
def test_missing_acceptance_metadata_fails_closed(tmp_path: Path, field: str) -> None:
    entry = {**_VALID_ENTRY}
    del entry[field]
    result = _run(_write_exceptions(tmp_path, [entry]), date="2026-01-01")
    assert result.returncode == 1, result.stdout


@pytest.mark.parametrize("change", [
    {"source": "unsupported"}, {"approved_by": "other-user"},
    {"source": "container", "severity": "Critical"},
    {"status": "dismissed", "dismissal_reason": ""},
    {"status": "dismissed", "dismissal_reason": "accepted_risk"},
])
def test_policy_violation_fails_closed(tmp_path: Path, change: dict) -> None:
    result = _run(_write_exceptions(tmp_path, [{**_VALID_ENTRY, **change}]), date="2026-01-01")
    assert result.returncode == 1, result.stdout


def test_documented_false_positive_is_accepted(tmp_path: Path) -> None:
    entry = {**_VALID_ENTRY, "status": "dismissed", "dismissal_reason": "false_positive"}
    result = _run(_write_exceptions(tmp_path, [entry]), date="2026-01-01")
    assert result.returncode == 0, result.stderr


def _run_trivy(tmp_path: Path, entries: list[dict], *, severity: str = "HIGH", artifact: str = "supabase/postgres:17.6.1.136") -> subprocess.CompletedProcess[str]:
    report = tmp_path / "trivy.json"
    report.write_text(json.dumps({"ArtifactName": artifact, "Results": [{"Vulnerabilities": [{
        "VulnerabilityID": "CVE-2099-9999", "PkgName": "example-pkg",
        "InstalledVersion": "1.0.0", "Severity": severity,
    }]}]}), encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT_PATH), "--exceptions-file",
        str(_write_exceptions(tmp_path, entries)), "--date", "2026-01-01",
        "--trivy-report", str(report)], capture_output=True, text=True)


def test_trivy_container_finding_requires_matching_image_exception(tmp_path: Path) -> None:
    entry = {**_VALID_ENTRY, "source": "container", "severity": "High", "image": "supabase/postgres:17.6.1.136"}
    assert _run_trivy(tmp_path, [entry]).returncode == 0
    assert _run_trivy(tmp_path, [{**entry, "image": "supabase/gotrue:v2.188.1"}]).returncode == 1
    assert _run_trivy(tmp_path, [{**entry, "version_constraint": "==0.9.0"}]).returncode == 1
    assert _run_trivy(tmp_path, [{**entry, "source": "dependency"}]).returncode == 1
    assert _run_trivy(tmp_path, []).returncode == 1


def test_trivy_critical_cannot_use_real_risk_exception(tmp_path: Path) -> None:
    entry = {**_VALID_ENTRY, "source": "container", "severity": "High", "image": "supabase/postgres:17.6.1.136"}
    assert _run_trivy(tmp_path, [entry], severity="CRITICAL").returncode == 1


def test_trivy_malformed_report_fails_closed(tmp_path: Path) -> None:
    report = tmp_path / "trivy.json"
    report.write_text("{}", encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT_PATH), "--exceptions-file",
        str(_write_exceptions(tmp_path, [])), "--trivy-report", str(report)], capture_output=True, text=True)
    assert result.returncode == 1


@pytest.mark.parametrize("reference", ["supabase/postgres", "supabase/postgres:latest", "supabase/postgres:nightly", "${IMAGE}", "${POSTGRES_IMAGE:-supabase/postgres:latest}"])
def test_workflow_inventory_rejects_unpinned_refs(tmp_path: Path, reference: str) -> None:
    import yaml

    workflow = yaml.safe_load((_REPO_ROOT / ".github/workflows/cve-monitor.yml").read_text())
    steps = workflow["jobs"]["supabase-images"]["steps"]
    script = next(step["run"] for step in steps if step["name"] == "Derive pinned Supabase image inventory")
    script = script.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    (tmp_path / "supabase").mkdir()
    (tmp_path / "supabase/docker-compose.yml").write_text(f"services:\n  db:\n    image: {reference}\n")
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0


def test_workflow_scans_and_gates_every_image_without_suppression() -> None:
    import yaml

    workflow = yaml.safe_load((_REPO_ROOT / ".github/workflows/cve-monitor.yml").read_text())
    steps = workflow["jobs"]["supabase-images"]["steps"]
    scan = next(step["run"] for step in steps if step["name"] == "Scan every tracked Supabase image")
    assert 'for i in "${!images[@]}"' in scan
    assert '--ignore-unfixed=false --ignorefile /dev/null --exit-code 0' in scan
    assert 'check_dependency_risk_register.py "${reports[@]}"' in scan
    assert not any(step.get("continue-on-error") for step in steps)


def test_workflow_inventory_and_scan_happy_path(tmp_path: Path) -> None:
    import os
    import yaml

    workflow = yaml.safe_load((_REPO_ROOT / ".github/workflows/cve-monitor.yml").read_text())
    steps = workflow["jobs"]["supabase-images"]["steps"]
    inventory = next(step["run"] for step in steps if step["name"] == "Derive pinned Supabase image inventory")
    inventory = inventory.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    inventory_path = tmp_path / "images.txt"
    inventory = inventory.replace("/tmp/supabase-images.txt", str(inventory_path))
    result = subprocess.run([sys.executable, "-c", inventory], cwd=_REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    images = inventory_path.read_text().splitlines()
    compose = yaml.safe_load((_REPO_ROOT / "supabase/docker-compose.yml").read_text())
    expected = [service["image"].split(":-", 1)[1].removesuffix("}") for service in compose["services"].values() if "image" in service]
    assert images == list(dict.fromkeys(expected))
    assert len(images) >= 9

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "calls.jsonl"
    trivy = fake_bin / "trivy"
    trivy.write_text(f"#!{sys.executable}\n" +
        "import json, sys\nfrom pathlib import Path\n" +
        f"with Path({str(calls)!r}).open('a') as f: f.write(json.dumps(sys.argv[1:]) + chr(10))\n" +
        "Path(sys.argv[sys.argv.index('--output')+1]).write_text(json.dumps({'ArtifactName': sys.argv[-1], 'Results': []}))\n")
    trivy.chmod(0o755)
    exceptions = _write_exceptions(tmp_path, [])
    uv = fake_bin / "uv"
    uv.write_text(f"#!{sys.executable}\n" +
        "import os, sys\n" +
        f"os.execv({sys.executable!r}, [{sys.executable!r}, {str(SCRIPT_PATH)!r}, '--exceptions-file', {str(exceptions)!r}] + sys.argv[sys.argv.index('scripts/check_dependency_risk_register.py')+1:])\n")
    uv.chmod(0o755)
    scan = next(step["run"] for step in steps if step["name"] == "Scan every tracked Supabase image")
    scan = scan.replace("/tmp/supabase-images.txt", str(inventory_path))
    env = {**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", "")}
    result = subprocess.run(["/bin/bash", "-c", scan], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    scans = [json.loads(line) for line in calls.read_text().splitlines()]
    assert [call[-1] for call in scans] == images
    assert len(list((tmp_path / "supabase-scan").glob("*.json"))) == len(images)
    assert all(call[0] == "image" and "--ignore-unfixed=false" in call for call in scans)
