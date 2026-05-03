# Arbeitsprotokoll Sub-Slice J.3 — agentLog-Polling-Intervall (Issue #221)

**Datum:** 2026-05-03
**Branch:** `fix/task-J3-agentlog-interval`
**Scope:** `frontend/src/components/Step4Report.vue`, `frontend/src/components/__tests__/Step4Report.spec.ts`

## Befund (Audit J)

`Step4Report.vue` enthält zwei unabhängige `useIncrementalLogPolling`-Aufrufe:

| Polling-Target | Intervall vorher |
|---|---|
| agentLog | **1500 ms** |
| consoleLog | 2000 ms |
| statusPolling | 2500 ms |

Das agentLog-Intervall war mit 1500 ms der schnellste Loop im gesamten System und erzeugte im steady-state ~1.5 Requests/s allein fuer Step4 — ohne UX-Mehrwert gegenueber einem auf 2500 ms angepassten Wert.

## Aenderung

**Datei:** `frontend/src/components/Step4Report.vue`, Zeile 208

```diff
- intervalMs: 1500,
+ intervalMs: 2500, // Sub-Slice J.3 (#221): auf 2500 ms angeglichen (Konsistenz mit statusPolling, -33 % Backend-Last)
```

Nur dieses eine Intervall wurde veraendert. `consoleLog` (2000 ms) und der `setTimeout`-Wert fuer den Highlight-Effekt (Zeile 440, ebenfalls 1500 ms, aber UI-Animation) bleiben unveraendert.

## Test (Step4Report.spec.ts)

Neues `describe`-Block "Step4Report — agentLog-Polling-Intervall (Sub-Slice J.3)":

1. **`ruft useIncrementalLogPolling fuer agentLog mit intervalMs=2500 auf`** — mountet die Komponente, findet den agentLog-Aufruf (erkennbar an `parseLine: parseAgentEntry`) und assertet `{ intervalMs: 2500 }`.
2. **`consoleLog-Polling bleibt bei 2000 ms (unveraendert)`** — assertet den consolLog-Aufruf (kein `parseLine`) auf `{ intervalMs: 2000 }`.

Dafuer wurde `useIncrementalLogPolling` als File-level-Mock (`vi.mock`) registriert, was das gesamte Test-File beeinflusst. Der Mock liefert das gleiche Return-Shape wie das echte Composable (`lines: ref([])`, `polling: { start, stop }`, `reset: fn`), sodass alle bestehenden Tests (Sub-Slice 15, 16a, 16b) weiterhin gruen bleiben.

## Ergebnis

```
Test Files  18 passed (18)
     Tests  148 passed (148)   # +2 gegenueber Vorher (146)
```

`npm run check` vollstaendig gruen: vue-tsc clean, alle 148 Tests, Build success.

## Begründung

- Konsistenz: alle drei Polling-Loops in Step4 laufen nun mit >= 2000 ms.
- Backend-Last: -33 % Requests fuer den agentLog-Endpoint (1500 ms → 2500 ms = 0.67 vs. 0.4 Req/s).
- UX-Regression: keine — der Log-Refresh verzögert sich um maximal 1 s mehr. Agent-Logs sind informativ, nicht zeitkritisch.
