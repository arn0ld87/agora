"""Tests fuer ``scripts/restore-drill.sh`` (Issue #766).

Der Drill selbst braucht einen frischen Host, ein echtes Backup und einen
Docker-Daemon — er laeuft hier nicht. Was hier laeuft, ist der *Ablauf*: dass
die Phasen in der dokumentierten Reihenfolge stehen, dass jeder Schritt im
Protokoll landet, dass ein fehlgeschlagener Pruefpunkt den Drill rot faerbt und
dass ein Dry-Run sich nicht als Nachweis ausgibt.

Damit ist das Skript geprueft, der Betriebsnachweis aber ausdruecklich nicht
erbracht — siehe ``docs/runbooks/restore-drill.md``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DRILL = REPO_ROOT / "scripts" / "restore-drill.sh"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(DRILL), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
    )


@pytest.fixture()
def restored(tmp_path: Path) -> Path:
    """Ein plausibel restauriertes Datenverzeichnis."""
    data = tmp_path / "uploads"
    (data / "run_registry").mkdir(parents=True)
    (data / "run_registry" / "run_a.json").write_text(
        json.dumps({"run_id": "run_a", "run_type": "simulation_run", "status": "completed"}),
        encoding="utf-8",
    )
    (data / "simulations" / "sim_0123456789ab").mkdir(parents=True)
    (data / "reports" / "r1").mkdir(parents=True)
    (data / "reports" / "r1" / "report.json").write_text("{}", encoding="utf-8")
    (data / "provider_connections.json").write_text(
        json.dumps({"connections": [{"id": "conn_1"}]}), encoding="utf-8"
    )
    return data


class TestInvocation:
    def test_script_is_syntactically_valid(self) -> None:
        assert subprocess.run(["bash", "-n", str(DRILL)]).returncode == 0

    def test_script_is_executable(self) -> None:
        assert DRILL.stat().st_mode & 0o111

    def test_missing_backup_dir_is_a_usage_error(self, tmp_path) -> None:
        assert _run("--phase", "verify").returncode == 2

    def test_unknown_phase_is_a_usage_error(self, tmp_path) -> None:
        result = _run("--phase", "nonsense", "--backup-dir", str(tmp_path))

        assert result.returncode == 2
        assert "Unbekannte Phase" in result.stderr


class TestDryRunCoversEveryPhase:
    def test_all_five_phases_run_in_the_documented_order(self, tmp_path) -> None:
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "all",
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", str(tmp_path / "uploads"),
            "--protocol", str(protocol),
            "--upgrade-ref", "v0.9.5",
            "--rollback-ref", "v0.9.4",
            "--dry-run",
        )

        assert result.returncode == 0
        text = protocol.read_text(encoding="utf-8")
        order = [
            text.index("Phase 1/5 — Backup"),
            text.index("Phase 2/5 — Restore"),
            text.index("Phase 3/5 — Verifikation"),
            text.index("Phase 4/5 — Upgrade"),
            text.index("Phase 5/5 — Rollback"),
        ]
        assert order == sorted(order), "Phasen nicht in dokumentierter Reihenfolge"

    def test_a_dry_run_says_it_is_not_evidence(self, tmp_path) -> None:
        """Der wichtigste Satz im Protokoll: sonst landet ein Dry-Run-Log als
        vermeintlicher Betriebsnachweis am Issue."""
        protocol = tmp_path / "drill.log"

        _run(
            "--phase", "all",
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", str(tmp_path / "uploads"),
            "--protocol", str(protocol),
            "--dry-run",
        )

        assert "KEIN Betriebsnachweis" in protocol.read_text(encoding="utf-8")

    def test_a_dry_run_executes_nothing(self, tmp_path) -> None:
        backup = tmp_path / "backup"

        _run(
            "--phase", "backup",
            "--backup-dir", str(backup),
            "--data-dir", str(tmp_path / "uploads"),
            "--protocol", str(tmp_path / "drill.log"),
            "--dry-run",
        )

        assert not backup.exists()

    def test_every_command_is_written_to_the_protocol(self, tmp_path) -> None:
        protocol = tmp_path / "drill.log"

        _run(
            "--phase", "restore",
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", str(tmp_path / "uploads"),
            "--protocol", str(protocol),
            "--dry-run",
        )

        text = protocol.read_text(encoding="utf-8")
        assert "docker compose down" in text
        assert "neo4j-admin database load" in text

    def test_upgrade_and_rollback_are_skipped_without_a_ref(self, tmp_path) -> None:
        protocol = tmp_path / "drill.log"

        _run(
            "--phase", "all",
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", str(tmp_path / "uploads"),
            "--protocol", str(protocol),
            "--dry-run",
        )

        text = protocol.read_text(encoding="utf-8")
        assert "übersprungen: --upgrade-ref nicht gesetzt" in text
        assert "übersprungen: --rollback-ref nicht gesetzt" in text


class TestVerifyPhaseIsReal:
    """Diese Phase laeuft wirklich — sie braucht kein Docker."""

    def test_a_healthy_restore_passes(self, tmp_path, restored) -> None:
        result = _run(
            "--phase", "verify",
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", str(restored),
            "--protocol", str(tmp_path / "drill.log"),
        )

        assert result.returncode == 0, result.stdout + result.stderr

    def test_a_run_still_marked_running_fails_the_drill(self, tmp_path, restored) -> None:
        """Genau die Zusage aus docs/backup-restore.md: ein restaurierter Host
        darf keinen historischen Prozess als laufend vortaeuschen."""
        (restored / "run_registry" / "run_b.json").write_text(
            json.dumps(
                {"run_id": "run_b", "run_type": "simulation_prepare", "status": "processing"}
            ),
            encoding="utf-8",
        )
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "verify",
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", str(restored),
            "--protocol", str(protocol),
        )

        assert result.returncode == 1
        assert "FEHLGESCHLAGEN: Restore-Verifikation" in protocol.read_text(encoding="utf-8")
