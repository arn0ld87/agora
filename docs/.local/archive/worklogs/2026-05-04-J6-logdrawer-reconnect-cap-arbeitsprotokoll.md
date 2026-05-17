# Sub-Slice J.6 — LogDrawer SSE Reconnect-Cap

**Datum:** 2026-05-04
**Branch:** fix/j6-logdrawer-reconnect-cap
**Referenz:** Audit-Empfehlung 7 (docu/2026-04-22-refactoring-produkt-audit.md)

## Ausgangslage

`LogDrawer.vue` nutzte `EventSource.onerror` ohne jeglichen Reconnect-Cap. Der Browser
versucht nach einem SSE-Fehler automatisch alle ~3 s neu zu verbinden. Bei dauerhaftem
Backend-Ausfall hammerte die Verbindung unbegrenzt weiter — ohne UI-Feedback und ohne
Abbruchbedingung. Das Gegenstück `useEventStream.ts` löst dieses Problem seit PR #9
mit `MAX_RECONNECT_ATTEMPTS = 5`; LogDrawer hatte diese Absicherung nie erhalten.

## Geänderte Dateien

### `frontend/src/components/LogDrawer.vue`

- **Konstante** `MAX_RECONNECT_ATTEMPTS = 5` neben `RING_BUFFER_MAX` eingefügt.
- **Reaktiver State** `streamFailed = ref(false)` für Template-Binding hinzugefügt.
- **Nicht-reaktiver Counter** `let reconnectAttempts = 0` analog zu `lastOffset` als
  modul-lokale Variable (kein `ref` — reaktive Änderungen des Counters selbst sind
  nicht nötig; nur `streamFailed` steuert das Template).
- **`startStream()`** setzt `streamFailed.value = false` am Anfang (bewusster Start
  zählt nicht als Fehler).
- **`onerror`-Handler** erhöht `reconnectAttempts`. Bei `>= MAX_RECONNECT_ATTEMPTS`:
  `stopStream()` → `streamFailed.value = true` → exhausted-Message → `return`.
  Darunter: bisheriges Verhalten (warn + connectionError-Statuszeile).
- **`onmessage`-Handler** resettet `reconnectAttempts = 0` bei jeder validen Nachricht,
  setzt `streamFailed.value = false` zurück (kurze Hiccups akkumulieren nicht).
- **`manualReconnect()`** neue Funktion: Counter und State zurücksetzen, `startStream()`.
- **Template** — neuer `v-if="streamFailed"` Reload-Button mit CSS-Klassen
  `close-btn reconnect-btn` (identischer Stil wie bestehende Drawer-Buttons, nur
  `width: auto` und Error-Farbe für Erkennbarkeit), Label aus i18n.
- **Style** — `.reconnect-btn` Differenzierung: `width: auto; padding: 0 10px;
  color: var(--status-error)`.

### `frontend/src/i18n/locales/de.json`

Zwei neue Keys in der `logs.drawer`-Sektion:
- `reconnectExhausted`: "Verbindung zum Log-Stream nach mehreren Versuchen abgebrochen."
- `reconnect`: "Erneut verbinden"

### `frontend/src/i18n/locales/en.json`

Gespiegelt:
- `reconnectExhausted`: "Log stream connection lost after multiple attempts."
- `reconnect`: "Reconnect"

### `frontend/src/components/__tests__/LogDrawer.spec.ts` (neu)

Neu angelegt (kein pre-existierender Spec vorhanden).

## Tests

### Befund

`npx vitest run src/components/__tests__/LogDrawer.spec.ts` → 2/2 PASS.
Gesamt-Suite `npx vitest run` → 158/158 PASS (vorher: 156, d. h. +2 neue Cases).

### Test-Case 1: Reconnect-Cap greift

Mock-`EventSource` wird 5× mit `onerror` gefeuert. Erwartung:
- `close()` wurde aufgerufen (stopStream)
- `.reconnect-btn` ist im DOM sichtbar

### Test-Case 2: Counter-Reset bei message

3 Errors → valide Message → Counter reset → 4 weitere Errors (kein Cap) →
1 weiterer Error (5. nach Reset → Cap). Erwartung:
- Nach 3 Errors + Message: kein `.reconnect-btn`
- Nach 4 weiteren Errors (Gesamt 3+4=7, aber Counter nach Reset bei 4): kein Cap
- Nach dem 5. Post-Reset-Error: `.reconnect-btn` sichtbar, `close()` aufgerufen

### Mock-Pattern

`EventSource` als globale Klasse durch `MockEventSource` ersetzt (vor dem Import
des SUT). Die `FakeSourceHandle`-Schnittstelle stellt `fireMessage()` und
`fireError()` für Test-Kontrolle bereit. Pattern analog zu `useEventStream.spec.ts`
(dort wird `openSimulationStream` gemockt, hier die Klasse selbst — weil LogDrawer
`new EventSource()` direkt aufruft).

## Edge-Cases

**Counter-Reset-Fenster:** Der Counter wird per `onmessage` auf 0 zurückgesetzt —
nicht per Timer. Das ist bewusst: Ein kurzer Hiccup (1–2 Fehler, dann Message-Erfolg)
gibt dem Drawer einen frischen 5er-Cap. Akkumulation über lange Zeit ohne Messages
wird damit korrekt behandelt.

**`startStream()` resettet `streamFailed`:** Wenn der User auf "Erneut verbinden"
klickt, setzt `manualReconnect()` erst Counter und Flag zurück, ruft dann
`startStream()` — das setzt Flag nochmals auf `false` (idempotent, kein Problem).

**Pre-existing TS-Fehler:** `vue-tsc --noEmit` zeigt 2 Fehler in
`Step4Report.spec.ts` (Zeilen 416, 420). Diese Fehler existieren auch vor meinen
Änderungen (per `git stash`-Verifikation bestätigt). Meine Änderungen führen keine
neuen TS-Fehler ein. Tests und Build sind grün.

## Akzeptanz-Checkliste

- [x] `MAX_RECONNECT_ATTEMPTS = 5` Konstante in LogDrawer.vue
- [x] `onerror` cappt nach 5 Versuchen: `stopStream()` + `streamFailed=true`
- [x] `onmessage` resettet `reconnectAttempts` auf 0
- [x] Reload-Button bei `streamFailed === true` (i18n-Label, Drawer-Button-Stil)
- [x] `manualReconnect()` setzt Counter + State zurück
- [x] i18n-Keys `reconnectExhausted` + `reconnect` in de.json und en.json
- [x] Vitest-Cases: Cap-Test + Counter-Reset-Test (2 Cases, alle grün)
- [x] Lint sauber (eslint .)
- [x] Build erfolgreich (vite build)
- [x] CHANGELOG-Eintrag
- [x] Dieses Arbeitsprotokoll
