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


def _targets(tmp_path: Path) -> list[str]:
    """Alle drei Zielverzeichnisse auf verwerfbare Pfade.

    Ohne sie zeigen ``--store-dir`` und ``--instance-dir`` auf den eigenen
    Checkout, und der Restore bricht ab (``guard_restore_target``). Genau dieser
    Halbfehler — ein Pfad gesetzt, zwei vergessen — stand vorher in diesen
    Tests.
    """
    return [
        "--data-dir", str(tmp_path / "uploads"),
        "--store-dir", str(tmp_path / "data"),
        "--instance-dir", str(tmp_path / "instance"),
    ]


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
            *_targets(tmp_path),
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
            *_targets(tmp_path),
            "--protocol", str(protocol),
            "--dry-run",
        )

        assert "KEIN Betriebsnachweis" in protocol.read_text(encoding="utf-8")

    def test_a_dry_run_executes_nothing(self, tmp_path) -> None:
        backup = tmp_path / "backup"

        _run(
            "--phase", "backup",
            "--backup-dir", str(backup),
            *_targets(tmp_path),
            "--protocol", str(tmp_path / "drill.log"),
            "--dry-run",
        )

        assert not backup.exists()

    def test_every_command_is_written_to_the_protocol(self, tmp_path) -> None:
        protocol = tmp_path / "drill.log"

        _run(
            "--phase", "restore",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
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
            *_targets(tmp_path),
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
            *_targets(tmp_path),
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
            *_targets(tmp_path),
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


def _docker_stub(tmp_path: Path, secret_line: str | None = None) -> Path:
    """Ein ``docker``-Stub, der ``docker compose ...`` ohne echten Daemon gruen
    macht.

    ``phase_backup``/``phase_restore`` rufen echten Docker auf; ohne Daemon
    scheitert jeder nicht-dry Testlauf am ersten ``docker compose``-Aufruf,
    bevor Manifest, Rechte oder Pruefsumme ueberhaupt entstehen. Optional gibt
    der Stub eine Zeile auf stdout aus, um die Redaktion im echten ``run()``-Pfad
    zu pruefen.
    """
    stub_dir = tmp_path / "stubbin"
    stub_dir.mkdir(exist_ok=True)
    docker = stub_dir / "docker"
    body = "#!/bin/sh\n"
    if secret_line:
        body += f'echo "{secret_line}"\n'
    body += "exit 0\n"
    docker.write_text(body, encoding="utf-8")
    docker.chmod(0o755)
    return stub_dir


def _real_backup(
    tmp_path: Path, stub_bin: Path
) -> tuple[Path, subprocess.CompletedProcess]:
    """Fuehrt ``--phase backup`` echt (nicht dry) gegen tmp-Verzeichnisse aus."""
    backup = tmp_path / "backup"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    instance = tmp_path / "instance"
    instance.mkdir()
    protocol = tmp_path / "backup.log"

    result = _run(
        "--phase", "backup",
        "--backup-dir", str(backup),
        "--data-dir", str(uploads),
        "--store-dir", str(data),
        "--instance-dir", str(instance),
        "--protocol", str(protocol),
        env={"PATH": f"{stub_bin}:{os.environ['PATH']}"},
    )
    return backup, result


class TestGuardRestoreTarget:
    """Codex-Befund aus dem Phase-0-Audit (docs/plans/supabase.md §6): ein
    ``--phase restore`` ohne explizite Zielpfade ueberschrieb bislang
    ``backend/data``, ``backend/instance`` und ``backend/uploads`` des
    Rechners, auf dem der Drill laeuft."""

    def test_restore_without_explicit_targets_refuses_to_write_into_the_checkout(
        self, tmp_path
    ) -> None:
        """Verhindert, dass ein Restore ohne --data-dir/--store-dir/--instance-dir
        den eigenen Checkout des Betreibers ueberschreibt."""
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "restore",
            "--backup-dir", str(tmp_path / "backup"),
            "--protocol", str(protocol),
        )

        assert result.returncode == 1
        text = protocol.read_text(encoding="utf-8")
        assert "Restore würde in den eigenen Checkout schreiben" in text

    @pytest.mark.parametrize(
        "target",
        [
            "backend/uploads",
            str(REPO_ROOT / "backend" / ".." / "backend" / "uploads"),
        ],
        ids=["relativ", "punkt-punkt"],
    )
    def test_the_guard_resolves_paths_before_it_compares_them(
        self, tmp_path, target: str
    ) -> None:
        """Ein Zeichenkettenvergleich haette genau die Schreibweise durchgelassen,
        die der Skriptkopf selbst vorschlaegt — ``--data-dir backend/uploads``
        loest zur Laufzeit auf den eigenen Checkout auf."""
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "restore",
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", target,
            "--store-dir", str(tmp_path / "data"),
            "--instance-dir", str(tmp_path / "instance"),
            "--protocol", str(protocol),
        )

        assert result.returncode == 1
        assert "Restore würde in den eigenen Checkout schreiben" in protocol.read_text(
            encoding="utf-8"
        )

    def test_a_symlink_into_the_checkout_is_caught(self, tmp_path) -> None:
        """Der Pfadstring liegt ausserhalb, das Ziel nicht — ohne Aufloesung
        waere das der bequemste Weg am Guard vorbei."""
        link = tmp_path / "sieht-harmlos-aus"
        link.symlink_to(REPO_ROOT / "backend" / "uploads")
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "restore",
            "--backup-dir", str(tmp_path / "backup"),
            "--data-dir", str(link),
            "--store-dir", str(tmp_path / "data"),
            "--instance-dir", str(tmp_path / "instance"),
            "--protocol", str(protocol),
        )

        assert result.returncode == 1
        assert "Restore würde in den eigenen Checkout schreiben" in protocol.read_text(
            encoding="utf-8"
        )

    def test_allow_repo_target_bypasses_the_guard(self, tmp_path) -> None:
        """Der explizite Opt-out fuer den frischen Host, auf dem der Checkout
        selbst das Ziel ist, darf den Guard tatsaechlich umgehen."""
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "restore",
            "--backup-dir", str(tmp_path / "backup"),
            "--allow-repo-target",
            "--protocol", str(protocol),
            "--dry-run",
        )

        text = protocol.read_text(encoding="utf-8")
        assert result.returncode == 0
        assert "Phase 2/5" in text
        assert "Restore würde in den eigenen Checkout schreiben" not in text

    def test_explicit_disposable_targets_bypass_the_guard(self, tmp_path) -> None:
        """Der Normalfall — alle drei Ziele explizit auf ein verwerfbares
        Verzeichnis gesetzt — darf ebenfalls ohne Guard-Abbruch laufen."""
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "restore",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
            "--protocol", str(protocol),
            "--dry-run",
        )

        text = protocol.read_text(encoding="utf-8")
        assert result.returncode == 0
        assert "Restore würde in den eigenen Checkout schreiben" not in text


class TestBackupManifestAndPermissions:
    """Codex-Befund aus dem Phase-0-Audit: ein durch volle Platte oder Bitrot
    beschaedigtes Archiv durchlief das Backup bislang unbemerkt gruen, und die
    Archive selbst trugen Fernet-Stores und Klartext-API-Keys ohne
    eingeschraenkte Dateirechte."""

    def test_backup_writes_a_checksum_manifest_for_every_archive(
        self, tmp_path
    ) -> None:
        """Verhindert, dass ein durch abgebrochenes tar beschaedigtes Archiv
        ohne Pruefsumme in den Restore wandert."""
        stub = _docker_stub(tmp_path)
        backup, result = _real_backup(tmp_path, stub)

        assert result.returncode == 0, result.stdout + result.stderr
        manifest = (backup / "MANIFEST.sha256").read_text(encoding="utf-8")
        assert "uploads.tar.gz" in manifest
        assert "data.tar.gz" in manifest
        assert "instance.tar.gz" in manifest

    def test_backup_directory_and_archives_are_not_world_or_group_readable(
        self, tmp_path
    ) -> None:
        """Verhindert, dass die Fernet-Stores und Klartext-API-Keys im Backup
        fuer andere Systemnutzer lesbar auf der Platte liegen."""
        stub = _docker_stub(tmp_path)
        backup, result = _real_backup(tmp_path, stub)

        assert result.returncode == 0, result.stdout + result.stderr
        assert (backup.stat().st_mode & 0o777) == 0o700
        archives = list(backup.glob("*.tar.gz"))
        assert archives, "keine Archive erzeugt"
        for archive in archives:
            assert (archive.stat().st_mode & 0o777) == 0o600


class TestRestoreRejectsCorruptedArchive:
    def test_a_corrupted_archive_fails_the_restore_instead_of_silently_loading(
        self, tmp_path
    ) -> None:
        """Verhindert, dass ein durch Bitrot oder abgebrochenes tar
        beschaedigtes Archiv unbemerkt zurueckgespielt wird und den
        Restore-Host mit kaputten Daten befuellt."""
        stub = _docker_stub(tmp_path)
        backup, backup_result = _real_backup(tmp_path, stub)
        assert backup_result.returncode == 0, backup_result.stdout + backup_result.stderr

        with (backup / "data.tar.gz").open("ab") as fh:
            fh.write(b"\x00\x00corrupt-append")

        protocol = tmp_path / "restore.log"
        result = _run(
            "--phase", "restore",
            "--backup-dir", str(backup),
            "--data-dir", str(tmp_path / "uploads"),
            "--store-dir", str(tmp_path / "data"),
            "--instance-dir", str(tmp_path / "instance"),
            "--protocol", str(protocol),
            env={"PATH": f"{stub}:{os.environ['PATH']}"},
        )

        assert result.returncode == 1
        assert "Prüfsumme weicht ab" in protocol.read_text(encoding="utf-8")


class TestPostgresBackupAndRestore:
    """PostgreSQL-Phasen (#1583). Ein echter pg_dump/pg_restore-Durchlauf
    braucht eine erreichbare Datenbank — der lebt in
    ``backend/tests/integration/test_postgres_backup_restore.py``. Hier laeuft
    nur der Ablauf: Skip ohne aktiven Postgres-Backend, Dry-Run-Kommandos mit
    aktivem Backend, und dass ohne ``DATABASE_URL`` hart fehlgeschlagen wird
    statt stillschweigend uebersprungen."""

    #: Kein AGORA_*_BACKEND=postgres, keine DATABASE_URL — der Normalfall, in
    #: dem dieses Skript heute lief (Default ueberall Legacy).
    _NO_POSTGRES_ENV = {
        "AGORA_METADATA_BACKEND": None,
        "AGORA_LLM_PROFILE_BACKEND": None,
        "AGORA_PROJECT_BACKEND": None,
        "DATABASE_URL": None,
    }

    def test_pg_restore_is_part_of_the_documented_all_sequence(self, tmp_path) -> None:
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "all",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
            "--protocol", str(protocol),
            "--dry-run",
            env=self._NO_POSTGRES_ENV,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        text = protocol.read_text(encoding="utf-8")
        order = [
            text.index("Phase 1/5 — Backup"),
            text.index("Phase 2/5 — Restore"),
            text.index("PostgreSQL-Restore (#1583)"),
            text.index("Phase 3/5 — Verifikation"),
        ]
        assert order == sorted(order), "pg_restore steht nicht zwischen Restore und Verifikation"

    def test_pg_restore_is_a_no_op_without_an_active_postgres_backend(
        self, tmp_path
    ) -> None:
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "pg_restore",
            "--backup-dir", str(tmp_path / "backup"),
            "--protocol", str(protocol),
            "--dry-run",
            env=self._NO_POSTGRES_ENV,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        text = protocol.read_text(encoding="utf-8")
        assert "uebersprungen: kein AGORA_*_BACKEND=postgres aktiv" in text
        assert "pg_restore --host=" not in text

    def test_backup_skips_postgres_without_an_active_backend(self, tmp_path) -> None:
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "backup",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
            "--protocol", str(protocol),
            "--dry-run",
            env=self._NO_POSTGRES_ENV,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        text = protocol.read_text(encoding="utf-8")
        assert "PostgreSQL-Backup uebersprungen: kein AGORA_*_BACKEND=postgres aktiv" in text
        assert "pg_dump --host=" not in text

    def test_backup_shows_the_pg_dump_command_when_a_backend_is_active(
        self, tmp_path
    ) -> None:
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "backup",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
            "--protocol", str(protocol),
            "--dry-run",
            env={
                "AGORA_PROJECT_BACKEND": "postgres",
                "DATABASE_URL": "postgresql+psycopg://user:geheim@127.0.0.1:5432/agora",
            },
        )

        assert result.returncode == 0, result.stdout + result.stderr
        text = protocol.read_text(encoding="utf-8")
        assert "Aktive PostgreSQL-Backends: PROJECT_BACKEND" in text
        assert "pg_dump --host=" in text
        assert "-n agora -Fc" in text
        assert "postgres_backup_manifest.py" in text
        # Das Passwort aus DATABASE_URL darf im Dry-Run nirgendwo auftauchen —
        # die Zerlegung ueber pg_cli laeuft im Dry-Run erst gar nicht.
        assert "geheim" not in text

    def test_pg_restore_shows_the_command_when_a_backend_is_active(
        self, tmp_path
    ) -> None:
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "pg_restore",
            "--backup-dir", str(tmp_path / "backup"),
            "--protocol", str(protocol),
            "--dry-run",
            env={
                "AGORA_PROJECT_BACKEND": "postgres",
                "DATABASE_URL": "postgresql+psycopg://user:geheim@127.0.0.1:5432/agora",
            },
        )

        assert result.returncode == 0, result.stdout + result.stderr
        text = protocol.read_text(encoding="utf-8")
        assert "pg_restore --host=" in text
        assert "--clean --if-exists" in text
        assert "geheim" not in text

    def test_backup_fails_hard_when_active_but_database_url_is_missing(
        self, tmp_path
    ) -> None:
        """Ein aktiver Postgres-Schalter ohne DATABASE_URL ist ein
        Konfigurationsfehler, kein Grund zum stillen Uebergehen."""
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "backup",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
            "--protocol", str(protocol),
            "--dry-run",
            env={"AGORA_PROJECT_BACKEND": "postgres", "DATABASE_URL": None},
        )

        assert result.returncode == 1
        assert "DATABASE_URL ist nicht gesetzt" in protocol.read_text(encoding="utf-8")


class TestRedaction:
    def test_a_bearer_token_never_reaches_the_protocol(self, tmp_path) -> None:
        """Verhindert, dass ein per Copy-Paste in ``run()`` geratener
        ``Authorization: Bearer``-Header das Backend-Token im weitergegebenen
        Protokoll offenlegt."""
        stub = _docker_stub(tmp_path, secret_line="Authorization: Bearer geheim123")
        _, result = _real_backup(tmp_path, stub)
        assert result.returncode == 0, result.stdout + result.stderr

        text = (tmp_path / "backup.log").read_text(encoding="utf-8")
        assert "[REDACTED]" in text
        assert "geheim123" not in text

    def test_a_key_inside_a_json_body_is_redacted_too(self, tmp_path) -> None:
        """Die haeufigste Form, in der ein Schluessel auftaucht. Das Muster
        erfasste den Wert erst nach dem oeffnenden Anfuehrungszeichen nicht —
        ein JSON-Koerper lief unveraendert ins Protokoll."""
        stub = _docker_stub(
            tmp_path, secret_line='{"api_key": "sk-nichtinsprotokoll"}'
        )
        _, result = _real_backup(tmp_path, stub)
        assert result.returncode == 0, result.stdout + result.stderr

        text = (tmp_path / "backup.log").read_text(encoding="utf-8")
        assert "[REDACTED]" in text
        assert "sk-nichtinsprotokoll" not in text
