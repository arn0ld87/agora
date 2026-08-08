#!/usr/bin/env python3
"""Faltet changelog.d/-Fragmente in CHANGELOG.md unter ## [Unreleased].

Teil der Merge-Friction-Entschärfung (2026-08-08): PRs schreiben nicht mehr
direkt in CHANGELOG.md (jede Einfügung an derselben Stelle kollidierte mit
jedem parallel offenen PR), sondern legen eindeutige Fragment-Dateien unter
changelog.d/ ab. Dieses Skript sammelt sie ein — beim Release-Schnitt oder
wann immer eine konsolidierte CHANGELOG gewünscht ist.

Usage:
    python3 scripts/collect-changelog.py          # einsammeln + Fragmente löschen
    python3 scripts/collect-changelog.py --check  # Exit 1, wenn Fragmente vorliegen
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRAGMENT_DIR = REPO_ROOT / "changelog.d"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
UNRELEASED_MARKER = "## [Unreleased]"


def fragments() -> list[Path]:
    if not FRAGMENT_DIR.is_dir():
        return []
    return sorted(
        (p for p in FRAGMENT_DIR.glob("*.md") if p.name != "README.md"),
        key=lambda p: p.name,
        reverse=True,
    )


def main() -> int:
    frags = fragments()
    check_only = "--check" in sys.argv[1:]

    if check_only:
        if frags:
            print(f"{len(frags)} offene Fragmente in changelog.d/:")
            for p in frags:
                print(f"  - {p.name}")
            return 1
        print("OK: keine offenen CHANGELOG-Fragmente.")
        return 0

    if not frags:
        print("Nichts zu tun: keine Fragmente in changelog.d/.")
        return 0

    text = CHANGELOG.read_text(encoding="utf-8")
    if UNRELEASED_MARKER not in text:
        print(f"FEHLER: Marker '{UNRELEASED_MARKER}' fehlt in CHANGELOG.md", file=sys.stderr)
        return 2

    blocks = []
    for p in frags:
        body = p.read_text(encoding="utf-8").strip()
        if body:
            blocks.append(body)

    insertion = "\n\n".join(blocks)
    head, _, tail = text.partition(UNRELEASED_MARKER)
    # tail beginnt mit dem Rest direkt nach dem Marker (inkl. Leerzeile).
    new = f"{head}{UNRELEASED_MARKER}\n\n{insertion}\n{tail}"
    CHANGELOG.write_text(new, encoding="utf-8")

    for p in frags:
        p.unlink()

    print(f"{len(blocks)} Fragmente nach CHANGELOG.md übernommen und entfernt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
