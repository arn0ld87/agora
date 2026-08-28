"""Regressionstests für scripts/check-pip-audit-hardstop.sh.

Hintergrund (main-Rotlauf 2026-08-08): Zeile 32 nutzte ``>=`` innerhalb von
``[[ ]]`` — den Operator gibt es in Bash nicht, jeder Lauf endete mit
"syntax error in conditional expression" und Exit 2, unabhängig von Datum
und Flag-Liste. Diese Tests führen das Skript wirklich aus; ein erneuter
Syntaxfehler lässt bereits den Vor-Cutoff-Fall fehlschlagen.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check-pip-audit-hardstop.sh"


def _run(hardcutoff: str, flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env={
            "PATH": "/usr/bin:/bin",
            "PIP_AUDIT_HARDCUTOFF": hardcutoff,
            "PIP_AUDIT_FLAGS": flags,
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_before_hardcutoff_allows_ignore_list() -> None:
    result = _run("2999-01-01", "--ignore-vuln GHSA-xxxx")
    assert result.returncode == 0, result.stderr
    assert "vor dem Hardcutoff" in result.stdout


def test_after_hardcutoff_with_empty_list_is_ok() -> None:
    result = _run("2000-01-01", "")
    assert result.returncode == 0, result.stderr
    assert "Liste ist leer" in result.stdout


def test_after_hardcutoff_with_ignore_list_fails_with_exit_2() -> None:
    result = _run("2000-01-01", "--ignore-vuln GHSA-xxxx --ignore-vuln GHSA-yyyy")
    assert result.returncode == 2
    assert "non-empty" in result.stderr


def test_on_hardcutoff_day_list_must_already_be_empty() -> None:
    # Inklusiv-Semantik: am Cutoff-Tag selbst ist die Liste nicht mehr erlaubt.
    #
    # #1203: ``date.today()`` liefert das Datum der LOKALEN Zeitzone, das
    # Skript bildet sein "heute" aber mit ``date -u`` (UTC, Zeile 26). In
    # Europe/Berlin (UTC+1/+2) sind das zwischen Mitternacht und 01:00 bzw.
    # 02:00 zwei verschiedene Tage: der Test setzt den Cutoff dann auf den
    # Folgetag aus Sicht des Skripts, das nimmt korrekt den
    # "vor dem Hardcutoff"-Zweig und liefert Exit 0 statt 2.
    # Beide Seiten muessen dieselbe Zeitzone verwenden.
    import datetime

    today = datetime.datetime.now(datetime.UTC).date().isoformat()
    result = _run(today, "--ignore-vuln GHSA-xxxx")
    assert result.returncode == 2
