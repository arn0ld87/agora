# Ticket 6: Frontend Replay UI

**Blocked by:** 4, 8
**Size:** m
**Layer:** 7 (Frontend)

## Aufgabe

Replay-Button + Dialog + Untermenü in der Run-Detail-Ansicht.

## Scope

- Replay-Button in `RunDetailView.vue`
- Dialog mit zwei Optionen:
  - "Identisch wiederholen" — startet Replay ohne Overrides
  - "Variante" — Felder für Seed-Dokument, Seed-Wert, Modell
- Eigenes Untermenü in der Run-Detail-Seite für Replay-Aktionen
- API-Client: `replayRun(run_id, overrides?)` in `frontend/src/api/runs.ts`
- TypeScript-Types: `ReplayRequest`, `ReplayResponse` in `frontend/src/types/run.ts`

## Akzeptanz

- [ ] Replay-Button sichtbar bei abgeschlossenen Runs
- [ ] Dialog öffnet mit beiden Optionen
- [ ] Identisches Replay startet neuen Run
- [ ] Varianten-Replay mit Overrides funktioniert
- [ ] Neuer Run erscheint in der Run-Liste
