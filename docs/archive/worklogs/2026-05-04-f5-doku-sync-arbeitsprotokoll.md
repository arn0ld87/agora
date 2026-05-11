# Arbeitsprotokoll — F5 Doku-Sync

**Datum:** 2026-05-04
**Slice:** M9-1 · F5 (PLAN.md)
**Branch:** `chore/f5-doku-sync` → `main` (FF)
**Subagent:** `agora-doc-worker` (Haiku) + Orchestrator-Restwerk (Arbeitsprotokoll, CHANGELOG)

## Befund

`docs/status.md` war drift gegen den Live-Stand:

- Stand-Datum stand auf `2026-05-03` — heute ist `2026-05-04`.
- Backend-Test-Count `1330` — `cd backend && uv run pytest --collect-only -q` meldet `1370/1374 tests collected (4 deselected)`. Drift +40 Tests durch die letzten M9-Slices (N2, N6, F2.2, N3) und die jeweiligen neuen pytest-Files (`test_compose_snapshot.py`, `test_token_bundle_gate.sh`-Helper, neue Auth-Tests).
- README.md englischer Block (Z. 415) referenzierte noch das v0.9.0-Plateau hartcodiert: `**1258 backend + 125 frontend tests** = 1383 green`. Der deutsche Block (Z. 65) verweist seit Sub-Slice 44 schon korrekt auf `docs/status.md` — der englische Block war übersehen worden.

CLAUDE.md wurde geprüft (`rg -n "1258|1383|1330|1289" CLAUDE.md`) — keine Treffer, nichts anzufassen.

## Aktion

1. `bash scripts/sync-status.sh` → `docs/status.md` regeneriert mit `Stand: 2026-05-04`, `Backend Tests collected: 1370`, `Frontend Spec-Files: 17`.
2. Aktualisierungs-Protokoll-Eintrag am Ende von `status.md` angehängt:

   > `- 2026-05-04: F5 Doku-Sync — Test-Counts auf 1370 (1330 → 1370 nach Layer-9-Slices), README inline-Zahl entfernt.`

   Der Sub-Slice-44-Eintrag bleibt erhalten.

3. `README.md:415` umgeschrieben — englischer Bullet referenziert jetzt `docs/status.md` für aktuelle Test-Counts, identisch zum deutschen Block:

   ```diff
   - **Quality gates are in place** via `npm run check` (**1258 backend + 125 frontend tests** = 1383 green, Vitest on `jsdom`, 2 Redis integration tests skip cleanly without `TEST_REDIS_URL`).
   + **Quality gates are in place** via `npm run check` (backend lint + tests, frontend lint + Vitest on `jsdom`, frontend build; current test counts in [`docs/status.md`](docs/status.md); 2 Redis integration tests skip cleanly without `TEST_REDIS_URL`).
   ```

## Verifikation

```bash
bash scripts/sync-status.sh --check    # exit 0
rg -n "1258|1383|1330" README.md CLAUDE.md     # leer
cd backend && uv run pytest -x -q              # 1370 passed (Drift-Treffer-Check)
git diff --exit-code schemas/                  # clean
```

## Risiken

- Wenn neue Tests nach diesem Commit dazukommen, drift `status.md` wieder. `sync-status.sh --check` als CI-Gate ist nicht eingehängt — F5-Followup-Slice könnte das nachziehen.
- CONTRIBUTING.md bzw. ROADMAP.md (im Repo nicht (mehr) vorhanden) sind kein Risiko mehr — F5-Eintrag in PLAN.md sprach von „ROADMAP nennt noch v0.6.1", aber die Datei existiert nicht im Working-Tree. Falls sie mal existierte, wurde sie zwischenzeitlich entfernt.

## Refs

- PLAN.md F5 (Doku-Drift)
- Vorgänger-Slice 44 (`status.md` inaugural)
