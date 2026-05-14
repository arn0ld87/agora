"""MAI-17: radon-Komplexitäts-Gate mit Allowlist.

Liest radon-Output und failt bei Rank≥D, wenn die Funktion nicht in
radon-allowlist.txt steht. Erlaubt damit Bestand, blockiert neue Hotspots.

Schlüsselformat in der Allowlist:
  <rel-path>::<name>       für Module-Level-Funktionen und Klassen
  <rel-path>::Class.method für Methoden (classname-Präfix aus radon JSON)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = REPO_ROOT / "radon-allowlist.txt"
SEVERITY_FAIL = {"D", "E", "F"}


def load_allowlist() -> set[str]:
    if not ALLOWLIST.exists():
        return set()
    return {
        line.strip()
        for line in ALLOWLIST.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


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

    for path, blocks in data.items():
        for block in blocks:
            rank = block.get("rank", "A")
            if rank not in SEVERITY_FAIL:
                continue
            key = build_key(path, block)
            if key in allowed:
                continue
            violations.append(
                f"{path}:{block.get('lineno')}  {block['name']}  "
                f"rank={rank}  complexity={block.get('complexity')}"
            )

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
