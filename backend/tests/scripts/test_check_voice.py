"""
Contract-Tests für backend/scripts/check_voice.py.

Testet das CLI-Verhalten gegen Eingabe-Fixtures (tmp-Dateien).
Aufrufe via subprocess.run — wir testen den Vertrag, nicht Internals.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Skript-Pfad: relativ zum Repo-Root (backend/ ist cwd im CI, aber
# __file__ liegt in backend/tests/scripts/ → 3 Ebenen hoch = Repo-Root,
# dann backend/scripts/check_voice.py)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPT_PATH = _REPO_ROOT / "backend" / "scripts" / "check_voice.py"


def _run(
    extra_args: list[str],
    tmp_path: Path,
    *,
    files: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Schreibt Fixtures und ruft check_voice.py auf."""
    written: list[Path] = []
    if files:
        for name, content in files.items():
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            written.append(p)

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--repo-root",
        str(tmp_path),
        *extra_args,
    ]
    if written and "--paths" not in extra_args:
        cmd += ["--paths"] + [str(p) for p in written]

    return subprocess.run(cmd, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# 1. Sauberer Text → Exit 0
# ---------------------------------------------------------------------------


def test_clean_text_exit_zero(tmp_path: Path) -> None:
    result = _run(
        [],
        tmp_path,
        files={"clean.py": "# Normale deutsche Beschreibung\ntext = 'hallo welt'\n"},
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"


# ---------------------------------------------------------------------------
# 2. Forecast-Phrase → Exit 1, Hit in stdout
# ---------------------------------------------------------------------------


def test_forecast_phrase_exit_one(tmp_path: Path) -> None:
    result = _run(
        [],
        tmp_path,
        files={"forecast.py": 'PROMPT = "This is a future prediction of outcomes."\n'},
    )
    assert result.returncode == 1, f"stdout={result.stdout!r}"
    assert "future prediction" in result.stdout


# ---------------------------------------------------------------------------
# 3. Marketing-Phrase → Exit 1
# ---------------------------------------------------------------------------


def test_marketing_phrase_exit_one(tmp_path: Path) -> None:
    result = _run(
        [],
        tmp_path,
        files={"marketing.py": 'TEXT = "A groundbreaking approach to AI."\n'},
    )
    assert result.returncode == 1, f"stdout={result.stdout!r}"
    assert "groundbreaking" in result.stdout


# ---------------------------------------------------------------------------
# 4. --soft → Exit 0 trotz Hits, Hits dennoch in stdout
# ---------------------------------------------------------------------------


def test_soft_flag_returns_zero_despite_hits(tmp_path: Path) -> None:
    result = _run(
        ["--soft"],
        tmp_path,
        files={"soft.py": 'MSG = "A revolutionary solution!"\n'},
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    # Hit muss trotzdem in der Ausgabe erscheinen
    assert "revolutionary" in result.stdout


# ---------------------------------------------------------------------------
# 5. Eingebaute Allowlist: voice-register-katalog.md wird übersprungen
# ---------------------------------------------------------------------------


def test_allowlist_skips_voice_register_katalog(tmp_path: Path) -> None:
    # Lege die Datei an der exakten Allowlist-Position an
    katalog = tmp_path / "prompts" / "2026-05-02-voice-register-katalog.md"
    katalog.parent.mkdir(parents=True, exist_ok=True)
    katalog.write_text(
        "# Anti-Pattern-Katalog\n- revolutionary\n- future prediction\n- groundbreaking\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--repo-root",
            str(tmp_path),
            "--paths",
            str(katalog),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Allowlisted file sollte Exit 0 geben.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# 6. Word-Boundary: kein Substring-Match, korrekter Match bei echten Treffern
# ---------------------------------------------------------------------------


def test_word_boundary_no_substring_match(tmp_path: Path) -> None:
    # "infrastructure" enthält kein Wort-Boundary-Match für "future prediction"
    # "re-leverage" (mit Bindestrich) trifft NICHT auf \bleverage\b, weil
    # "leverage" allein im Wort steht → doch: "re-leverage" enthält \bleverage\b
    # (Bindestrich ist Wort-Grenze). Das ist ein akzeptierter false positive.
    # Wichtig: "infrastructural" enthält NICHT "revolutionary" als Wort.
    content = (
        "# Test\n"
        "infra = 'infrastructural components'\n"          # kein Treffer
        "verb = 'We leverage the platform here'\n"        # Treffer: leverage
        "noun = 'financial leverage ratio'\n"             # Treffer: leverage (akzeptierter false positive)
    )
    result = _run(
        [],
        tmp_path,
        files={"boundary.py": content},
    )
    # "infrastructural" darf NICHT "revolutionary" triggern
    assert "revolutionary" not in result.stdout
    # "leverage" soll getroffen werden (zwei Mal)
    assert "leverage" in result.stdout
    assert result.returncode == 1
