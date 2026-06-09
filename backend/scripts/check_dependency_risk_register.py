"""check_dependency_risk_register.py — Issue #631.

Prüft alle aktiven Ausnahmen in docs/dependency-risk-exceptions.json:
- Jede Ausnahme muss Pflichtfelder enthalten (advisory_id, package, version_constraint,
  severity, reason, blocker, target_version, owner, deadline, issue, status).
- Abgelaufene Deadlines (deadline < today) führen zu Exit 1.
- Nur Einträge mit status == "open" werden auf Deadline geprüft.

Aufruf:
  python scripts/check_dependency_risk_register.py
  python scripts/check_dependency_risk_register.py --exceptions-file path/to/file.json
  python scripts/check_dependency_risk_register.py --date 2026-08-01  # Zeitreise für Tests

Exit-Codes:
  0 — alle Ausnahmen valide und nicht abgelaufen
  1 — mindestens eine Ausnahme abgelaufen oder ungültig
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXCEPTIONS_FILE = REPO_ROOT / "docs" / "dependency-risk-exceptions.json"

REQUIRED_FIELDS = {
    "advisory_id",
    "package",
    "version_constraint",
    "severity",
    "reason",
    "blocker",
    "target_version",
    "owner",
    "deadline",
    "issue",
    "status",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Prüft Deadlines der Dependency-Risk-Ausnahmen."
    )
    p.add_argument(
        "--exceptions-file",
        type=Path,
        default=DEFAULT_EXCEPTIONS_FILE,
        help="Pfad zur exceptions-JSON-Datei (default: docs/dependency-risk-exceptions.json)",
    )
    p.add_argument(
        "--date",
        type=str,
        default=None,
        help="Referenzdatum im Format YYYY-MM-DD (default: heute). Für Tests.",
    )
    return p.parse_args()


def load_exceptions(path: Path) -> list[dict]:
    if not path.exists():
        print(f"::error::Datei nicht gefunden: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"::error::JSON-Fehler in {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict) or "exceptions" not in data:
        print(
            f"::error::Ungültiges Format: Top-Level-Key 'exceptions' fehlt in {path}",
            file=sys.stderr,
        )
        sys.exit(1)
    entries = data["exceptions"]
    if not isinstance(entries, list):
        print(
            "::error::'exceptions' muss eine Liste sein.",
            file=sys.stderr,
        )
        sys.exit(1)
    return entries  # type: ignore[return-value]


def validate_entry(entry: dict, index: int) -> list[str]:
    """Gibt Liste von Fehlermeldungen zurück (leer = OK)."""
    errors: list[str] = []
    missing = REQUIRED_FIELDS - entry.keys()
    if missing:
        errors.append(
            f"Eintrag #{index} ({entry.get('advisory_id', '?')}): "
            f"Pflichtfelder fehlen: {', '.join(sorted(missing))}"
        )
    # Deadline-Format prüfen (wenn vorhanden)
    deadline_raw = entry.get("deadline", "")
    if deadline_raw and not missing:
        try:
            date.fromisoformat(deadline_raw)
        except ValueError:
            errors.append(
                f"Eintrag #{index} ({entry.get('advisory_id', '?')}): "
                f"Ungültiges Deadline-Format '{deadline_raw}' — erwartet YYYY-MM-DD"
            )
    return errors


def check_deadline(entry: dict, today: date) -> str | None:
    """Gibt Fehlermeldung zurück wenn abgelaufen, sonst None."""
    if entry.get("status") != "open":
        return None
    deadline_raw = entry.get("deadline", "")
    if not deadline_raw:
        return None
    try:
        deadline = date.fromisoformat(deadline_raw)
    except ValueError:
        return None  # bereits durch validate_entry gemeldet
    if today > deadline:
        days_overdue = (today - deadline).days
        return (
            f"ABGELAUFEN ({days_overdue} Tage): "
            f"{entry.get('advisory_id', '?')} / {entry.get('package', '?')} — "
            f"Deadline war {deadline_raw}. "
            f"Siehe {entry.get('issue', 'kein Issue')}."
        )
    return None


def main() -> int:
    args = parse_args()

    today: date
    if args.date:
        try:
            today = date.fromisoformat(args.date)
        except ValueError:
            print(
                f"::error::Ungültiges --date-Format '{args.date}' — erwartet YYYY-MM-DD",
                file=sys.stderr,
            )
            return 1
    else:
        today = date.today()

    entries = load_exceptions(args.exceptions_file)

    validation_errors: list[str] = []
    deadline_errors: list[str] = []

    for i, entry in enumerate(entries):
        validation_errors.extend(validate_entry(entry, i))
        err = check_deadline(entry, today)
        if err:
            deadline_errors.append(err)

    if validation_errors:
        print("::error::Validierungsfehler in dependency-risk-exceptions.json:", file=sys.stderr)
        for e in validation_errors:
            print(f"  - {e}", file=sys.stderr)

    if deadline_errors:
        print(
            "::error::Abgelaufene Dependency-Risk-Ausnahmen müssen aufgelöst werden:",
            file=sys.stderr,
        )
        for e in deadline_errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            "\nEskalationspfad: docs/dependency-risk-register.md → Abschnitt 'Eskalationspfad'.",
            file=sys.stderr,
        )

    if validation_errors or deadline_errors:
        return 1

    open_count = sum(1 for e in entries if e.get("status") == "open")
    print(
        f"OK: all dependency risk exceptions are valid and not expired "
        f"({open_count} open, {len(entries) - open_count} resolved, "
        f"reference date: {today})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
