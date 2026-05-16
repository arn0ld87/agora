# Sub-Slice 26 — frontend/src/api/*.js → *.ts Migration

**Datum:** 2026-05-03
**Branch:** `feat/layer-6-task-19-frontend-api-ts`
**Refs:** #71 (Layer 6, Task 19)

## Scope

Migration aller 7 JavaScript-Module in `frontend/src/api/` nach TypeScript.
Kein Verhalten geändert — nur Typen ergänzt.

## Migrationstabelle

| Modul | Zeilen (vorher JS) | Zeilen (nachher TS) | Types aus contracts/ | Neue lokale Types |
|---|---|---|---|---|
| `graph.js → graph.ts` | 113 | 161 | — | `BuildGraphData`, `TaskStatusResponse`, `GraphDataResponse`, `ProjectResponse`, `GraphSnapshotResponse`, `GraphDiffResponse` |
| `index.js → index.ts` | 135 | 154 | — | Signaturen: `setAgoraToken(string\|null)`, `getAgoraToken(): string`, `requestWithRetry<T>`, Response-Interceptor `any`-Cast mit Reason-Kommentar |
| `logs.js → logs.ts` | 25 | 47 | — | `FetchLogsParams`, `LogEntry`, `FetchLogsResponse` |
| `report.js → report.ts` | 82 | 160 | `Report`, `EvidenceMap`, `ReportSection`, `EvidenceItem` aus `reportContract.ts`; `ApiEnvelope` aus `envelope.ts` | `GenerateReportData`, `ReportStatusParams`, `ReportStatusData`, `LogEnvelope`, `ChatWithReportData`, `ChatData` |
| `settings.js → settings.ts` | 32 | 47 | — | `SettingsResponse`, `SettingsSchemaResponse`, `SecretsPayload` |
| `simulation.js → simulation.ts` | 319 | 518 | `PersonaQuotaPlan` aus `personaQuotaContract.ts` | `SimulationPlatform`, `CreateSimulationData`, `PrepareSimulationData`, `TaskStatusData`, `StartSimulationData`, `StopSimulationData`, `SimulationRecord`, `ProfileRecord`, `ProfileQualityResponse`, `RunStatusResponse`, `EnvStatusData`, `CloseEnvData`, `InterviewAgentsData`, `ModelPreset`, `AvailableModelsResponse`, `BranchData`, `BranchRecord`, `PersonaTemplateRecord`, `SimulationActionsParams`, `TimelineResponse`, `AgentStatsResponse` |
| `stream.js → stream.ts` | 60 | 108 | — | `SseHelloPayload`, `SsePingPayload`, `SseEventFrame`, `StreamHandlers`, `TicketApiResponse` |

## Types aus contracts/

- `frontend/src/contracts/reportContract.ts`: `Report`, `EvidenceMap`, `ReportSection`, `EvidenceItem` (alle via `z.infer`)
- `frontend/src/contracts/personaQuotaContract.ts`: `PersonaQuotaPlan` (via `z.infer`)
- `frontend/src/api/envelope.ts`: `ApiEnvelope<T>` für report.ts Return-Types

## Besondere Entscheidungen

### index.ts — Response-Interceptor

Der Interceptor gibt `response.data` (das Envelope-Objekt) zurück statt des `AxiosResponse`. Das ist die bestehende Architektur: Konsumenten erhalten direkt `{ success, data, ... }`. Der Interceptor ist mit `: any` annotiert und einem Reason-Kommentar, weil das Axios-Typsystem den intentionellen Type-Widening-Schritt nicht ausdrücken kann.

### report.ts — Envelope vs. Unwrapped

Die Funktionen geben `ApiEnvelope<T>` zurück, weil der `index.ts`-Interceptor die Envelope-Body-Struktur weiterreicht (nicht auspackt). `Step4Report.vue` und `useIncrementalLogPolling` greifen auf `res.success` und `res.data` zu — das bestätigt den echten Return-Shape.

Für `getAgentLog`/`getConsoleLog` wird `LogEnvelope` verwendet statt `ApiEnvelope<LogData>`, damit die Typen exakt mit dem `fetcher`-Contract des JS-Composables `useIncrementalLogPolling` kompatibel sind.

### stream.ts — SSE-Event-Types

Abgeleitet aus `backend/app/api/simulation_stream.py`:
- `hello`: `{ simulation_id, ts }`
- `ping`: `{ ts }`
- `state`/`control`: `{ type, simulation_id, payload, ts }` (SseEventFrame)

Kein Zod-Spiegel für SSE (das ist Layer-0-Arbeit).

### package.json — check-Script und vue-tsc

`vue-tsc` + `typescript` wurden als devDependencies hinzugefügt und ein `check`-Script ergänzt (`vue-tsc --noEmit && npm run test && npm run build`), da das Projekt keines hatte.

### Step4Report.vue — AgentLogEntry Index-Signature

Pre-existing Type-Fehler: `entryAnchorId(e: Record<string, unknown>)` wurde mit `AgentLogEntry` (ohne Index-Signature) aufgerufen. Fix: `[key: string]: unknown` zu `AgentLogEntry` ergänzt. Dieser Fehler war vor der vue-tsc-Einführung nicht sichtbar.

### .js-Extension-Imports

Zwei Konsumenten importierten noch mit `.js`-Extension:
- `frontend/src/views/Home.vue`: `../api/simulation.js` → `../api/simulation`
- `frontend/src/components/HistoryDatabase.vue`: `../api/simulation.js` → `../api/simulation`

## Verifikation

```
npm run check:  vue-tsc clean + 137 Tests grün + Build erfolgreich
rg .js-imports: OK keine .js-Extension-Imports
backend pytest: 1282 passed, 9 skipped (keine Regression)
```
