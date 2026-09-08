"""Regressionstest: der Node-Gate in install.sh haelt sich an engines.node.

Defekt (Codex-P1 auf PR #1469, vitest 4.1.11 -> 5.0.0): vitest 5 verlangt
``^22.12.0 || ^24.0.0 || >=26.0.0``. Beide package.json deklarierten weiter
``>=20.0.0`` und install.sh liess jeden Node >= 20 durch. Eine saubere
Installation nach README landete damit auf einer Laufzeit, die die
Manifeste selbst ablehnen — der Widerspruch fiel nur deshalb nicht auf,
weil die CI vitest ausschliesslich ueber bun startet und Node dort nie
einrichtet, ``engines`` also nie erzwungen wird.

Der Test prueft nicht die Zahl 22, sondern die *Uebereinstimmung*: er liest
``engines.node`` aus den Manifesten und haelt den Bash-Gate dagegen. Zieht
ein spaeterer Bump den Bereich weiter, schlaegt er fehl, bis install.sh
nachgezogen ist — genau die Drift, die hier aufgefallen ist.

Bewusst kein ``packaging``/``semver``-Import: der Vergleich laeuft ueber
eine kleine Eigenimplementierung der drei zulaessigen Klauselformen, damit
der Test keine Abhaengigkeit einfuehrt, die zum Installationszeitpunkt
ohnehin nicht vorhanden waere.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "install.sh"
ROOT_MANIFEST = REPO_ROOT / "package.json"
FRONTEND_MANIFEST = REPO_ROOT / "frontend" / "package.json"


def _declared_range(manifest: Path) -> str:
    raw: object = json.loads(manifest.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    engines: object = raw["engines"]
    assert isinstance(engines, dict)
    node_range: object = engines["node"]
    assert isinstance(node_range, str)
    return node_range


def _extract_node_support_source() -> str:
    """Extrahiert node_supported() aus install.sh (Marker-Block)."""
    result = subprocess.run(
        [
            "sed",
            "-n",
            "/^# >>> node-support-block/,/^# <<< node-support-block/p",
            str(INSTALL_SH),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    source = result.stdout
    assert "node_supported() {" in source, "Funktionsdefinition nicht gefunden"
    return source


def _install_sh_accepts(major: int, minor: int) -> bool:
    """Fuehrt den extrahierten Gate in einer Subshell aus."""
    snippet = f"{_extract_node_support_source()}\nnode_supported {major} {minor}\n"
    result = subprocess.run(
        ["bash", "-c", snippet], capture_output=True, text=True, timeout=10
    )
    return result.returncode == 0


def _range_accepts(spec: str, major: int, minor: int) -> bool:
    """Wertet die Klauselformen aus, die in engines.node vorkommen duerfen.

    Unterstuetzt ``^X.Y.Z`` und ``>=X.0.0``. Jede andere Form ist ein
    Signal, dass dieser Test mitwachsen muss, statt still danebenzuliegen.
    """
    for clause in (c.strip() for c in spec.split("||")):
        if clause.startswith("^"):
            c_major, c_minor, _ = (int(p) for p in clause[1:].split("."))
            if major == c_major and (major, minor) >= (c_major, c_minor):
                return True
        elif clause.startswith(">="):
            c_major, c_minor, _ = (int(p) for p in clause[2:].split("."))
            if (major, minor) >= (c_major, c_minor):
                return True
        else:
            raise AssertionError(
                f"Unbekannte Klauselform {clause!r} in engines.node — "
                "Test erweitern statt Bereich raten."
            )
    return False


def test_root_and_frontend_declare_the_same_node_range() -> None:
    """Ein Repo, ein Node-Bereich. Zwei Werte waeren wieder Drift."""
    assert _declared_range(ROOT_MANIFEST) == _declared_range(FRONTEND_MANIFEST)


@pytest.mark.parametrize(
    ("major", "minor"),
    [
        (18, 20),  # EOL
        (20, 19),  # alter Floor — reicht fuer vite, nicht fuer vitest 5
        (22, 11),  # knapp unter der 22er-Grenze
        (22, 12),  # exakt die Grenze
        (23, 0),   # kein LTS, von vitest ausgeschlossen
        (24, 0),
        (25, 0),   # kein LTS, von vitest ausgeschlossen
        (26, 0),
        (28, 3),
    ],
)
def test_install_gate_matches_declared_engines(major: int, minor: int) -> None:
    spec = _declared_range(FRONTEND_MANIFEST)
    expected = _range_accepts(spec, major, minor)
    actual = _install_sh_accepts(major, minor)
    assert actual is expected, (
        f"install.sh {'akzeptiert' if actual else 'lehnt ab'} Node {major}.{minor}, "
        f"engines.node ({spec}) sagt {'akzeptiert' if expected else 'abgelehnt'}."
    )


def test_declared_range_covers_the_running_interpreter_of_ci() -> None:
    """Der Bereich muss mindestens eine aktive LTS-Linie zulassen.

    Ohne diese Schranke koennte ein Tippfehler den Bereich auf etwas
    Unerfuellbares eindampfen und der Parametrisierungstest oben bliebe
    trotzdem gruen — er prueft nur Uebereinstimmung, nicht Sinn.
    """
    spec = _declared_range(FRONTEND_MANIFEST)
    assert any(_range_accepts(spec, m, 0) for m in (24, 26)), (
        f"engines.node ({spec}) laesst weder Node 24 noch 26 zu."
    )
