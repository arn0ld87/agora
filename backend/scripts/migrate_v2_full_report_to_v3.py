"""MAI-06: Inventar-Skript für Bestandsreports vor v2-Retirement.

Liest alle existierenden full_report.md, prüft ob report-v3.json daneben liegt.
Schreibt einen Audit-Report nach docs/2026-05-14-mai-06-bestandsinventar.md.

NICHT destruktiv — löscht keine Files.

Ausführung (vom Repo-Root):
    uv run python backend/scripts/migrate_v2_full_report_to_v3.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "backend" / "uploads" / "reports"
AUDIT_FILE = REPO_ROOT / "docu" / "2026-05-14-mai-06-bestandsinventar.md"


def main() -> int:
    if not REPORTS_DIR.exists():
        print("Keine Bestandsreports — REPORTS_DIR fehlt.")
        AUDIT_FILE.write_text(
            "# MAI-06 — Bestands-Inventar Reports\n\n"
            "Erstellt von `backend/scripts/migrate_v2_full_report_to_v3.py` vor v2-Retirement.\n\n"
            "_Kein `backend/uploads/reports`-Verzeichnis gefunden — keine Bestandsreports._\n",
            encoding="utf-8",
        )
        print(f"OK: Inventur (leer) unter {AUDIT_FILE}")
        return 0

    report_dirs = sorted(
        d for d in REPORTS_DIR.iterdir() if d.is_dir()
    )

    rows: list[str] = [
        "| Report-ID | v2-md | v3-json | Status |",
        "|---|---|---|---|",
    ]
    v2_only_count = 0
    v3_ready_count = 0
    empty_count = 0

    for report_dir in report_dirs:
        v2 = report_dir / "full_report.md"
        v3 = report_dir / "report-v3.json"
        v2_exists = "✓" if v2.exists() else "—"
        v3_exists = "✓" if v3.exists() else "—"
        if v2.exists() and not v3.exists():
            status = "⚠️ Legacy — Export liefert in-meta Fallback"
            v2_only_count += 1
        elif v3.exists():
            status = "✓ v3-ready"
            v3_ready_count += 1
        else:
            status = "leer"
            empty_count += 1
        rows.append(f"| `{report_dir.name}` | {v2_exists} | {v3_exists} | {status} |")

    total = len(report_dirs)
    summary_lines = [
        "# MAI-06 — Bestands-Inventar Reports",
        "",
        "Erstellt von `backend/scripts/migrate_v2_full_report_to_v3.py` vor v2-Retirement.",
        "",
        f"**Gesamt:** {total} Report-Verzeichnisse  ",
        f"**v3-ready:** {v3_ready_count}  ",
        f"**Legacy (v2-md ohne v3-json):** {v2_only_count}  ",
        f"**Leer:** {empty_count}",
        "",
        "> **Hinweis:** Legacy-Reports (v2-md ohne v3-json) liefern beim MD-Export",
        "> den Fallback auf `markdown_content` aus `meta.json`.",
        "> Das Löschen von `full_report.md` ist NICHT Aufgabe dieses Skripts.",
        "",
        *rows,
        "",
    ]
    AUDIT_FILE.write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"OK: Inventur unter {AUDIT_FILE}")
    print(f"    {total} Reports — {v3_ready_count} v3-ready, {v2_only_count} legacy, {empty_count} leer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
