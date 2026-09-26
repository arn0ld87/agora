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
import textwrap
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
    """Codex-Befund P1 auf PR #1498, seit #1633 gegen den Offline-Weg erneuert:
    ``agora-neo4j`` mountet kein ``/backups`` und Neo4j Community kann eine
    laufende Datenbank ohnehin nicht laden. ``docker compose down`` nimmt den
    Container mit; erst ``create`` legt einen neuen (nicht gestarteten) an,
    gegen den der Wegwerf-Container per ``--volumes-from`` laden kann. Dieselbe
    Schutzabsicht wie zuvor: der Dump erreicht die Lade-Umgebung, und das Laden
    passiert erst danach — nur eben ohne den Zwischenschritt ``exec`` gegen
    einen laufenden Dienst."""

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

    def test_no_exec_against_a_running_service_remains(self, tmp_path) -> None:
        text = self._protocol(tmp_path)

        assert "docker compose exec -T neo4j neo4j-admin" not in text

    def test_the_offline_container_mounts_the_backup_directory(self, tmp_path) -> None:
        text = self._protocol(tmp_path)

        assert "--volumes-from" in text
        assert ":/backups" in text

    def test_the_container_exists_before_the_offline_load(self, tmp_path) -> None:
        """``--volumes-from`` braucht einen existierenden Zielcontainer — ohne
        ``create`` zuvor gaebe es keine Volumes, gegen die der Wegwerf-
        Container laden koennte."""
        text = self._protocol(tmp_path)

        assert text.index("docker compose create neo4j") < text.index(
            "neo4j-admin database load"
        )


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

    ``compose ps ... -q`` liefert eine feste Fake-Container-ID, ``inspect``
    je nach ``--format``-Vorlage entweder ein Fake-Image oder — gesteuert
    ueber ``DOCKER_STUB_CONFIG_FILES`` — den Inhalt des
    ``com.docker.compose.project.config_files``-Labels (#1633-Nachtrag).
    ``run ... neo4j-admin database dump`` legt die Dump-Datei im gemounteten
    Host-Pfad an (aus dem ``-v <host>:/backups``-Argument geparst) und
    scheitert, wenn ``DOCKER_STUB_FAIL_DUMP=1`` gesetzt ist; ``database load``
    ist immer erfolgreich. Jeder ``run``-Aufruf protokolliert sein komplettes
    argv (eine Zeile je Argument) nach ``<stub_dir>/last-docker-run-argv.txt``
    — Regressionsschutz dafuer, dass ``--volumes-from`` tatsaechlich eine
    einzeilige Container-ID bekommt und nicht mehrzeiligen Log-Muell aus einer
    Command Substitution.
    """
    stub_dir = tmp_path / "stubbin"
    stub_dir.mkdir(exist_ok=True)
    docker = stub_dir / "docker"
    secret_echo = f'echo "{secret_line}"\n' if secret_line else ""
    script = (
        "#!/bin/sh\n"
        + secret_echo
        + textwrap.dedent(
            """
            case "$1" in
              compose)
                shift
                case "$1" in
                  ps)
                    echo "fake-neo4j-container-id"
                    exit 0
                    ;;
                  *)
                    exit 0
                    ;;
                esac
                ;;
              inspect)
                case "$3" in
                  *config_files*)
                    printf '%s' "${DOCKER_STUB_CONFIG_FILES:-}"
                    exit 0
                    ;;
                esac
                echo "fake-neo4j-image:5.26-community"
                exit 0
                ;;
              run)
                argv_log="$(dirname "$0")/last-docker-run-argv.txt"
                : > "$argv_log"
                for arg in "$@"; do
                  printf '%s\\n' "$arg" >> "$argv_log"
                done
                host_backups=""
                prev=""
                for arg in "$@"; do
                  if [ "$prev" = "-v" ]; then
                    host_backups="$arg"
                  fi
                  prev="$arg"
                done
                host_dir="${host_backups%%:*}"
                case "$*" in
                  *"database dump"*)
                    if [ -n "$DOCKER_STUB_FAIL_DUMP" ]; then
                      exit 1
                    fi
                    : > "$host_dir/neo4j.dump"
                    exit 0
                    ;;
                  *"database load"*)
                    exit 0
                    ;;
                esac
                exit 0
                ;;
              *)
                exit 0
                ;;
            esac
            """
        )
    )
    docker.write_text(script, encoding="utf-8")
    docker.chmod(0o755)
    return stub_dir


def _real_backup(
    tmp_path: Path,
    stub_bin: Path,
    env: dict[str, str | None] | None = None,
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

    merged_env: dict[str, str | None] = {"PATH": f"{stub_bin}:{os.environ['PATH']}"}
    merged_env.update(env or {})

    result = _run(
        "--phase", "backup",
        "--backup-dir", str(backup),
        "--data-dir", str(uploads),
        "--store-dir", str(data),
        "--instance-dir", str(instance),
        "--protocol", str(protocol),
        env=merged_env,
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


class TestComposeFileOverlayGuard:
    """Nachtrag zu #1633: Der reale Zielhost (armserver) faehrt den Stack mit
    vier Compose-Dateien (docker-compose.yml, docker-compose.prod.yml,
    docker-compose.meinserver.yml, deploy/compose/docker-compose.codex-cli.yml).
    Ohne gesetztes COMPOSE_FILE legt ein nacktes ``docker compose
    down``/``create``/``up`` den neo4j-Container nur mit der Default-Datei neu
    an und verliert die Overlays (Ports, Mounts) still."""

    def test_restore_refuses_without_compose_file_when_the_container_used_several(
        self, tmp_path
    ) -> None:
        stub = _docker_stub(tmp_path)
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "restore",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
            "--protocol", str(protocol),
            env={
                "PATH": f"{stub}:{os.environ['PATH']}",
                "COMPOSE_FILE": None,
                "DOCKER_STUB_CONFIG_FILES": "docker-compose.yml,docker-compose.prod.yml",
            },
        )

        assert result.returncode == 1
        text = protocol.read_text(encoding="utf-8")
        assert "COMPOSE_FILE" in text
        assert "docker compose down" not in text

    def test_restore_proceeds_past_the_guard_when_compose_file_is_set(
        self, tmp_path
    ) -> None:
        """Mit gesetztem COMPOSE_FILE lässt der Guard den Lauf weiterlaufen —
        ein spaeterer Abbruch (hier: fehlende Archive, das Backup-Verzeichnis
        ist leer) ist nicht der Guard, sondern ein anderer, unabhaengiger
        Pruefpunkt."""
        stub = _docker_stub(tmp_path)
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "restore",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
            "--protocol", str(protocol),
            env={
                "PATH": f"{stub}:{os.environ['PATH']}",
                "COMPOSE_FILE": "docker-compose.yml:docker-compose.prod.yml",
                "DOCKER_STUB_CONFIG_FILES": "docker-compose.yml,docker-compose.prod.yml",
            },
        )

        text = protocol.read_text(encoding="utf-8")
        assert "docker compose down" in text
        assert "wurde mit mehreren Compose-Dateien erzeugt" not in text
        assert result.returncode == 1
        assert "Backup fehlt" in text

    def test_dry_run_only_warns_without_compose_file(self, tmp_path) -> None:
        """Der Dry-Run braucht keinen Docker-Daemon — die Pruefung selbst
        greift nicht auf echte Container zu, sondern warnt pauschal."""
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "restore",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
            "--protocol", str(protocol),
            "--dry-run",
            env={"COMPOSE_FILE": None},
        )

        assert result.returncode == 0, result.stdout + result.stderr
        text = protocol.read_text(encoding="utf-8")
        assert "COMPOSE_FILE" in text
        assert "Phase 2/5" in text


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


class TestNeo4jOfflineDumpAndLoad:
    """#1633: ``agora-neo4j`` mountet kein ``/backups``, und Neo4j Community
    kann eine laufende Datenbank ohnehin nicht dumpen/laden. Backup und
    Restore fahren Neo4j deshalb ueber einen Wegwerf-Container mit
    ``--volumes-from`` statt ``docker compose exec`` gegen den laufenden
    Dienst."""

    def test_backup_dry_run_stops_dumps_offline_then_restarts(self, tmp_path) -> None:
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "backup",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
            "--protocol", str(protocol),
            "--dry-run",
        )

        assert result.returncode == 0, result.stdout + result.stderr
        text = protocol.read_text(encoding="utf-8")
        assert "docker compose exec -T neo4j neo4j-admin" not in text
        order = [
            text.index("docker compose stop neo4j"),
            text.index("--volumes-from"),
            text.index("neo4j-admin database dump"),
            text.index("docker compose start neo4j"),
        ]
        assert order == sorted(order), "Reihenfolge stop/dump/start nicht eingehalten"

    def test_backup_dry_run_uses_placeholders_for_container_and_image(
        self, tmp_path
    ) -> None:
        protocol = tmp_path / "drill.log"

        _run(
            "--phase", "backup",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
            "--protocol", str(protocol),
            "--dry-run",
        )

        text = protocol.read_text(encoding="utf-8")
        assert "<neo4j-container>" in text
        assert "<neo4j-image>" in text

    def test_restore_dry_run_creates_container_before_offline_load_then_ups(
        self, tmp_path
    ) -> None:
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "restore",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
            "--protocol", str(protocol),
            "--dry-run",
        )

        assert result.returncode == 0, result.stdout + result.stderr
        text = protocol.read_text(encoding="utf-8")
        assert "docker compose exec -T neo4j neo4j-admin" not in text
        order = [
            text.index("docker compose create neo4j"),
            text.index("--volumes-from"),
            text.index("neo4j-admin database load"),
            text.index("docker compose up -d"),
        ]
        assert order == sorted(order), "Reihenfolge create/load/up nicht eingehalten"

    def test_the_volumes_from_argument_is_a_single_line_container_id(
        self, tmp_path
    ) -> None:
        """Regression: ``log()`` schreibt ueber ``tee`` auch auf stdout. Wurde
        es innerhalb der Command Substitution fuer ``cid``/``image`` benutzt,
        landeten Log-Zeilen IM Rueckgabewert, und ``docker run
        --volumes-from`` bekam mehrzeiligen Text statt der reinen
        Container-ID — der Stub ignoriert Argumente und haette das nicht
        bemerkt."""
        stub = _docker_stub(tmp_path)
        backup, result = _real_backup(tmp_path, stub)

        assert result.returncode == 0, result.stdout + result.stderr
        argv = (stub / "last-docker-run-argv.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        idx = argv.index("--volumes-from")
        assert argv[idx + 1] == "fake-neo4j-container-id"

    def test_real_backup_writes_the_dump_into_the_manifest(self, tmp_path) -> None:
        stub = _docker_stub(tmp_path)
        backup, result = _real_backup(tmp_path, stub)

        assert result.returncode == 0, result.stdout + result.stderr
        assert (backup / "neo4j" / "neo4j.dump").is_file()
        manifest = (backup / "MANIFEST.sha256").read_text(encoding="utf-8")
        assert "neo4j/neo4j.dump" in manifest

    def test_a_failed_dump_still_restarts_neo4j_and_still_runs_the_postgres_backup(
        self, tmp_path
    ) -> None:
        """C) aus der Spec: PostgreSQL-Backup ist unabhaengig vom Neo4j-Schritt
        — ein Neo4j-Fehlschlag darf das PostgreSQL-Backup nicht verhindern,
        und Neo4j muss trotzdem wieder anlaufen."""
        stub = _docker_stub(tmp_path)

        backup, result = _real_backup(
            tmp_path,
            stub,
            env={
                "DOCKER_STUB_FAIL_DUMP": "1",
                "AGORA_METADATA_BACKEND": None,
                "AGORA_LLM_PROFILE_BACKEND": None,
                "AGORA_PROJECT_BACKEND": None,
                "DATABASE_URL": None,
            },
        )

        assert result.returncode == 1
        text = (tmp_path / "backup.log").read_text(encoding="utf-8")
        assert "docker compose start neo4j" in text
        pg_index = text.index("PostgreSQL-Backup uebersprungen")
        fail_index = text.index("FEHLGESCHLAGEN")
        assert pg_index < fail_index, "PostgreSQL-Backup muss vor dem Fehlschlag laufen"


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

    def test_a_corrupted_neo4j_dump_fails_the_restore_before_loading(
        self, tmp_path
    ) -> None:
        """Dieselbe Prüfsummen-Pflicht gilt für ``neo4j/neo4j.dump`` (#1633) —
        ein beschaedigter Dump darf nicht in den Wegwerf-Container geladen
        werden."""
        stub = _docker_stub(tmp_path)
        backup, backup_result = _real_backup(tmp_path, stub)
        assert backup_result.returncode == 0, backup_result.stdout + backup_result.stderr

        with (backup / "neo4j" / "neo4j.dump").open("ab") as fh:
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
    _ACTIVE_POSTGRES_ENV = {
        "AGORA_PROJECT_BACKEND": "postgres",
        "DATABASE_URL": "postgresql+psycopg://user:geheim@127.0.0.1:5432/agora",
    }

    _NO_POSTGRES_ENV = {
        "AGORA_METADATA_BACKEND": None,
        "AGORA_LLM_PROFILE_BACKEND": None,
        "AGORA_PROJECT_BACKEND": None,
        "DATABASE_URL": None,
    }

    def test_postgres_restore_runs_before_the_application_starts(self, tmp_path) -> None:
        """Codex-Review auf #1602: der PostgreSQL-Restore gehoert in die
        Restore-Phase vor ``docker compose up -d`` — sonst startet die App
        gegen ein leeres oder halb restauriertes Schema."""
        protocol = tmp_path / "drill.log"

        result = _run(
            "--phase", "all",
            "--backup-dir", str(tmp_path / "backup"),
            *_targets(tmp_path),
            "--protocol", str(protocol),
            "--dry-run",
            env=self._ACTIVE_POSTGRES_ENV,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        text = protocol.read_text(encoding="utf-8")
        restore = text.index("Phase 2/5 — Restore")
        pg_restore = text.index("pg_restore --host=", restore)
        app_start = text.index("$ docker compose up -d\n", restore)
        verify = text.index("Phase 3/5 — Verifikation")
        assert restore < pg_restore < app_start < verify

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
        assert "PostgreSQL-Restore uebersprungen: kein AGORA_*_BACKEND=postgres aktiv" in text
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
        assert "-n agora -Fc --snapshot=" in text
        assert "postgres-manifest.json" in text
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
        assert "alembic stamp" in text
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

    def test_verify_omits_the_manifest_option_for_an_old_verifier(self, tmp_path) -> None:
        """Codex-Review auf #1602: nach ``--rollback-ref`` auf einen Stand vor
        #1583 kennt restore_verify.py ``--postgres-manifest`` nicht. Das
        Skript reicht die Option nur weiter, wenn der Pruefer sie kennt."""
        script = (REPO_ROOT / "scripts" / "restore-drill.sh").read_text(encoding="utf-8")

        assert "grep -q -- '--postgres-manifest'" in script
        assert 'verify_args+=(--postgres-manifest' in script


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
