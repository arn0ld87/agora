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
import logging
import sys

from jsonschema import Draft202012Validator, FormatChecker
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXCEPTIONS_FILE = REPO_ROOT / "docs" / "dependency-risk-exceptions.json"
SCHEMA_FILE = REPO_ROOT / "schemas" / "dependency-risk-exceptions.schema.json"
SCHEMA = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker()).evolve(
    schema={"$ref": "#/$defs/Exception", "$defs": SCHEMA["$defs"]}
)
LOGGER = logging.getLogger(__name__)


def configure_logging() -> None:
    info = logging.StreamHandler(sys.stdout)
    info.addFilter(lambda record: record.levelno < logging.ERROR)
    errors = logging.StreamHandler(sys.stderr)
    errors.setLevel(logging.ERROR)
    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers = [info, errors]
    LOGGER.propagate = False

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
    p.add_argument("--trivy-report", type=Path, action="append", default=[],
                   help="Trivy JSON image report; repeat for multiple images.")
    return p.parse_args()


def load_exceptions(path: Path) -> list[dict]:
    if not path.is_file():
        LOGGER.error(f"::error::Datei nicht gefunden oder kein reguläres File: {path}")
        sys.exit(1)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        LOGGER.error(f"::error::JSON-Fehler in {path}: {exc}")
        sys.exit(1)
    if not isinstance(data, dict) or "exceptions" not in data:
        LOGGER.error(
            f"::error::Ungültiges Format: Top-Level-Key 'exceptions' fehlt in {path}",
            
        )
        sys.exit(1)
    entries = data["exceptions"]
    if not isinstance(entries, list):
        LOGGER.error(
            "::error::'exceptions' muss eine Liste sein.",
            
        )
        sys.exit(1)
    if not all(isinstance(e, dict) for e in entries):
        LOGGER.error(
            "::error::Alle Einträge in 'exceptions' müssen JSON-Objekte sein.",
            
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
    for error in VALIDATOR.iter_errors(entry):
        errors.append(f"Eintrag #{index} ({entry.get('advisory_id', '?')}): {error.message}")
    # Deadline-Format prüfen (wenn vorhanden)
    deadline_raw = entry.get("deadline", "")
    if deadline_raw:
        try:
            date.fromisoformat(deadline_raw)
        except (ValueError, TypeError):
            errors.append(
                f"Eintrag #{index} ({entry.get('advisory_id', '?')}): "
                f"Ungültiges Deadline-Format '{deadline_raw}' — erwartet YYYY-MM-DD"
            )
    return errors


def check_deadline(entry: dict, today: date) -> str | None:
    """Gibt Fehlermeldung zurück wenn abgelaufen, sonst None."""
    if entry.get("status") not in {"open", "dismissed"}:
        return None
    deadline_raw = entry.get("deadline", "")
    if not deadline_raw:
        return None
    try:
        deadline = date.fromisoformat(deadline_raw)
    except (ValueError, TypeError):
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


def check_trivy_report(path: Path, entries: list[dict]) -> list[str]:
    """Match actual image/package/version findings; malformed reports fail closed."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict) or not isinstance(report.get("ArtifactName"), str):
            raise ValueError("ArtifactName fehlt")
        image = report["ArtifactName"]
        results = report.get("Results")
        if not image.strip() or not isinstance(results, list):
            raise ValueError("Results fehlt oder ist keine Liste")
        findings = []
        for result in results:
            if not isinstance(result, dict):
                raise ValueError("Ungültiges Result")
            vulnerabilities = result.get("Vulnerabilities", [])
            if not isinstance(vulnerabilities, list):
                raise ValueError("Ungültige Vulnerabilities")
            for finding in vulnerabilities:
                if not isinstance(finding, dict) or not all(
                    isinstance(finding.get(key), str) and finding[key].strip()
                    for key in ("VulnerabilityID", "PkgName", "InstalledVersion", "Severity")
                ):
                    raise ValueError("Unvollständiges Finding")
                findings.append(finding)
    except (OSError, ValueError, TypeError) as exc:
        return [f"Trivy-Report {path}: {exc}"]

    errors = []
    for finding in findings:
        severity = finding["Severity"].upper()
        if severity not in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"}:
            errors.append(f"Unbekannter Schweregrad: {severity}")
            continue
        if severity not in {"HIGH", "CRITICAL"}:
            continue
        matches = [entry for entry in entries if
            entry.get("source") == "container" and entry.get("image") == image
            and entry.get("advisory_id") == finding["VulnerabilityID"]
            and entry.get("package") == finding["PkgName"]
            and entry.get("version_constraint") == f"=={finding['InstalledVersion']}"
            and str(entry.get("severity", "")).upper() == severity
            and entry.get("status") in {"open", "dismissed"}]
        if severity == "CRITICAL":
            matches = [entry for entry in matches if entry.get("status") == "dismissed"]
        if not matches:
            errors.append(f"{severity}: {image} / {finding['PkgName']} / "
                          f"{finding['VulnerabilityID']}: keine gültige Ausnahme")
    return errors


def main() -> int:
    configure_logging()
    args = parse_args()

    today: date
    if args.date:
        try:
            today = date.fromisoformat(args.date)
        except ValueError:
            LOGGER.error(
                f"::error::Ungültiges --date-Format '{args.date}' — erwartet YYYY-MM-DD",
                
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

    for report in args.trivy_report:
        validation_errors.extend(check_trivy_report(report, entries))

    if validation_errors:
        LOGGER.error("::error::Validierungsfehler in dependency-risk-exceptions.json:")
        for e in validation_errors:
            LOGGER.error(f"  - {e}")

    if deadline_errors:
        LOGGER.error(
            "::error::Abgelaufene Dependency-Risk-Ausnahmen müssen aufgelöst werden:",
            
        )
        for e in deadline_errors:
            LOGGER.error(f"  - {e}")
        LOGGER.error(
            "\nEskalationspfad: docs/dependency-risk-register.md → Abschnitt 'Eskalationspfad'.",
            
        )

    if validation_errors or deadline_errors:
        return 1

    open_count = sum(1 for e in entries if e.get("status") == "open")
    LOGGER.info(
        f"OK: all dependency risk exceptions are valid and not expired "
        f"({open_count} open, {len(entries) - open_count} resolved, "
        f"reference date: {today})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
