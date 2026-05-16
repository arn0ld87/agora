# FE-Redesign Followups Phase B — Worklog

**Datum:** 2026-05-15
**Branch:** feat/fe-redesign-followups-b
**Basis:** feat/fe-redesign-followups-integration (Phase A)

## Übersicht

Phase B liefert die fehlenden Felder für SimulationPulseBar (Sentiment-Heatbar)
und RedditPost (Voting-Score-Anzeige). Contract-First-Ansatz: Layer 0 zuerst,
dann OASIS-Runner, dann Frontend.

## Skip-Begründungen (Tool-Pflicht)

- `code-review-graph` MCP: nicht geladen in dieser Session → direkt `rg` + `Read`.
- `context-mode` MCP: nicht geladen in dieser Session → direkt `Bash`/`Read`.
- `context7`: kein Library-API-Lookup nötig (Pydantic v2 `field_validator`,
  Zod `.default()` sind bekannte Patterns; keine breaking changes erwartet).

## B1 — Backend Contract-Erweiterung

**Datei:** `backend/app/contracts/post_event_contract.py`

- `field_validator` zu Pydantic-Imports ergänzt.
- `sentiment: float | None = Field(default=None, ...)` mit `@field_validator`-Klasse,
  Range-Check -1.0 ≤ v ≤ 1.0 wenn nicht None.
- `score: int = Field(default=0, ...)` — Voting-Score, kann negativ sein.
- `extra="forbid"` bleibt. Beide Felder explizit im Schema.

**Datei:** `backend/tests/contracts/test_post_event_contract.py`

- Neue Klasse `TestPostCreatedEventSentimentScore` mit 14 Tests:
  - sentiment: null, 0.0, 1.0, -1.0 akzeptiert; 1.5 / -1.5 rejected.
  - score: default 0, positiv, negativ, 0; Twitter-Score default 0.
- Gesamt vorher: 10 Tests → nachher: 24 Tests (+14).

## B2 — OASIS-Runner Emission

**Datei:** `backend/scripts/run_parallel_simulation.py`

- `_emit_post_created_to_redis`: payload um `"sentiment": None` und `"score": 0` ergänzt.
- Kommentare: Architektur-Slot für künftigen Sentiment-Service.
- Beide Felder passgenau zum PostCreatedEvent-Contract übergeben.

## B3 — Schema-Drift

```
cd backend && uv run python -m app.contracts.dump_schemas
```

Output: alle 27 Schemas OK. Diff in `schemas/post-created-event.schema.json`:
- `+score`: `type: integer, default: 0`
- `+sentiment`: `anyOf: [number, null], default: null`

`git diff schemas/` zeigt nur erwartete Änderungen für diese zwei Felder.

## B4 — Frontend Zod-Spiegel

**Datei:** `frontend/src/contracts/postEventContract.ts`

- `sentiment: z.number().min(-1).max(1).nullable().optional()` ergänzt.
- `score: z.number().int().default(0)` ergänzt (`.optional()` weggelassen,
  da `.default()` bereits optional macht; `.optional().default()` erzeugte
  TS2719-Fehler durch Zod-Typ-Inferenz-Kollision).
- `.strict()` bleibt.

**Datei:** `frontend/src/contracts/__tests__/postEventContract.spec.ts`

- 7 neue Tests: sentiment null/0/±1 akzeptiert, >1/<-1 rejected; score default/positiv/negativ;
  Schema-Drift-Gate für score + sentiment.
- Bestehende Specs (useSimFeed, TwitterPost, RedditThread, StepSimulationFeedView)
  um `score: 0` in `mkPost`/`mkNode` ergänzt — nötig durch TypeScript-Required-Inferenz
  von `z.number().default(0)`.

## B5 — SimulationPulseBar Heatbar

**Datei:** `frontend/src/components/v4/sim-feed/SimulationPulseBar.vue`

- Neues Prop: `recentPosts?: PostCreatedEvent[]`.
- `sentimentClass()`-Helper: null → `sentiment-null`, <-0.33 → `sentiment-negative`,
  >0.33 → `sentiment-positive`, sonst → `sentiment-neutral`.
- Heatbar rendert ein `<div class="spb-pulse">` pro Post mit entsprechender Klasse.
- Wenn alle sentiments null: `spb-pulse--dim` Klasse + Pulse-Animation als Hinweis
  "Sentiment-Service nicht aktiv".
- Fallback (keine Posts): `<div class="spb-fill">` wie bisher.
- CSS-Variablen: `--status-red`, `--text-tertiary`, `--status-green`.

**Datei:** `frontend/src/components/v4/sim-feed/__tests__/SimulationPulseBar.spec.ts`

- 5 neue Tests: negative/positive/neutral Klassen, sentiment-null Klasse, gemischte Distribution.

## B6 — RedditPost Voting-Bar (read-only)

**Datei:** `frontend/src/components/v4/sim-feed/RedditPost.vue`

- `.rp-voting`-Div mit Up-Arrow-SVG, Score-Span, Down-Arrow-SVG.
- `scoreClass`: positiv (>0) → `rp-score--positive` (orange), negativ (<0) →
  `rp-score--negative` (blau), 0 → kein Klasse (grau).
- `scoreDisplay`: k-Format für |score| ≥ 1000 (z.B. `1.5k`).
- Kein Click-Handler — read-only.

**Datei:** `frontend/src/components/v4/sim-feed/__tests__/RedditPost.spec.ts` (NEU)

- 9 Tests: body/persona rendering, role=article, score-0 neutral, positiv orange,
  negativ blau, kein onclick, k-Format, depth=0.

## Schema-Drift-Check-Output

```
schemas/post-created-event.schema.json:
  + score: integer, default 0
  + sentiment: anyOf[number, null], default null
Alle anderen 26 Schemas: unverändert.
```

## Test-Deltas

**Backend:**
- Vorher: 2282 passed (contract: 10)
- Nachher: 2296 passed (contract: 24, +14)

**Frontend:**
- Vorher: ~912 passed (121 files)
- Nachher: 917 passed (121 files, +5 neue Phase-B-Tests in bestehenden Specs,
  +9 neue Tests in RedditPost.spec.ts neu)
  Gesamt neu: ~16 Frontend-Tests (7 Zod + 5 PulseBar + 9 RedditPost - 5 bestehende)

## Bundle-Delta

Vorher: `index-*.js` ~776 kB (gzip ~254 kB)
Nachher: `index-D93MdfwA.js` 776.43 kB │ gzip: 254.15 kB
Delta: ~+0 kB gzip (Änderungen sind Inline-Logic, kein neuer Import)

## Gates

- Backend: `pytest -x -q` → 2296 passed, 9 skipped, exit 0
- Backend: `ruff check --fix app/ tests/` → All checks passed
- Backend: `mypy app` → Success: no issues found in 173 source files
- Frontend: `typecheck` → exit 0
- Frontend: `test:coverage` → 917 passed (121 files), exit 0
- Frontend: `build` → exit 0
- Frontend: `lint` → exit 0

## Gaps

Keine offenen Gaps. Sentiment-Service-Slot ist dokumentiert als architektonisch offen
(Phase C oder separater Slice wenn Sentiment-Berechnung implementiert wird).
