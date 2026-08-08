"""MAI-17: radon-Komplexitäts-Gate mit Allowlist.

Liest radon-Output und failt bei Rank≥D, wenn die Funktion nicht in
radon-allowlist.txt steht. Erlaubt damit Bestand, blockiert neue Hotspots.

Schlüsselformat in der Allowlist:
  <rel-path>::<name>       für Module-Level-Funktionen und Klassen
  <rel-path>::Class.method für Methoden (classname-Präfix aus radon JSON)

Optionale cc-Obergrenze je Eintrag (#1084), rückwärtskompatibel:
  <rel-path>::<name>  # cc<=<N>

Fehlt die Obergrenze, verhält sich der Eintrag wie bisher (reine Duldung).
Überschreitet die gemessene Komplexität die Obergrenze, failt das Gate.
Unterschreitet sie die Obergrenze, gibt es nur einen Hinweis, keinen Fail.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = REPO_ROOT / "radon-allowlist.txt"
SEVERITY_FAIL = {"D", "E", "F"}
_MAX_CC_RE = re.compile(r"cc\s*<=\s*(\d+)")


def load_allowlist() -> dict[str, int | None]:
    """Liest die Allowlist und liefert Schlüssel -> optionale cc-Obergrenze.

    Ein Eintrag ohne (parsebare) Obergrenze bekommt ``None`` und wird wie
    bisher rein geduldet, unabhängig von der gemessenen Komplexität. Eine
    defekte Obergrenze (z. B. ``# cc<=abc``) fällt ebenfalls auf ``None``
    zurück, statt das Gate abstürzen zu lassen.
    """
    if not ALLOWLIST.exists():
        return {}
    entries: dict[str, int | None] = {}
    for raw_line in ALLOWLIST.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "#" in stripped:
            key_part, _, comment_part = stripped.partition("#")
            key = key_part.strip()
            match = _MAX_CC_RE.search(comment_part)
            max_cc = int(match.group(1)) if match else None
        else:
            key = stripped
            max_cc = None
        if key:
            entries[key] = max_cc
    return entries


def build_key(path: str, block: dict) -> str:
    """Erstellt den Allowlist-Schlüssel passend zum radon-JSON-Format."""
    classname = block.get("classname", "") or ""
    name = block["name"]
    fullname = f"{classname}.{name}" if classname else name
    return f"{path}::{fullname}"


def main() -> int:
    result = subprocess.run(
        ["radon", "cc", "app", "--min", "C", "--no-assert", "-j"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return 1

    data = json.loads(result.stdout or "{}")
    allowed = load_allowlist()
    violations: list[str] = []
    notices: list[str] = []

    for path, blocks in data.items():
        for block in blocks:
            rank = block.get("rank", "A")
            if rank not in SEVERITY_FAIL:
                continue
            key = build_key(path, block)
            if key not in allowed:
                violations.append(
                    f"{path}:{block.get('lineno')}  {block['name']}  "
                    f"rank={rank}  complexity={block.get('complexity')}"
                )
                continue

            max_cc = allowed[key]
            complexity = block.get("complexity")
            if max_cc is None or not isinstance(complexity, int | float):
                continue
            if complexity > max_cc:
                violations.append(
                    f"{path}:{block.get('lineno')}  {block['name']}  "
                    f"rank={rank}  complexity={complexity}  "
                    f"überschreitet Allowlist-Obergrenze cc<={max_cc}"
                )
            elif complexity < max_cc:
                notices.append(
                    f"{key}: gemessen complexity={complexity} liegt unter der "
                    f"Allowlist-Obergrenze cc<={max_cc} — Wert kann abgesenkt werden."
                )

    if notices:
        print("Hinweis: Allowlist-Obergrenzen mit Luft nach unten:")
        for n in notices:
            print(f"  - {n}")

    if violations:
        print(
            "::error::Neue Komplexitäts-Hotspots (rank D+) gefunden:",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nFix-Optionen:\n"
            "  1) Funktion refactorn (Sub-Funktionen extrahieren).\n"
            "  2) Falls bewusst akzeptiert: Eintrag in backend/radon-allowlist.txt\n"
            "     mit Begründungs-Kommentar und Refactor-Slice-Referenz.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: keine neuen Komplexitäts-Hotspots "
        f"({len(allowed)} pre-existing in allowlist)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
