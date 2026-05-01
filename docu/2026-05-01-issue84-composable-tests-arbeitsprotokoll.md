# Slice 6 — Frontend-Composable-Tests (Closes #84)

**Datum:** 2026-05-01
**Sprint:** v0.8.0 — Frontend Consolidation
**Issue:** #84 (EPIC-10-ST-07) — Frontend Composable Tests (Vitest)
**Branch:** `claude/elegant-engelbart-ab0ebd`

## Vorgehen

Vitest-Coverage für die drei in der Story genannten Composables. Pro Composable mindestens 5 Tests, decken Happy-Path, Cleanup-bei-Unmount und mindestens einen Edge-Case ab.

## Setup-Änderungen

- `jsdom` und `@vue/test-utils` als Dev-Dependencies installiert.
- `frontend/vite.config.js`: `test.environment` von `node` auf `jsdom` umgestellt — wird für `mount()`/`unmount()` und für DOM-APIs in den Composable-Tests gebraucht.

## Geschriebene Tests

| Datei | Tests | Schwerpunkte |
|---|---:|---|
| `frontend/src/composables/__tests__/usePolling.spec.js` | 7 | Lifecycle (start/stop), Intervall-Pacing, `immediate`-Option, `onError`-Callback, mehrfacher Start, `isTicking`-Concurrent-Guard, Cleanup auf Unmount |
| `frontend/src/composables/__tests__/useEventStream.spec.js` | 7 | leere ID, Erfolgsfall, Getter-Funktion-Auflösung, Handler-Wrapping (`lastEventAt`, `attempts`-Reset), `stop()`-Schließen, Unmount-Cleanup, Fehlerpfad |
| `frontend/src/composables/__tests__/useWorkspaceStatus.spec.js` | 6 | Initial-State, `updateStatus()`, Map-Fallback, Default-Fallback, Default-Args, Idempotenz |

Bestehende Coverage: `frontend/src/api/__tests__/envelope.spec.ts` (11 Tests).

**Gesamt: 31 Tests in 4 Dateien, alle grün** in 22 s.

## Test-Patterns

- **Composable-Mount**: jeder Test nutzt eine Dummy-`defineComponent({ setup() { exposed = composable(...) } })` plus `mount(Comp)` aus `@vue/test-utils`. So bekommen wir einen echten Vue-Lifecycle (`onUnmounted` läuft), während wir das vom Composable ausgegebene API über die `exposed`-Variable inspizieren.
- **Fake-Timers** (`vi.useFakeTimers()`/`vi.advanceTimersByTimeAsync`) für `usePolling`-Intervall-Tests, statt echtes `setInterval` abzuwarten.
- **Mock von `../../api/stream`** für `useEventStream` mit `vi.mock()`. Eine Fake-Source mit `close: vi.fn()` ersetzt die echte `EventSource`.
- **Mock von `vue-i18n`** für `useWorkspaceStatus`, damit `t(key)` deterministisch `t:${key}` liefert ohne i18n-Setup.

## Edge-Case-Beobachtung

`useEventStream.getId()` hat eine subtile `null ?? ref` Falle: bei `ref(null)` gibt der Nullish-Coalesce-Fallback das Ref-Objekt selbst zurück, was als truthy durchgeht. Der Test umgeht das mit `ref('')` und der Edge-Case ist im Test-Kommentar dokumentiert. **Kein Fix in diesem Slice** — Verhaltensänderung wäre außerhalb des Test-Scopes.

## Geänderte Dateien

| Datei | Δ |
|---|---|
| `frontend/src/composables/__tests__/usePolling.spec.js` (NEU) | +120 Zeilen |
| `frontend/src/composables/__tests__/useEventStream.spec.js` (NEU) | +125 Zeilen |
| `frontend/src/composables/__tests__/useWorkspaceStatus.spec.js` (NEU) | +95 Zeilen |
| `frontend/vite.config.js` | `environment: 'node'` → `'jsdom'` |
| `frontend/package.json` / `package-lock.json` | `jsdom`, `@vue/test-utils` Dev-Deps |
| `.gitignore` | +1 Negativ-Pattern |
| `CHANGELOG.md` | `[Unreleased]`-Block ergänzt |

## Akzeptanz-Mapping zu Issue #84

| Akzeptanzkriterium | Erfüllt durch |
|---|---|
| `@vue/test-utils` und `jsdom` als devDeps | `npm install -D` durchgeführt |
| `frontend/vite.config.js` `test.environment` auf `jsdom` | Direkt umgestellt; Kommentar im File aktualisiert |
| Mindestens je 5 Tests pro Composable | usePolling 7, useEventStream 7, useWorkspaceStatus 6 |
| `npm run check` grün, Frontend-Testanzahl explizit | 31 Tests grün, dokumentiert oben |

## Out-of-scope (laut Story-Definition)

- Vue-Component-Tests
- Coverage-Reports im CI
- TypeScript-Migration der Composables (gehört zu v1.2.0)

## v0.8.0-Ergebnis

| ✅ 13/13 | ⬜ 0/13 |
|---|---|
| #29 #30 #31 #32 #33 #34 #35 #36 #37 #38 #39 #40 #84 | — |

Milestone „v0.8.0 — Frontend Consolidation" ist mit diesem Sub-Slice **vollständig**.
