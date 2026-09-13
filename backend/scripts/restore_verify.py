"""Maschinenpruefbare Restore-Verifikation (Issue #766).

Warum das existiert
-------------------
``docs/backup-restore.md`` beschreibt unter „Restore-Verifikation" sorgfaeltig,
was nach einem Restore stimmen muss — als Prosa-Checkliste. Eine Checkliste, die
ein Mensch abhakt, ist kein Betriebsnachweis: sie laesst sich im Zweifel auch
abhaken, wenn niemand hingesehen hat, und sie produziert nichts, was man einem
Issue anheften koennte.

Dieses Skript prueft dieselben Punkte gegen die *restaurierte Installation* und
gibt ein Protokoll aus, das genau das ist: ein Nachweis mit Zeitstempel,
Ergebnis je Punkt und Exit-Code.

Was es NICHT ist
----------------
Es ersetzt den Drill nicht. Es ist der pruefbare Teil davon. Der Drill selbst
braucht einen frischen Host, ein echtes Backup aus einem echten Lauf und einen
Upgrade-/Rollback-Durchgang — siehe ``scripts/restore-drill.sh``.

Aufruf::

    uv run python scripts/restore_verify.py --data-dir uploads --store-dir data
    uv run python scripts/restore_verify.py --data-dir ... --json

``--data-dir`` ist das Artefaktverzeichnis (``backend/uploads``),
``--store-dir`` das der dateibasierten JSON-Stores (``backend/data``, siehe
``app/services/data_dir.py::resolve_data_dir``). Zwei Pfade, weil es zwei
Verzeichnisse sind: ``provider_connections.json`` liegt im zweiten, und ein
Pruefer, dem man nur das erste zeigt, ueberspringt den gesamten
Provider/Secrets-Abschnitt — schweigend.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Check:
    """Ein Pruefpunkt aus der Checkliste in docs/backup-restore.md."""

    name: str
    section: str
    ok: bool
    detail: str
    #: ``True``, wenn der Punkt mangels Voraussetzung nicht geprueft werden
    #: konnte. Das ist ausdruecklich KEIN Erfolg — ein uebersprungener Punkt
    #: darf einen Drill nicht gruen faerben.
    skipped: bool = False


@dataclass
class VerificationReport:
    checks: List[Check] = field(default_factory=list)
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def failed(self) -> List[Check]:
        return [c for c in self.checks if not c.ok and not c.skipped]

    @property
    def skipped(self) -> List[Check]:
        return [c for c in self.checks if c.skipped]

    @property
    def proven(self) -> bool:
        """Nur ohne Fehler UND ohne uebersprungene Punkte ist ein Restore belegt.

        Ein uebersprungener Punkt ist kein Nachweis — genau das sagt das
        Protokoll seit jeher in Prosa, und genau daran hing es, dass ``main``
        trotzdem mit 0 endete und ``restore-drill.sh`` gruen meldete.
        """
        return not self.failed and not self.skipped

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "ok": self.proven,
            "proven": self.proven,
            "failed_count": len(self.failed),
            "skipped_count": len(self.skipped),
            "checks": [
                {
                    "name": c.name,
                    "section": c.section,
                    "ok": c.ok,
                    "skipped": c.skipped,
                    "detail": c.detail,
                }
                for c in self.checks
            ],
        }


def _check(report: VerificationReport, section: str, name: str) -> Callable:
    """Dekorator-freier Helfer: fuehrt *fn* aus und protokolliert das Ergebnis."""

    def run(fn: Callable[[], tuple]) -> None:
        try:
            ok, detail, skipped = fn()
        except Exception as exc:  # noqa: BLE001 — ein Pruefpunkt darf den Lauf nie abbrechen
            report.checks.append(
                Check(name=name, section=section, ok=False, detail=f"{type(exc).__name__}: {exc}")
            )
            return
        report.checks.append(
            Check(name=name, section=section, ok=ok, detail=detail, skipped=skipped)
        )

    return run


# ---------------------------------------------------------------------------
# Artefakte
# ---------------------------------------------------------------------------


def verify_artifacts(data_dir: Path, report: VerificationReport) -> None:
    """„ein bestehender Run ist sichtbar", „Simulation-Artefakte vorhanden"."""
    section = "Artefakte"

    _check(report, section, "Datenverzeichnis vorhanden")(
        lambda: (data_dir.is_dir(), str(data_dir), False)
    )
    if not data_dir.is_dir():
        return

    registry = data_dir / "run_registry"
    runs = sorted(registry.glob("*.json")) if registry.is_dir() else []
    _check(report, section, "RunRegistry enthaelt mindestens einen Run")(
        lambda: (
            bool(runs),
            f"{len(runs)} Run-Manifest(e) in {registry}",
            not registry.is_dir(),
        )
    )

    def _readable() -> tuple:
        unreadable = []
        for path in runs:
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                unreadable.append(f"{path.name}: {exc}")
        return (
            not unreadable,
            "alle Manifeste lesbar" if not unreadable else "; ".join(unreadable[:5]),
            not runs,
        )

    _check(report, section, "Run-Manifeste sind gueltiges JSON")(_readable)

    simulations = data_dir / "simulations"
    sim_dirs = [p for p in simulations.iterdir() if p.is_dir()] if simulations.is_dir() else []
    _check(report, section, "Simulationsartefakte vorhanden")(
        lambda: (
            bool(sim_dirs),
            f"{len(sim_dirs)} Simulationsverzeichnis(se)",
            not simulations.is_dir(),
        )
    )

    reports_dir = data_dir / "reports"
    report_files = sorted(reports_dir.glob("**/*.json")) if reports_dir.is_dir() else []
    _check(report, section, "Mindestens ein Report liegt vor")(
        lambda: (
            bool(report_files),
            f"{len(report_files)} Reportdatei(en) in {reports_dir}",
            not reports_dir.is_dir(),
        )
    )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def verify_reconciliation(data_dir: Path, report: VerificationReport) -> None:
    """„Ein restaurierter Host darf keinen historischen Prozess als 'laeuft gerade' vortaeuschen."""
    section = "Reconciliation"
    registry = data_dir / "run_registry"
    if not registry.is_dir():
        report.checks.append(
            Check(
                name="Kein Run steht faelschlich auf laufend",
                section=section,
                ok=False,
                detail=f"{registry} fehlt",
                skipped=True,
            )
        )
        return

    running: List[str] = []
    for path in sorted(registry.glob("*.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — von verify_artifacts bereits gemeldet
            continue
        if manifest.get("status") in {"pending", "processing", "paused"}:
            running.append(f"{manifest.get('run_id')} ({manifest.get('run_type')})")

    _check(report, section, "Kein Run steht faelschlich auf laufend")(
        lambda: (
            not running,
            "keine offenen Runs"
            if not running
            else (
                f"{len(running)} Run(s) weiterhin offen: {', '.join(running[:5])} — "
                "Startup-Reconciliation hat nicht gegriffen (#1476/#1472)"
            ),
            False,
        )
    )


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def _connection_entries(raw: Any) -> List[Dict[str, Any]]:
    """Normalisiert ``provider_connections.json`` auf eine Liste von Eintraegen.

    ``ProviderConnectionStore`` schreibt ``{"version": 1, "connections":
    {<id>: {...}}}`` — unter ``connections`` steht ein *Objekt*, adressiert nach
    Connection-ID (``provider_connection_store.py:111``). Ueber dieses Objekt zu
    iterieren liefert die Schluessel, also ``str``; ein ``.get("secret_ref")``
    darauf beendete den Pruefpunkt mit einem ``AttributeError`` statt mit einer
    Aussage darueber, ob der Secret-Store entschluesselbar ist.

    Die Listenform wird weiter gelesen: sie kommt in Handstaenden und
    Fremdexporten vor, und ein Pruefer, der daran abstuerzt, prueft nichts mehr.
    """
    container = raw.get("connections", raw) if isinstance(raw, dict) else raw
    if isinstance(container, dict):
        values: List[Any] = list(container.values())
    elif isinstance(container, list):
        values = list(container)
    else:
        return []
    return [entry for entry in values if isinstance(entry, dict)]


def verify_secrets(store_dir: Path, report: VerificationReport) -> None:
    """„Secret-Store laesst sich mit dem restaurierten AGORA_SECRET_KEY entschluesseln".

    Geprueft wird ausschliesslich, OB die Entschluesselung gelingt — kein
    Klartext verlaesst diese Funktion, und keiner landet im Protokoll.

    ``store_dir`` ist ``backend/data`` bzw. ``AGORA_DATA_DIR``, nicht das
    Artefaktverzeichnis.
    """
    section = "Provider/Secrets"
    connections = store_dir / "provider_connections.json"

    if not connections.is_file():
        report.checks.append(
            Check(
                name="ProviderConnections vorhanden",
                section=section,
                ok=False,
                detail=f"{connections} fehlt",
                skipped=True,
            )
        )
        return

    def _connections() -> tuple:
        entries = _connection_entries(json.loads(connections.read_text(encoding="utf-8")))
        return bool(entries), f"{len(entries)} Verbindung(en)", False

    _check(report, section, "ProviderConnections vorhanden")(_connections)

    def _decryptable() -> tuple:
        if not os.environ.get("AGORA_SECRET_KEY"):
            return False, "AGORA_SECRET_KEY nicht gesetzt", True
        from app.services.llm_provider_secrets_store import get_llm_provider_secrets_store

        store = get_llm_provider_secrets_store()
        entries = _connection_entries(json.loads(connections.read_text(encoding="utf-8")))
        refs = [e["secret_ref"] for e in entries if e.get("secret_ref")]
        if not refs:
            return True, "keine hinterlegten Secrets", False
        failures = []
        for ref in refs:
            try:
                # Nur der Erfolg zaehlt — der Wert wird bewusst nicht gebunden.
                if store.get_plaintext(ref) is None:
                    failures.append(f"{ref}: leer")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{ref}: {type(exc).__name__}")
        return (
            not failures,
            f"{len(refs)} Secret(s) entschluesselbar"
            if not failures
            else "; ".join(failures[:5]),
            False,
        )

    _check(report, section, "Secret-Store entschluesselbar")(_decryptable)


# ---------------------------------------------------------------------------


def run_verification(
    data_dir: Path, store_dir: Optional[Path] = None
) -> VerificationReport:
    """Faehrt alle drei Abschnitte ab.

    ``store_dir`` faellt auf ``data_dir`` zurueck, damit aeltere Aufrufe mit
    einem einzigen Pfad weiter funktionieren; im Drill zeigt es auf
    ``backend/data``.
    """
    report = VerificationReport()
    verify_artifacts(data_dir, report)
    verify_reconciliation(data_dir, report)
    verify_secrets(store_dir if store_dir is not None else data_dir, report)
    return report


def render(report: VerificationReport) -> str:
    lines = [
        "Restore-Verifikation (Issue #766)",
        f"Zeitpunkt: {report.started_at}",
        "",
    ]
    section = None
    for check in report.checks:
        if check.section != section:
            section = check.section
            lines.append(f"[{section}]")
        mark = "SKIP" if check.skipped else ("OK  " if check.ok else "FAIL")
        lines.append(f"  {mark}  {check.name} — {check.detail}")
    lines.append("")
    if report.failed:
        lines.append(f"ERGEBNIS: {len(report.failed)} Pruefpunkt(e) fehlgeschlagen.")
    elif report.skipped:
        lines.append(
            f"ERGEBNIS: keine Fehler, aber {len(report.skipped)} Punkt(e) "
            "uebersprungen — ein uebersprungener Punkt ist kein Nachweis."
        )
    else:
        lines.append("ERGEBNIS: alle Pruefpunkte gruen.")
    return "\n".join(lines)


#: Jeder Pruefpunkt gruen, keiner uebersprungen.
_EXIT_OK = 0
#: Mindestens ein Pruefpunkt ist fehlgeschlagen.
_EXIT_FAILED = 1
#: Kein Fehler, aber mindestens ein Punkt konnte nicht geprueft werden. Ein
#: eigener Code, damit ``restore-drill.sh`` „nicht belegt" von „kaputt"
#: unterscheiden kann, ohne dass eines von beiden als gruen durchgeht.
_EXIT_UNPROVEN = 2


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Restauriertes Artefaktverzeichnis (ueblicherweise backend/uploads)",
    )
    parser.add_argument(
        "--store-dir",
        type=Path,
        default=None,
        help=(
            "Restauriertes Store-Verzeichnis (ueblicherweise backend/data bzw. "
            "AGORA_DATA_DIR). Ohne Angabe wird --data-dir verwendet."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Protokoll als JSON ausgeben")
    args = parser.parse_args(argv)

    report = run_verification(args.data_dir, args.store_dir)
    print(json.dumps(report.to_dict(), indent=2) if args.json else render(report))
    if report.failed:
        return _EXIT_FAILED
    return _EXIT_OK if report.proven else _EXIT_UNPROVEN


if __name__ == "__main__":
    raise SystemExit(main())
