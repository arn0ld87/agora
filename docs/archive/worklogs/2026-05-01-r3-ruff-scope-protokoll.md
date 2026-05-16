# R3 — CI-Ruff-Scope angleichen · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** R3

## Implementierung

`.github/workflows/ci.yml`: Ruff-Step im Backend-Job nutzt jetzt `app/ tests/` statt einer hand-gepflegten Datei-Allowlist. Damit deckt CI denselben Scope wie `npm run lint:backend` lokal ab.

Lokal grün, CI lieferte vorher dieselben Pfade plus zusätzliche Files — kein Lint-Verlust.

## Tests

`npm run check` grün, lokaler Ruff-Lauf sauber.
