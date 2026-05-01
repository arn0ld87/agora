# Slice A3 — Report-Models extrahieren (Closes #45)

**Datum:** 2026-05-01
**Sprint:** v0.9.0 — Domain Cleanup
**Issue:** #45 (EPIC-07-ST-01) — Report-Models extrahieren

## Inventur

`backend/app/services/report_agent.py` (3184 LOC vor diesem Slice — durch Issue #103 sogar gewachsen statt geschrumpft) enthielt sechs reine Datenklassen:

| Klasse | Zeilenbereich | Zeilen |
|---|---|---|
| `ReportStatus` (Enum) | 400-406 | 7 |
| `ReportSection` | 410-426 | 17 |
| `ReportOutline` | 430-449 | 20 |
| `Report` | 453-482 | 30 |
| `EvidenceItem` | 486-513 | 28 |
| `ReportClaim` | 517-539 | 23 |

Gesamt **131 LOC pure Datenklassen**, in sich geschlossen — keine Abhängigkeit zu `ReportLogger`, `ReportAgent` oder `ReportManager`. Logger und Agent verbleiben in `report_agent.py` (Issue #46/#47 Scope).

`backend/app/models/` existiert bereits mit `task.py` und `project.py` — Pattern für Domain-Models etabliert.

## Externe Caller

- `backend/app/api/report.py:15` — `ReportAgent, ReportManager, ReportStatus`
- `backend/app/api/runs.py:19` — `ReportAgent, ReportManager, ReportStatus`
- `backend/tests/test_report_export.py:11` — `Report, ReportManager, ReportOutline, ReportSection, ReportStatus`
- `backend/tests/test_report_manager.py:4` — `Report, ReportAgent, ReportManager, ReportOutline, ReportSection, ReportStatus`

## Schnittentscheidung

**Re-Export-Pattern.** Models leben in `app/models/report.py`, `report_agent.py` importiert sie ganz oben und macht sie damit weiterhin als `from app.services.report_agent import Report, ...` erreichbar. Vorteile:

- Keine Caller-Anpassungen in Production-Code (`api/report.py`, `api/runs.py`) oder Tests nötig
- Nur ein Diff-Locus für #45
- Migrations-Schritt für Caller kann später nachgezogen werden, wenn das gewünscht ist

Trade-off: zwei Wahrheiten für die Import-Pfade (`models.report` und `services.report_agent`). Der Service-Pfad ist als Re-Export gekennzeichnet, neue Caller sollen `models.report` nutzen.

## Änderungen

**Neu:** `backend/app/models/report.py` (165 LOC) — die sechs Klassen 1:1 verschoben, plus `from __future__ import annotations` und Modul-Docstring.

**Geändert:** `backend/app/services/report_agent.py`
- Models-Block (Z. 400-540) entfernt
- Re-Export-Import oben dazu: `from ..models.report import Report, ReportClaim, ReportOutline, ReportSection, ReportStatus, EvidenceItem`
- Unused Imports entfernt: `from dataclasses import dataclass`, `from enum import Enum`
- **Datei:** 3184 → 3053 LOC (−4 %, −131 Zeilen)

**Geändert:** `backend/app/models/__init__.py` — Models in `__all__` aufgenommen.

## Verifikation

`npm run check` 5/5 grün:
- Backend Lint: `ruff` clean
- Backend Tests: **517 passed**, 2 skipped (Redis)
- Frontend Lint: 0 errors, 1 vorhandene Warning (nicht aus diesem Slice)
- Frontend Tests: **40 passed** (5 Files)
- Frontend Build: vite, ok

Tests, die direkt Models nutzen und damit Re-Export-Korrektheit verifizieren:
- `test_report_manager.py` — Konstruktion von `Report`, `ReportOutline`, `ReportSection`, `ReportStatus`
- `test_report_export.py` — alle fünf Models über Service-Pfad importiert

## Konsequenz für v0.9.0

Issue #45 abgeschlossen. Verbleibender v0.9.0-Backlog: **9 echte Issues** (EPIC-06 ×2: #42/#43; EPIC-07 ×4: #46/#47/#48/#49; EPIC-08 ×3: #50/#51/#52). Pfad A komplett.

## Folge-Slice

Slice B1 (Issue #42) — FSM-Integration in `SimulationManager`. Status-Setzungen durch `simulation_state_machine.is_valid_transition()`-Guards absichern.

Alternative (falls Pfad-C-Inventur ergibt, dass Issue #103 weitere EPIC-07-Issues retrospektiv erfüllt): Status-Doku-Slices vorziehen.
