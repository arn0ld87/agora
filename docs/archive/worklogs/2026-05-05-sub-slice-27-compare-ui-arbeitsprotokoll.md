# Sub-Slice 27 — Compare UI (BranchComparePanel) · 2026-05-05

**Closes:** [#67](https://github.com/arn0ld87/agora/issues/67)
**Layer:** 7 (Graph / Runs / Compare — Frontend)
**Backend-Voraussetzung:** Sub-Slice 24 (#66, commit `3584eb6`) — `GET /api/simulation/<id>/compare`

---

## Was wurde gebaut

| Datei | Typ | Anmerkung |
|---|---|---|
| `frontend/src/contracts/branchComparisonContract.ts` | NEU | Zod-Spiegel zu `backend/app/contracts/branch_comparison.py` |
| `frontend/src/composables/useBranchComparison.ts` | NEU | Composable analog zu `useGraphDiff.ts` |
| `frontend/src/components/compare/BranchComparePanel.vue` | NEU | SFC mit Top-Bar, Δ-Strip, Branch-Karten, Cluster-Listen |
| `frontend/src/components/compare/__tests__/BranchComparePanel.spec.ts` | NEU | 10 Tests |
| `frontend/src/contracts/__tests__/branchComparisonContract.spec.ts` | NEU | 10 Tests |
| `frontend/src/composables/__tests__/useBranchComparison.spec.ts` | NEU | 9 Tests |
| `frontend/src/i18n/locales/de.json` | GEÄNDERT | `branchCompare`-Block hinzugefügt (35 Keys) |
| `frontend/src/i18n/locales/en.json` | GEÄNDERT | `branchCompare`-Block hinzugefügt (35 Keys) |
| `CHANGELOG.md` | GEÄNDERT | Added-Eintrag Sub-Slice 27 |

**Gesamt neue Dateien:** 6 · **Geänderte Dateien:** 3 · **i18n-Keys:** 35 (DE) + 35 (EN)

---

## Designentscheidungen

**ID-basierte Cluster-Listen statt Label-Match:**
`clusters_only_in_a`, `clusters_only_in_b`, `clusters_changed` nutzen `cluster_id` als Key. Labels werden angezeigt, aber nicht als Matching-Grundlage. Entspricht dem Pydantic-Modell (`ClusterChange.cluster_id` als gemeinsamer Bezugspunkt).

**Kein Single-Number-Score:**
Der Backend-Contract liefert keinen aggregierten Score. Die UI zeigt sechs separate Δ-Tiles, damit der Nutzer selbst gewichten kann, welche Dimension relevant ist.

**ClusterSummary-Reuse:**
`ClusterSummarySchema` wird direkt aus `graphDiffContract.ts` importiert (Single Source of Truth). Kein Duplikat in `branchComparisonContract.ts`.

**SegmentReach-Refine mit statischer Fehlermeldung:**
Die Zod-Refine-API in der verwendeten Version erlaubt keine Funktion als zweites Argument (TS-Fehler). Zwei separate `refine()`-Aufrufe mit statischen Meldungen — fachlich äquivalent zum Pydantic-Validator.

**`z.string()` für Zeitstempel:**
Analog zu `graphDiffContract.ts`. Offset-aware ISO-8601-Strings vom Backend werden akzeptiert, keine stricte `z.string().datetime()`-Prüfung — verhindert Ablehnungen bei leicht abweichenden Timestamp-Formaten.

**Direkter `fetch` ohne Auth-Wrapper:**
`useGraphDiff.ts` nutzt ebenfalls direkten `fetch` mit `credentials: "same-origin"`. Der Auth-Wrapper aus `frontend/src/api/stream.ts` ist spezifisch für SSE-Streams. Konsistent mit dem Stil-Anker.

---

## Out of Scope

- Persona-Diff (#69, Layer 8)
- Multi-Way-Compare (>2 Branches)
- Single-Number-Confidence-Score (Spike § 6.4)
- Backend-Änderungen (bereits fertig durch Sub-Slice 24)
- Modifikation von `branch_comparison.py` oder `schemas/branch-comparison.schema.json`
- Wiederverwendung von `GraphDiffPanel` (BranchMetrics != Graph-Snapshot)

---

## Akzeptanz-Snapshots

```
vue-tsc --noEmit:   0 errors
vitest:             236 passed (30 Test Files, davon 29 neu)
eslint:             clean (keine Warnings, keine Errors)
build:              1.71s, clean (chunk-size Warning ist pre-existing)
Voice-Lint:         clean (keine verbotenen Phrasen)
strict parse:       BranchComparisonSchema.parse() in useBranchComparison.ts:62
safeParse:          nicht in useBranchComparison.ts
```

---

## Backend-Pendant-Verweise

- `backend/app/contracts/branch_comparison.py` — Pydantic-Quelle (autoritativ)
- `schemas/branch-comparison.schema.json` — JSON-Schema-Dump
- `backend/app/api/simulation.py` — Endpoint-Implementierung
- `backend/app/services/compare_service.py` — Service-Logik
- `docs/2026-05-03-task-23-compare-model-spike.md` — Design-Spec
