"""Role-Leakage-Audit CLI (Issue #1323, Slice 5.1).

Analysiert ein Simulationsverzeichnis auf Rollenvertauschungen in Aktionstext.

Aufruf:
    uv run python scripts/role_leakage_audit.py <sim_dir> [--json out.json] [--max-examples N]

Kein LLM, kein Netzwerk. Rein regelbasiert.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Sicherstellen, dass das backend-Paket importierbar ist
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.sim.role_leakage import audit_sim_dir  # noqa: E402


def _format_table(summary) -> str:  # type: ignore[no-untyped-def]
    """Rendert eine lesbare Tabelle auf stdout."""
    lines: list[str] = []
    lines.append(f"\nRole-Leakage-Audit: {summary.sim_dir}")
    lines.append("=" * 60)
    lines.append(
        f"Texttragende Aktionen gesamt: {summary.text_actions}"
    )
    lines.append(
        f"Konflikte gesamt:             {summary.conflicts} "
        f"({summary.rate:.1%})"
    )
    if summary.by_reason:
        lines.append("Nach Kategorie:")
        for reason, count in sorted(summary.by_reason.items()):
            lines.append(f"  {reason:<35} {count}")

    lines.append("")
    lines.append("Pro Plattform:")
    lines.append(f"  {'Plattform':<12} {'Aktionen':>10} {'Konflikte':>10} {'Rate':>8}")
    lines.append("  " + "-" * 42)
    for ps in summary.per_platform:
        lines.append(
            f"  {ps.platform:<12} {ps.text_actions:>10} {ps.conflicts:>10} {ps.rate:>8.1%}"
        )

    if summary.examples:
        lines.append("")
        lines.append(f"Beispiele (max. {len(summary.examples)}):")
        for i, ex in enumerate(summary.examples, 1):
            lines.append(
                f"  [{i}] {ex.agent_name!r} ({ex.platform}, Runde {ex.round},"
                f" {ex.action_type})"
            )
            lines.append(f"      Phrase: {ex.self_reference!r}")
            lines.append(f"      Grund:  {ex.reason}")
            if ex.matched_role:
                lines.append(f"      Treffer:{ex.matched_role!r}")
            lines.append(f"      Text:   {ex.excerpt[:120]!r}")

    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Role-Leakage-Audit für Simulationsaktionen."
    )
    parser.add_argument("sim_dir", help="Pfad zum Simulationsverzeichnis")
    parser.add_argument(
        "--json",
        metavar="FILE",
        dest="json_out",
        default=None,
        help="Optional: Summary als JSON in diese Datei schreiben",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=5,
        metavar="N",
        help="Maximale Anzahl Beispiele in der Ausgabe (Standard: 5)",
    )
    args = parser.parse_args(argv)

    sim_dir = Path(args.sim_dir)
    if not sim_dir.is_dir():
        sys.stderr.write(f"Fehler: Verzeichnis nicht gefunden: {sim_dir}\n")
        return 2

    summary = audit_sim_dir(sim_dir, max_examples=args.max_examples)

    # Tabellen-Ausgabe
    print(_format_table(summary))

    # JSON-Ausgabe
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.write_text(
            json.dumps(summary.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        sys.stdout.write(f"JSON-Ausgabe: {out_path}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
