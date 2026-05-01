# Slice A5 — Report-Logger trennen (Closes #46)

**Datum:** 2026-05-01
**Sprint:** v0.9.0 — Domain Cleanup
**Issue:** #46 (EPIC-07-ST-02) — Report-Logging trennen

## Inventur

`backend/app/services/report_agent.py` (3053 LOC nach Slice A3) enthielt zwei Logger-Klassen inline:

| Klasse | Zeilenbereich | Zeilen |
|---|---|---|
| `ReportLogger` | 53-321 | 269 |
| `ReportConsoleLogger` | 324-403 | 80 |

Gesamt **352 LOC Logger-Code** im Agent-Modul. Externe Caller: keine — beide Klassen werden ausschließlich vom `ReportAgent`-Konstruktor instanziiert. Re-Export-Pattern dennoch übernommen, analog zu Slice A3, für stabile IDE-Auflösung und für Test-Code, der ggf. via `from app.services.report_agent import ReportLogger` mocken könnte.

## Schnittentscheidung

**Neue Datei** `backend/app/services/report_logger.py` (377 LOC) mit beiden Klassen 1:1 verschoben. Dependencies (`os`, `json`, `datetime`, `logging`, `Optional`, `Dict`, `Any`, `Config`) explizit importiert; `from __future__ import annotations` für lazy-Type-Resolution. `ReportConsoleLogger` zieht `import logging` jetzt auf Modul-Ebene (vorher zweimal lokal in `_setup_file_handler`/`close`).

**Type-Hint-Cleanup:** Drei Methoden hatten `section_title: str = None` und `section_index: int = None` — formal korrekt nach PEP 484, aber Mypy/Ruff bevorzugen `Optional[str]`/`Optional[int]`. Beim Verschieben auf das gängige Schema gehoben. `_file_handler` typisiert als `Optional[logging.FileHandler]`.

**Re-Export:** `report_agent.py` importiert oben `from .report_logger import ReportLogger, ReportConsoleLogger`. Damit bleiben sie weiterhin als `app.services.report_agent.ReportLogger` erreichbar.

## Änderungen

**Neu:** `backend/app/services/report_logger.py` (377 LOC)

**Geändert:** `backend/app/services/report_agent.py`
- Logger-Klassen-Block (Z. 53-405) entfernt, durch dreizeiligen Re-Export-Kommentar ersetzt
- Re-Export-Import in den Modul-Header
- **Datei:** 3053 → 2705 LOC (−11 %, −348 Zeilen)

## Verifikation

`npm run check` 5/5 grün:
- Backend Lint: `ruff` clean
- Backend Tests: **517 passed**, 2 skipped (Redis)
- Frontend Lint: 0 errors, 1 vorhandene Warning (nicht aus diesem Slice)
- Frontend Tests: **40 passed** (5 Files)
- Frontend Build: vite, ok

`ReportLogger` und `ReportConsoleLogger` sind in den Test-Suites nicht direkt instanziiert (nur indirekt über `ReportAgent.__init__`); Verifikation läuft über die `test_report_*`-Tests, die den Agent end-to-end ausüben.

## Konsequenz für v0.9.0

Issue #46 abgeschlossen. Verbleibender v0.9.0-Backlog: **7 echte Issues** (EPIC-06 ×2: #42/#43; EPIC-07 ×2: #47/#48; EPIC-08 ×3: #50/#51/#52).

`report_agent.py` ist von 3184 LOC (vor Pfad A) auf 2705 LOC (nach A5) geschrumpft — **−15 % in einem halben Tag**, ohne Verhaltensänderung.

## Folge-Slice

Slice B1 (Issue #42) — FSM-Integration in `SimulationManager`. Status-Setzungen durch `simulation_state_machine.is_valid_transition()`-Guards absichern. Empfohlen für **direkten Sichtcheck**, weil das Verhaltensänderung an Statusübergängen mit sich bringt (ungültige Transitionen werfen dann Domain-Error statt still durchzulaufen).
