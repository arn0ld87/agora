# `docu/` — Arbeits-, Refactoring- und Architekturdokumentation

Diese Ablage enthält die **laufende Projektdokumentation** für Agora.

## Zweck

Hier liegen insbesondere:

- Audit- und Bestandsaufnahmen
- Refactoring-Backlogs
- Zielarchitektur-Dokumente
- Arbeitsprotokolle für P0/P1-Schritte
- Verlauf / historische Notizen unter `docu/history/`
- spezielle Teilprotokolle, z.B. für:
  - Simulation-API-Split
  - GraphPanel-Modularisierung
  - Embedding-/Config-Härtung
  - Polling-Composable

## Wichtige Dateien zum Einstieg

- `2026-04-22-refactoring-produkt-audit.md`
- `refactoring-backlog-priorisiert.md`
- `target-architecture.md`
- `feature-roadmap.md`
- `p0-arbeitsprotokoll.md`

## Betrieb (Operator)

Wer Agora installieren, aktualisieren oder im Fehlerfall debuggen muss,
beginnt mit:

- [`operator-guide.md`](operator-guide.md) — Komplette
  Operator-Anleitung (Install, Provider-Keys, Backup, Update, Diagnose,
  Security).
- [`secret-key-lifecycle.md`](secret-key-lifecycle.md) — AGORA_SECRET_KEY
  erzeugen, sicher speichern, rotieren, im Verlustfall handhaben.
- [`backup-restore.md`](backup-restore.md) — Asset-Tabelle inkl.
  Multi-Provider-Hub-Daten unter `backend/data/`.
- [`deployment-prod-like.md`](deployment-prod-like.md) — Prod-Compose,
  Reverse-Proxy, gevent.

## Konvention

- **`docu/`** = aktive Projekt-, Refactoring- und Verlaufsdokumentation
- **`docu/history/`** = ältere Pläne, Berichte und verschobene Root-Notizen

Wenn du den aktuellen technischen Stand verstehen willst, beginne mit:
1. `target-architecture.md`
2. `refactoring-backlog-priorisiert.md`
3. `p0-arbeitsprotokoll.md`
