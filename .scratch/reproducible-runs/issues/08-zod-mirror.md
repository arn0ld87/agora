# Ticket 8: Zod Mirror + Frontend Contracts

**Blocked by:** 1
**Blocks:** 6
**Size:** s
**Layer:** 6 (Frontend Contracts)

## Aufgabe

TypeScript/Zod-Spiegel des `RunManifest`-Contracts.

## Scope

- `RunManifestSchema` in `frontend/src/contracts/runManifestContract.ts`
- `ReplayRequestSchema`, `ReplayResponseSchema`
- `ManifestStatusSchema`, `ManifestInputsSchema`, etc.
- API-Client-Typen in `frontend/src/types/run.ts`:
  - `RunManifest`, `ReplayRequest`, `ReplayResponse`
- `getRunManifest(run_id)` in `frontend/src/api/runs.ts`

## Akzeptanz

- [ ] Zod-Schemas validieren gegen JSON-Schema aus Ticket 1
- [ ] TypeScript-Types sind konsistent mit Pydantic-Modell
- [ ] `bun run check` grün
