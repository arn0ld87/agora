"""Regressionstest: nltk >= 3.10 darf den Ingestion-Pfad nicht blockieren.

nltk 3.10 installiert beim Import einen Meta-Path-Finder (``nltk/inisec.py``),
der jeden von nltk ausgelösten Import blockiert, dessen Modul unterhalb des
aktuellen Arbeitsverzeichnisses liegt. Gedacht ist er gegen
CWD-Import-Hijacking; er unterscheidet aber nicht zwischen dem Projektbaum und
einer virtuellen Umgebung, die zufällig darunter liegt.

Genau das ist hier der Normalfall:

* nativ:     ``cd backend && uv run python run.py``, venv unter ``backend/.venv``
* Container: ``WORKDIR /app``, venv unter ``/app/backend/.venv``

In beiden Fällen gilt *jedes* venv-Paket als "aus dem CWD". Sobald
``unstructured`` beim Parsen nltk lädt, fliegen ``regex`` und ``defusedxml`` mit
einem ``ImportError`` heraus und der Ingestion-Pfad bricht — zur Laufzeit, nicht
beim Build.

Gegenmittel ist ``NLTK_DISABLE_IMPORT_SECURITY=1``, gesetzt an drei Stellen:

* ``backend/app/__init__.py`` — deckt jeden Einstieg ab, der ``app`` importiert
  (``run.py``, gunicorn, Skripte, Worker),
* ``Dockerfile`` (base- und prod-Stage) als ENV,
* ``backend/tests/conftest.py`` für die Suite selbst.

``PYTHONSAFEPATH=1`` ist **keine** Alternative, obwohl die Fehlermeldung von nltk
es vorschlägt: nltk setzt es selbst per ``setdefault`` und der Hook greift
trotzdem.

Alle Subprozesse hier laufen mit **entfernter** ``NLTK_DISABLE_IMPORT_SECURITY``.
Würden sie den Opt-out aus ``conftest.py`` erben, wären sie grün, ohne die
produktive Konfiguration je zu prüfen.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


def _run_without_optout(code: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Subprozess ohne geerbten Opt-out — sonst testet er nichts."""
    env = os.environ.copy()
    env.pop("NLTK_DISABLE_IMPORT_SECURITY", None)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


def test_guard_is_actually_active_without_optout() -> None:
    """Vorbedingung: ohne Opt-out blockiert nltk den Import wirklich.

    Ohne diesen Nachweis wären die folgenden Tests tautologisch — sie wären auch
    dann grün, wenn nltk den Hook upstream wieder entfernt.
    """
    result = _run_without_optout("import nltk; from nltk.text import Text", BACKEND_DIR)
    if result.returncode == 0:
        pytest.skip(
            "nltk blockiert Imports aus dem CWD-Baum nicht mehr — der Hook ist "
            "offenbar upstream entfernt oder entschärft. Dann können "
            "NLTK_DISABLE_IMPORT_SECURITY und dieser Test entfallen."
        )
    assert "Blocked import" in result.stderr, (
        "Erwartet wurde der nltk-Import-Guard, der Subprozess ist aber an etwas "
        f"anderem gescheitert:\n{result.stderr}"
    )


@pytest.mark.parametrize(
    "cwd",
    [
        pytest.param(BACKEND_DIR, id="cwd=backend (venv direkt darunter)"),
        pytest.param(REPO_ROOT, id="cwd=repo-root (venv zwei Ebenen darunter)"),
    ],
)
def test_importing_app_unblocks_nltk(cwd: Path) -> None:
    """``import app`` setzt den Opt-out — der produktive Einstieg trägt ihn.

    Das ist der eigentliche Nachweis. ``run.py``, gunicorn und jedes Skript
    importieren ``app``, bevor irgendetwas nltk anfasst. Fällt die Setzung aus
    ``app/__init__.py`` heraus, bricht dieser Test — anders als eine Prüfung, die
    den Opt-out aus der Testumgebung erbt.
    """
    result = _run_without_optout("import app; from nltk.text import Text", cwd)
    assert result.returncode == 0, (
        f"nltk-Import nach `import app` aus {cwd} fehlgeschlagen — vermutlich "
        "fehlt os.environ.setdefault('NLTK_DISABLE_IMPORT_SECURITY', '1') in "
        f"backend/app/__init__.py.\nstderr:\n{result.stderr}"
    )


def test_ingestion_entrypoint_can_parse() -> None:
    """Der reale Bruchpfad: ``unstructured`` lädt nltk beim Parsen lazy.

    Hier ist der Fehler ursprünglich aufgeschlagen — nicht bei ``import nltk``,
    sondern erst beim ersten echten Parse-Aufruf zur Laufzeit.
    """
    result = _run_without_optout(
        "import app\n"
        "from unstructured.partition.text import partition_text\n"
        "els = partition_text(text='Das ist ein Satz. Und noch einer.')\n"
        "assert els, 'partition_text lieferte keine Elemente'\n",
        BACKEND_DIR,
    )
    assert result.returncode == 0, f"Ingestion-Parse fehlgeschlagen:\n{result.stderr}"


def _stage_block(dockerfile: str, stage: str) -> str:
    """Der Textblock einer Dockerfile-Stage, von ``AS <stage>`` bis zum nächsten ``FROM``."""
    lines = dockerfile.splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if line.startswith("FROM ") and line.rstrip().endswith(f"AS {stage}")
        ),
        None,
    )
    assert start is not None, f"Stage '{stage}' nicht im Dockerfile gefunden"
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("FROM ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


@pytest.mark.parametrize("stage", ["base", "prod"])
def test_dockerfile_stage_disables_nltk_import_guard(stage: str) -> None:
    """Jede relevante Container-Stage setzt den Opt-out einzeln als ENV.

    Pro Stage geprüft statt über einen Gesamt-Zähler: eine reine Zählung über die
    ganze Datei ist auch dann grün, wenn eine Stage den Opt-out doppelt trägt und
    die andere gar nicht.

    ``app/__init__.py`` greift im Container ebenfalls; die ENV-Setzung deckt
    darüber hinaus Prozesse ab, die mit nltk in Berührung kommen, bevor ``app``
    importiert ist.
    """
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    block = _stage_block(dockerfile, stage)
    env_lines = [
        line
        for line in block.splitlines()
        if "NLTK_DISABLE_IMPORT_SECURITY=1" in line and not line.lstrip().startswith("#")
    ]
    assert env_lines, (
        f"Stage '{stage}' setzt NLTK_DISABLE_IMPORT_SECURITY=1 nicht (Kommentare "
        "zählen nicht). Ohne den Opt-out bricht der Ingestion-Pfad im Container "
        "zur Laufzeit."
    )
