"""Regressionstest: nltk >= 3.10 darf den Ingestion-Pfad nicht blockieren.

nltk 3.10 installiert beim Import einen Meta-Path-Finder (``nltk/inisec.py``),
der jeden von nltk ausgelösten Import blockiert, dessen Modul **unterhalb des
aktuellen Arbeitsverzeichnisses** liegt. Gedacht ist er gegen
CWD-Import-Hijacking; er unterscheidet aber nicht zwischen dem Projektbaum und
einer virtuellen Umgebung, die zufällig darunter liegt.

Genau das ist hier der Normalfall:

* Container: ``WORKDIR /app``, venv unter ``/app/backend/.venv``
* lokal: ``cd backend && uv run …``, venv unter ``backend/.venv``

In beiden Fällen gilt *jedes* venv-Paket als "aus dem CWD". Sobald
``unstructured`` beim Parsen nltk lädt, fliegen ``regex`` und ``defusedxml`` mit
einem ``ImportError`` heraus und der Ingestion-Pfad bricht.

Gegenmittel ist ``NLTK_DISABLE_IMPORT_SECURITY=1`` — gesetzt im ``Dockerfile``
(base- und prod-Stage) und in ``backend/tests/conftest.py`` für die Suite.
``PYTHONSAFEPATH=1`` hilft **nicht**, obwohl die Fehlermeldung von nltk es
vorschlägt: nltk setzt es selbst per ``setdefault`` und der Hook greift trotzdem.

Diese Tests schlagen fehl, sobald eine der beiden Setzungen verschwindet.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

_IMPORT_PROBE = (
    "import nltk\n"
    "from nltk.text import Text\n"  # zieht `regex`
    "print('ok')\n"
)


@pytest.mark.parametrize(
    "cwd",
    [
        pytest.param(BACKEND_DIR, id="cwd=backend (venv direkt darunter)"),
        pytest.param(REPO_ROOT, id="cwd=repo-root (venv zwei Ebenen darunter)"),
    ],
)
def test_nltk_importable_with_venv_below_cwd(cwd: Path) -> None:
    """``import nltk`` überlebt beide Arbeitsverzeichnisse aus dem echten Betrieb."""
    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=120,
    )
    assert result.returncode == 0, (
        f"nltk-Import aus {cwd} fehlgeschlagen — vermutlich ist "
        f"NLTK_DISABLE_IMPORT_SECURITY nicht gesetzt.\nstderr:\n{result.stderr}"
    )


def test_dockerfile_disables_nltk_import_guard() -> None:
    """Beide Container-Stages setzen den Opt-out.

    Ohne ihn bricht der Ingestion-Pfad erst zur Laufzeit im Container — an einer
    Stelle, die keine Testsuite und kein Build-Schritt erreicht.
    """
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    occurrences = dockerfile.count("NLTK_DISABLE_IMPORT_SECURITY=1")
    assert occurrences >= 2, (
        "NLTK_DISABLE_IMPORT_SECURITY=1 muss in der base- UND der prod-Stage "
        f"gesetzt sein, gefunden: {occurrences}x"
    )
