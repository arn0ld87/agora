# Sub-Slice 24 — Gemini-Followup auf 20c (Frontend)

**Datum:** 2026-05-03
**Branch:** `feat/task-24-quota-frontend-gemini-followup`
**Layer:** 4 (Frontend)
**Refs:** Followup auf [PR #185](https://github.com/arn0ld87/agora/pull/185).

## Findings (Gemini auf PR #185)

| Schwere | Ort | Befund |
|---|---|---|
| HIGH | [`personaQuotaContract.ts:50`](frontend/src/contracts/personaQuotaContract.ts:50) | `buildQuotaPlanFromEntries` überschrieb bei doppeltem Segment-Namen statt zu addieren — UI-Anzeige (`Total: 20`) wich vom Payload (`total: 10`, last-wins-dict) ab |
| MEDIUM | [`Step2EnvSetup.vue:288`](frontend/src/components/Step2EnvSetup.vue:288) | hartkodierte deutsche Strings statt `vue-i18n` |
| MEDIUM | [`Step2EnvSetup.vue:774`](frontend/src/components/Step2EnvSetup.vue:774) | `v-for :key="idx"` → Fokus-Verlust beim Löschen mittlerer Zeilen |

## Fix

### 1. HIGH — Counts addieren statt überschreiben

```typescript
// vorher
targets[segment] = count;

// nachher
targets[segment] = (targets[segment] || 0) + count;
```

UI-Anzeige (`quotaTotal` summiert Array-Entries) und gesendeter Payload
(`Object.values(targets).reduce`) stimmen jetzt immer überein.

### 2. MEDIUM — i18n

Neue Keys `step2.quota.{toggle, hintOff, hintOn, segmentPlaceholder, addSegment, total, invalid}`
in beiden Locales [`de.json`](frontend/src/i18n/locales/de.json) und
[`en.json`](frontend/src/i18n/locales/en.json). Template + `quotaValidationError`
+ `startPrepare()`-Fallback nutzen jetzt `t(...)` statt Inline-Strings.

### 3. MEDIUM — Stable v-for-Key

Jeder `quotaEntry` bekommt eine eigene `id` (Counter + Date.now), erzeugt
in `_newEntryId()`. `v-for :key="entry.id"` statt `:key="idx"`. Auch der
LocalStorage-Reload via `_loadQuotaEntries()` vergibt neue IDs (alte
LocalStorage-Daten ohne `id` bleiben kompatibel — `id` wird beim Laden
neu generiert).

## Tests

Neu in [`personaQuotaContract.spec.ts`](frontend/src/contracts/__tests__/personaQuotaContract.spec.ts) — 2 Cases:

| Case | Erwartung |
|---|---|
| `[{a:5}, {a:3}, {b:2}]` | `targets={a:8,b:2}`, `total=10` |
| 3× `{a:1}` + `{b:4}` | `targets={a:3,b:4}`, `total=7` |

## Verifikation

```
$ npm test -- --run
16 Test Files passed | 137 Tests passed (vorher 135 → +2 für Doppel-Segment)

$ npm run lint
clean

$ npm run build
clean
```

## Geänderte Dateien

- `frontend/src/contracts/personaQuotaContract.ts` — `buildQuotaPlanFromEntries` addiert
- `frontend/src/contracts/__tests__/personaQuotaContract.spec.ts` — 2 neue Cases
- `frontend/src/components/Step2EnvSetup.vue` — i18n + stable id + entry counter
- `frontend/src/i18n/locales/de.json` — `step2.quota.*`-Block
- `frontend/src/i18n/locales/en.json` — `step2.quota.*`-Block
- `CHANGELOG.md` — `[Unreleased]` / Fixed-Block
