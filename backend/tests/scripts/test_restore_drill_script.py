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
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DRILL = REPO_ROOT / "scripts" / "restore-drill.sh"


def _run(
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str | None] | None = None,
) -> subprocess.CompletedProcess:
    environ = dict(os.environ)
    for key, value in (env or {}).items():
        if value is None:
            environ.pop(key, None)
        else:
            environ[key] = value
    return subprocess.run(
        ["bash", str(DRILL), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
        env=environ,
    )


@pytest.fixture()
def restored(tmp_path: Path) -> Path:
    """Ein plausibel restauriertes Artefaktverzeichnis (``backend/uploads``)."""
    data = tmp_path / "uploads"
    (data / "run_registry").mkdir(parents=True)
    (data / "run_registry" / "run_a.json").write_text(
        json.dumps({"run_id": "run_a", "run_type": "simulation_run", "status": "completed"}),
        encoding="utf-8",
    )
    (data / "simulations" / "sim_0123456789ab").mkdir(parents=True)
    (data / "reports" / "r1").mkdir(parents=True)
    (data / "reports" / "r1" / "report.json").write_text("{}", encoding="utf-8")
    return data


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    """Das Store-Verzeichnis (``backend/data``, ``AGORA_DATA_DIR``).

    ``provider_connections.json`` liegt hier, NICHT unter ``uploads`` — siehe
    ``app/services/data_dir.py::resolve_data_dir``.
    """
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "provider_connections.json").write_text(
        json.dumps({"version": 1, "connections": {"conn_1": {"id": "conn_1"}}}),
        encoding="utf-8",
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


class TestBackupCoversEveryPersistedDirectory:
    """Codex-Befund P1 auf PR #1498. ``docs/backup-restore.md`` listet drei
    Verzeichnisse mit Kritikalitaet „hoch": ``backend/uploads`` (Artefakte),
    ``backend/data`` (Provider-/Routing-/App-Stores) und ``backend/instance``
    (Instanzsettings). Ein Backup, das nur das erste erfasst, laesst nach dem
    Restore genau die Stores fehlen, die der Pruefer belegen soll."""

    def _protocol(self, tmp_path: Path, phase: str) -> str:
        protocol = tmp_path / "drill.log"
        _run(
            "--phase", phase,
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", str(tmp_path / "uploads"),
            "--store-dir", str(tmp_path / "data"),
            "--instance-dir", str(tmp_path / "instance"),
            "--protocol", str(protocol),
            "--dry-run",
        )
        return protocol.read_text(encoding="utf-8")

    @pytest.mark.parametrize("archive", ["uploads.tar.gz", "data.tar.gz", "instance.tar.gz"])
    def test_backup_writes_every_archive(self, tmp_path, archive: str) -> None:
        assert archive in self._protocol(tmp_path, "backup")

    @pytest.mark.parametrize("archive", ["uploads.tar.gz", "data.tar.gz", "instance.tar.gz"])
    def test_restore_reads_every_archive(self, tmp_path, archive: str) -> None:
        assert archive in self._protocol(tmp_path, "restore")

    def test_restore_follows_the_documented_recovery_order(self, tmp_path) -> None:
        """docs/backup-restore.md, „Recovery-Reihenfolge": data, instance,
        uploads, dann Neo4j."""
        text = self._protocol(tmp_path, "restore")

        order = [
            text.index("data.tar.gz"),
            text.index("instance.tar.gz"),
            text.index("uploads.tar.gz"),
            text.index("neo4j-admin database load"),
        ]
        assert order == sorted(order)


class TestNeo4jDumpReachesTheNewContainer:
    """Codex-Befund P1 auf PR #1498. ``docker compose down`` nimmt den
    Container mit; der neue startet mit einem leeren ``/backups``. Ein
    ``neo4j-admin database load --from-path=/backups`` ohne vorheriges
    Zurueckkopieren laedt nichts — und der Drill meldete das als erledigt."""

    def _protocol(self, tmp_path: Path) -> str:
        protocol = tmp_path / "drill.log"
        _run(
            "--phase", "restore",
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", str(tmp_path / "uploads"),
            "--protocol", str(protocol),
            "--dry-run",
        )
        return protocol.read_text(encoding="utf-8")

    def test_the_dump_is_copied_into_the_container(self, tmp_path) -> None:
        text = self._protocol(tmp_path)

        assert "docker compose cp" in text
        assert "neo4j:/backups" in text

    def test_the_copy_happens_before_the_load(self, tmp_path) -> None:
        text = self._protocol(tmp_path)

        assert text.index("neo4j:/backups") < text.index("neo4j-admin database load")

    def test_the_container_is_up_before_the_copy(self, tmp_path) -> None:
        """``docker compose cp`` in einen nicht existierenden Service schlaegt
        fehl — die Reihenfolge up, cp, load ist die einzige, die traegt."""
        text = self._protocol(tmp_path)

        assert text.index("docker compose up -d neo4j") < text.index("neo4j:/backups")


class TestVerifyPhaseIsReal:
    """Diese Phase laeuft wirklich — sie braucht kein Docker."""

    def test_a_healthy_restore_passes(self, tmp_path, restored, store, monkeypatch) -> None:
        result = _run(
            "--phase", "verify",
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", str(restored),
            "--store-dir", str(store),
            "--protocol", str(tmp_path / "drill.log"),
            env={"AGORA_SECRET_KEY": "x" * 32},
        )

        assert result.returncode == 0, result.stdout + result.stderr

    def test_a_run_still_marked_running_fails_the_drill(
        self, tmp_path, restored, store
    ) -> None:
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
            "--store-dir", str(store),
            "--protocol", str(protocol),
            env={"AGORA_SECRET_KEY": "x" * 32},
        )

        assert result.returncode == 1
        assert "FEHLGESCHLAGEN: Restore-Verifikation" in protocol.read_text(encoding="utf-8")

    def test_an_unproven_verification_does_not_pass_the_drill(
        self, tmp_path, restored, store
    ) -> None:
        """Codex-Befund P1 auf PR #1498: ``restore_verify.py`` liest nur seinen
        Exit-Code, und ein uebersprungener Pruefpunkt ergab dort 0. Ohne
        ``AGORA_SECRET_KEY`` bleibt der Secret-Store ungeprueft — der Drill darf
        das nicht als Nachweis verbuchen."""
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "verify",
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", str(restored),
            "--store-dir", str(store),
            "--protocol", str(protocol),
            env={"AGORA_SECRET_KEY": None},
        )

        assert result.returncode == 1
        assert "nicht belegt" in protocol.read_text(encoding="utf-8")

    def test_the_store_directory_is_where_the_secret_check_looks(
        self, tmp_path, restored, store
    ) -> None:
        """``provider_connections.json`` liegt in ``backend/data``. Ein Drill,
        der dem Pruefer nur ``uploads`` zeigt, ueberspringt den gesamten
        Provider/Secrets-Abschnitt und merkt es nicht."""
        protocol = tmp_path / "drill.log"

        _run(
            "--phase", "verify",
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", str(restored),
            "--store-dir", str(store),
            "--protocol", str(protocol),
            env={"AGORA_SECRET_KEY": "x" * 32},
        )

        text = protocol.read_text(encoding="utf-8")
        assert "OK    ProviderConnections vorhanden" in text
        assert "SKIP  ProviderConnections vorhanden" not in text
