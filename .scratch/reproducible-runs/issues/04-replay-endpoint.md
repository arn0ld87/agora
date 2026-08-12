# Ticket 4: Replay Endpoint

**Blocked by:** 1
**Blocks:** 6
**Size:** m
**Layer:** 3 (API)

## Aufgabe

`POST /api/runs/<run_id>/replay` — neuen Run aus Manifest starten.

## Scope

- Endpoint in `backend/app/api/runs.py`
- Liest `manifest.json` des Original-Runs
- Preflight-Check: warnt wenn Modell/Provider nicht mehr verfügbar, blockiert nicht
- Identisches Replay: übernimmt alle Parameter aus dem Manifest
- Varianten-Replay: Override-Body erlaubt `seed_document_id`, `random_seed`, `ai_model_ref`
- Erzeugt neuen Run mit `replayed_from_run_id = <original_run_id>`
- `parent_run_id` bleibt für die Run-Hierarchie
- Response: `202 { run_id, status: "pending" }`

## Akzeptanz

- [ ] Identisches Replay startet neuen Run mit gleicher Config
- [ ] Varianten-Replay mit anderem Seed-Dokument startet korrekt
- [ ] Preflight-Check warnt bei nicht verfügbarem Modell
- [ ] `replayed_from_run_id` ist im neuen Run gesetzt
- [ ] Test: Replay-Endpoint gibt 202 und neue run_id
