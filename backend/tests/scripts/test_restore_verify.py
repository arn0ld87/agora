"""Tests fuer die Restore-Verifikation (Issue #766).

Die Pruefpunkte spiegeln die Checkliste aus ``docs/backup-restore.md``. Getestet
wird gegen kuenstliche Restore-Verzeichnisse — der Drill selbst braucht einen
frischen Host und ist damit nicht Gegenstand dieser Tests.

Wichtigster Punkt: ein *uebersprungener* Pruefpunkt darf niemals als Erfolg
durchgehen. Genau daran scheitern Prosa-Checklisten.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "restore_verify.py"


@pytest.fixture(scope="module")
def verify():
    spec = importlib.util.spec_from_file_location("restore_verify", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["restore_verify"] = module
    spec.loader.exec_module(module)
    return module


def _install(tmp_path: Path, *, run_status: str = "completed") -> Path:
    """Ein plausibel restauriertes Datenverzeichnis."""
    data = tmp_path / "uploads"
    registry = data / "run_registry"
    registry.mkdir(parents=True)
    (registry / "run_a.json").write_text(
        json.dumps(
            {"run_id": "run_a", "run_type": "simulation_run", "status": run_status}
        ),
        encoding="utf-8",
    )
    sim = data / "simulations" / "sim_0123456789ab"
    sim.mkdir(parents=True)
    (sim / "state.json").write_text("{}", encoding="utf-8")
    reports = data / "reports" / "report_1"
    reports.mkdir(parents=True)
    (reports / "report.json").write_text("{}", encoding="utf-8")
    (data / "provider_connections.json").write_text(
        json.dumps({"connections": [{"id": "conn_1"}]}), encoding="utf-8"
    )
    return data


def _named(report, name: str):
    return next(c for c in report.checks if c.name == name)


class TestHealthyRestore:
    def test_a_complete_restore_passes(self, verify, tmp_path) -> None:
        report = verify.run_verification(_install(tmp_path))

        assert report.failed == []

    def test_exit_code_is_zero(self, verify, tmp_path, capsys) -> None:
        assert verify.main(["--data-dir", str(_install(tmp_path))]) == 0

    def test_json_output_is_machine_readable(self, verify, tmp_path, capsys) -> None:
        verify.main(["--data-dir", str(_install(tmp_path)), "--json"])

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["checks"]


class TestBrokenRestoreIsCaught:
    def test_missing_data_dir_fails(self, verify, tmp_path) -> None:
        report = verify.run_verification(tmp_path / "nope")

        assert report.failed
        assert verify.main(["--data-dir", str(tmp_path / "nope")]) == 1

    def test_a_run_still_marked_running_fails(self, verify, tmp_path) -> None:
        """Der Kern der Reconciliation-Zusage: ein restaurierter Host darf
        keinen historischen Prozess als laufend vortaeuschen."""
        report = verify.run_verification(_install(tmp_path, run_status="processing"))

        check = _named(report, "Kein Run steht faelschlich auf laufend")
        assert check.ok is False
        assert "run_a" in check.detail

    def test_corrupt_manifest_fails(self, verify, tmp_path) -> None:
        data = _install(tmp_path)
        (data / "run_registry" / "run_b.json").write_text("{not json", encoding="utf-8")

        report = verify.run_verification(data)

        assert _named(report, "Run-Manifeste sind gueltiges JSON").ok is False

    def test_empty_registry_fails(self, verify, tmp_path) -> None:
        data = _install(tmp_path)
        (data / "run_registry" / "run_a.json").unlink()

        report = verify.run_verification(data)

        assert _named(report, "RunRegistry enthaelt mindestens einen Run").ok is False


class TestSkipIsNotSuccess:
    def test_a_skipped_check_never_counts_as_passed(self, verify, tmp_path) -> None:
        data = _install(tmp_path)
        (data / "provider_connections.json").unlink()

        report = verify.run_verification(data)
        check = _named(report, "ProviderConnections vorhanden")

        assert check.skipped is True
        assert check.ok is False

    def test_the_summary_names_skipped_checks(self, verify, tmp_path) -> None:
        data = _install(tmp_path)
        (data / "provider_connections.json").unlink()

        rendered = verify.render(verify.run_verification(data))

        assert "uebersprungen" in rendered
        assert "SKIP" in rendered

    def test_secret_check_is_skipped_without_the_key(self, verify, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv("AGORA_SECRET_KEY", raising=False)

        report = verify.run_verification(_install(tmp_path))

        assert _named(report, "Secret-Store entschluesselbar").skipped is True


class TestProtocolIsEvidence:
    def test_report_carries_a_timestamp(self, verify, tmp_path) -> None:
        assert verify.run_verification(_install(tmp_path)).started_at

    def test_every_check_names_its_checklist_section(self, verify, tmp_path) -> None:
        report = verify.run_verification(_install(tmp_path))

        assert {c.section for c in report.checks} == {
            "Artefakte",
            "Reconciliation",
            "Provider/Secrets",
        }

    def test_no_secret_value_reaches_the_protocol(self, verify, tmp_path, monkeypatch) -> None:
        """Das Protokoll wird an Issues geheftet — es darf nie einen Klartext
        tragen, auch nicht versehentlich ueber eine Fehlermeldung."""
        data = _install(tmp_path)
        (data / "provider_connections.json").write_text(
            json.dumps({"connections": [{"id": "conn_1", "secret_ref": "ref_1"}]}),
            encoding="utf-8",
        )
        monkeypatch.setenv("AGORA_SECRET_KEY", "x" * 32)
        monkeypatch.setattr(
            "app.services.llm_provider_secrets_store.get_llm_provider_secrets_store",
            lambda: type(
                "S", (), {"get_plaintext": lambda _s, _r: "SUPERSECRETVALUE"}
            )(),
        )

        rendered = verify.render(verify.run_verification(data))

        assert "SUPERSECRETVALUE" not in rendered
