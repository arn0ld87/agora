"""Der Playwright-Install ueberlebt einen ausgefallenen Ubuntu-Mirror.

Zwei PRs nacheinander wurden am 2026-08-18 von einem Host rot gemacht, der
nichts mit Agora zu tun hat: ``playwright install --with-deps`` zieht
Font-Pakete von den Ubuntu-Mirrors, und bei nicht erreichbarem
``azure.archive.ubuntu.com`` bricht apt mit Exit 100 ab.

Diese Tests halten die Wiederholungs-Mechanik fest. Sie ist nur wertvoll,
solange sie tatsaechlich wiederholt — eine spaeter entfernte Schleife faellt
sonst niemandem auf, bis der naechste Mirror ausfaellt.

``npx``, ``sudo`` und ``sleep`` werden ueber ``PATH`` abgefangen; das Skript
laeuft also echt, ruft aber nichts Echtes auf.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts" / "ci" / "install-playwright-chromium.sh"
)


def _stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/usr/bin/env bash\n{body}\n")
    path.chmod(0o755)


def _run(
    tmp_path: Path, *, fail_first: int, attempts: int = 3
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Laesst ``npx`` die ersten *fail_first* Aufrufe scheitern."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"

    _stub(bin_dir, "npx", f"""
echo "npx $*" >> "{log}"
count=$(grep -c '^npx' "{log}")
if [ "$count" -le {fail_first} ]; then
  exit 100
fi
exit 0
""")
    # Der Retry-Pfad ruft beides auf; ohne Stub liefe der Test in eine echte
    # Wartezeit bzw. in eine Passwortabfrage.
    _stub(bin_dir, "sudo", f'echo "sudo $*" >> "{log}"')
    _stub(bin_dir, "sleep", f'echo "sleep $*" >> "{log}"')

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["PLAYWRIGHT_INSTALL_ATTEMPTS"] = str(attempts)
    env["PLAYWRIGHT_RETRY_BASE_DELAY"] = "1"

    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30
    )
    return result, (log.read_text().splitlines() if log.exists() else [])


def test_the_script_exists_where_the_action_expects_it():
    assert SCRIPT.is_file()


def test_one_successful_run_does_not_retry(tmp_path: Path):
    result, calls = _run(tmp_path, fail_first=0)

    assert result.returncode == 0
    assert len([c for c in calls if c.startswith("npx")]) == 1
    assert not [c for c in calls if c.startswith("sleep")]
    assert not [c for c in calls if c.startswith("sudo")]


def test_a_transient_failure_is_retried_and_succeeds(tmp_path: Path):
    """Genau der beobachtete Fall: der erste Versuch trifft den toten Mirror."""
    result, calls = _run(tmp_path, fail_first=1)

    assert result.returncode == 0
    assert len([c for c in calls if c.startswith("npx")]) == 2
    # Ohne die Aktualisierung griffe apt denselben unerreichbaren Host erneut an.
    assert [c for c in calls if c.startswith("sudo apt-get update")]
    assert [c for c in calls if c.startswith("sleep")]


def test_the_delay_grows_between_attempts(tmp_path: Path):
    _result, calls = _run(tmp_path, fail_first=2)
    sleeps = [c.split()[1] for c in calls if c.startswith("sleep")]

    assert sleeps == ["1", "2"]


def test_a_permanently_dead_mirror_fails_after_the_last_attempt(tmp_path: Path):
    """Der Retry darf einen echten Dauerfehler nicht verschlucken."""
    result, calls = _run(tmp_path, fail_first=99)

    assert result.returncode == 1
    assert len([c for c in calls if c.startswith("npx")]) == 3
    assert "::error::" in result.stdout
    # Nach dem letzten Versuch wird nicht mehr gewartet.
    assert len([c for c in calls if c.startswith("sleep")]) == 2


def test_the_attempt_count_is_configurable(tmp_path: Path):
    result, calls = _run(tmp_path, fail_first=99, attempts=2)
    assert result.returncode == 1
    assert len([c for c in calls if c.startswith("npx")]) == 2
