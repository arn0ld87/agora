# Ticket 5: Export Endpoint

**Blocked by:** 1
**Size:** s
**Layer:** 3 (API)

## Aufgabe

`GET /api/runs/<run_id>/export` — ZIP-Download mit Manifest + Artefakten.

## Scope

- Endpoint in `backend/app/api/runs.py`
- Erzeugt ZIP mit:
  - `manifest.json`
  - Run-Artefakte (Logs, generierte Inhalte — was im Run-Dir liegt)
- Streaming-Response (kein Temp-File)
- Dateiname: `agora-run-<run_id>.zip`

## Akzeptanz

- [ ] ZIP enthält `manifest.json`
- [ ] ZIP enthält Run-Artefakte
- [ ] Keine Secrets in der ZIP
- [ ] Test: Export-Endpoint gibt 200 mit ZIP
