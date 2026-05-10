# M11.4b-Followup-3 · Playwright-Timeout + waitUntil-Strategie

**Datum:** 2026-05-10
**Branch:** `fix/m11-4b-followup-3-playwright-goto`
**Sub-Slice-ID:** M11.4b-Followup-3

---

## Symptom

CI-Run für `adb3934` (Backend vollständig gefixt, Stub-Mode aktiv):

```
upload-graph.spec.ts:155
  await page.goto(`/process/${projectId}`, { waitUntil: 'networkidle', timeout: 60_000 });
Error: page.goto: Test timeout of 30000ms exceeded.

minimal-report.spec.ts:229
  await page.goto(`/report/${report_id}`, { waitUntil: 'networkidle' });
Error: page.goto: Test timeout of 30000ms exceeded.
```

Backend-Container-Logs bestätigten korrekten Stub-Betrieb — Fehler lag ausschließlich im Frontend/Playwright.

---

## Zwei systematische Bugs

### Bug 1 — Test-Total-Timeout 30s (Playwright-Default)

`page.goto({ timeout: 60_000 })` setzt nur den **Action-Timeout** (Wie lange `goto` selbst warten darf), NICHT den **Test-Total-Timeout**. Playwrights Default ist 30s pro Test. Da Upload + Ontology + Graph-Build + Report-Generation zusammen mehr als 30s brauchen (auch im Stub-Modus mit CI-Cold-Start), schlägt der Test am Total-Timeout an, bevor `goto` überhaupt 60s warten kann.

**Fix:** `test.setTimeout()` am Anfang der jeweiligen Test-Callbacks (targeted, kein Global-Bump in `playwright.config.ts`):
- `upload-graph.spec.ts`: `test.setTimeout(180_000)` (3 Min)
- `minimal-report.spec.ts`: `test.setTimeout(300_000)` (5 Min — 11 Sections × 4 ReACT-Iterationen)

### Bug 2 — `waitUntil: 'networkidle'` Anti-Pattern für SPAs

SPAs mit Polling (Pinia-State-Polling via `/api/report/<id>` oder `/api/graph/task/<id>`) oder SSE erreichen den `networkidle`-State (≥500 ms ohne Network-Request) strukturell nie. Der Browser wartet ins Leere bis der Test-Timeout schlägt.

**Fix:** `'networkidle'` ersetzen durch `'domcontentloaded'` in allen `page.goto`-Calls:
- `'domcontentloaded'`: HTML-Parser durch, Inline-Scripts ausgeführt — deterministisch und frühzeitig.
- Nachfolgende `expect(...).toBeVisible()` mit Auto-Wait sind der robuste Mount-Indikator.

---

## Geänderte Dateien

### `frontend/tests/e2e/upload-graph.spec.ts`

| Stelle | Vorher | Nachher |
|--------|--------|---------|
| Test-Callback-Anfang | (kein setTimeout) | `test.setTimeout(180_000)` |
| `page.goto` Zeile 155 | `waitUntil: 'networkidle'` | `waitUntil: 'domcontentloaded'` |

### `frontend/tests/e2e/minimal-report.spec.ts`

| Stelle | Vorher | Nachher |
|--------|--------|---------|
| Test-Callback-Anfang | (kein setTimeout) | `test.setTimeout(300_000)` |
| `page.goto` Zeile 229 | `waitUntil: 'networkidle'` | `waitUntil: 'domcontentloaded'` |

### `frontend/tests/e2e/health.spec.ts`

| Stelle | Vorher | Nachher |
|--------|--------|---------|
| `page.goto('/')` Zeile 25 | `waitUntil: 'networkidle'` | `waitUntil: 'domcontentloaded'` |

**Begründung Health-Smoke-Anpassung:** Test 3 in `health.spec.ts` hatte dasselbe `networkidle`-Anti-Pattern. Er war in M11.4a grün, aber das war Timing-Glück (SPA-Root ohne aktives Polling ist kurz ruhig). Die Korrektur macht ihn robuster — `toHaveTitle(/Agora/)` ist der Mount-Indikator via Auto-Wait. Test-Total-Timeout bleibt auf Default (30s), weil Health-Smoke schnell sein soll und kein Backend-Vorlauf nötig ist.

---

## waitUntil-Vorher/Nachher-Übersicht (alle e2e-Specs)

| Datei | Zeile | Vorher | Nachher |
|-------|-------|--------|---------|
| `health.spec.ts` | 25 | `'networkidle'` | `'domcontentloaded'` |
| `upload-graph.spec.ts` | 155 | `'networkidle'` | `'domcontentloaded'` |
| `minimal-report.spec.ts` | 229 | `'networkidle'` | `'domcontentloaded'` |

Kein `'networkidle'` verbleibt in `frontend/tests/e2e/`.

---

## Verifikation

```
# grep - kein networkidle mehr
grep -n "waitUntil" frontend/tests/e2e/*.spec.ts
  health.spec.ts:28:    await page.goto('/', { waitUntil: 'domcontentloaded' });
  upload-graph.spec.ts:162: { waitUntil: 'domcontentloaded', timeout: 60_000 }
  minimal-report.spec.ts:239: { waitUntil: 'domcontentloaded' }

# Frontend
npm run lint     → OK (0 Fehler)
npm run typecheck → OK (0 Fehler)
npm test -- --run → 45 passed, 461 tests

# playwright --list
Total: 6 tests in 3 files (alle korrekt registriert)

# Backend (unberührt)
ruff check app/ tests/ → All checks passed!
pytest -x -q -m "not llm" → 1691 passed, 9 skipped
```

---

## Nicht angefasst

- `playwright.config.ts` — kein Global-Timeout-Bump
- Backend-Files — kein Touch
- Neue Dependencies — keine
