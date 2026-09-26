"""Allowlist-Selektion exportierbarer Run-Artefakte (Issue #1680, Folge #1274 Punkt 7).

``GET /api/runs/<run_id>/export`` packte bisher per ``os.walk`` jede Datei
unter ``ArtifactLocator.run_dir(run_id)`` ungeprüft ins ZIP. Dieses Modul
ersetzt das durch eine explizite Allowlist, erhoben aus dem Inventar aller
Writer ins Run-Verzeichnis (relativ zu ``run_dir``, POSIX-Separatoren):

- ``manifest.json`` — ``manifest_capture.ManifestCapture``
- ``runtime_llm_routing.json`` — ``RuntimeRunConfig.save_config``
- ``stages/<stage_id>_llm_route_snapshot.json`` — ``RuntimeRunConfig.save_stage_snapshot``
- ``stages/<stage_id>_ai_route_snapshot.json`` — ``RuntimeRunConfig.save_ai_route_snapshot``
- ``llm_call_events.jsonl`` — ``RunUsageLedger`` / ``LLMInvocationLogger``
- ``usage_summary.json`` — ``RunUsageLedger``
- ``budget_warnings.json`` — ``RunBudget``

Transiente Schreibnebenprodukte der atomaren Writer
(``.tmp-manifest-*.json``, ``*.json.tmp``) und alles andere sind bewusst
NICHT erlaubt. Symlinks werden nie exportiert (auch nicht mit erlaubtem
Namen — das Ziel könnte außerhalb liegen oder zwischen Prüfung und Lesen
ausgetauscht werden); Dateien, deren realer Speicherort außerhalb des
Run-Verzeichnisses liegt, ebenso. Übersprungenes wird über den
``RunExportReport`` sichtbar gemeldet, nie still weggelassen.
"""
from __future__ import annotations

import fnmatch
import os
from typing import Final

from ..contracts.run_export_contract import RunExportReport, SkippedExportEntry

#: Exportierbare Artefakte als fnmatch-Muster, relativ zum Run-Verzeichnis.
#: Neue Writer ins Run-Verzeichnis müssen hier ergänzt werden (und zwar im
#: selben Change), sonst bleiben ihre Artefakte im Export sichtbar ``skipped``.
EXPORT_ALLOWED_PATTERNS: Final[tuple[str, ...]] = (
    "manifest.json",
    "runtime_llm_routing.json",
    "llm_call_events.jsonl",
    "usage_summary.json",
    "budget_warnings.json",
    "stages/*_llm_route_snapshot.json",
    "stages/*_ai_route_snapshot.json",
)


def _is_export_allowed(rel_posix: str) -> bool:
    return any(fnmatch.fnmatchcase(rel_posix, pattern) for pattern in EXPORT_ALLOWED_PATTERNS)


def select_run_export_files(run_id: str, run_dir: str) -> RunExportReport:
    """Selektiert die exportierbaren Dateien unterhalb ``run_dir`` (Issue #1680).

    Läuft wie der bisherige Export mit ``os.walk`` (``followlinks=False``),
    damit auch Unterverzeichnisse wie ``stages/`` berücksichtigt bleiben
    (Bug_019), entscheidet aber je Datei anhand der Allowlist. Das Ergebnis
    enthält jede vorgefundene Datei genau einmal — entweder in ``exported``
    oder mit Grund in ``skipped``.
    """
    report = RunExportReport(run_id=run_id)
    real_run_dir = os.path.realpath(run_dir)

    for root, _dirs, files in os.walk(run_dir):
        for name in files:
            full_path = os.path.join(root, name)
            rel_posix = os.path.relpath(full_path, run_dir).replace(os.sep, "/")
            if os.path.islink(full_path):
                report.skipped.append(
                    SkippedExportEntry(path=rel_posix, reason="symlink")
                )
                continue
            if not os.path.realpath(full_path).startswith(real_run_dir + os.sep):
                report.skipped.append(
                    SkippedExportEntry(path=rel_posix, reason="outside_run_dir")
                )
                continue
            if not _is_export_allowed(rel_posix):
                report.skipped.append(
                    SkippedExportEntry(path=rel_posix, reason="not_in_allowlist")
                )
                continue
            report.exported.append(rel_posix)

    report.exported.sort()
    report.skipped.sort(key=lambda entry: entry.path)
    return report
