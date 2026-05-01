# p2 — Issue #131: Tool-Call/Error-Panel toggleable

**Issue:** [#131](https://github.com/arn0ld87/agora/issues/131)
**Start:** 2026-05-01
**Branch:** `claude/issue-131-toolpanel`
**Worktree:** `.claude/worktrees/issue-131-toolpanel`
**Aufwand-Schätzung:** size-s (½–1 Tag)

## Ziel
Das zweite Pane („Terminal / Console-Logs / Tool-Calls + Errors") ist standardmäßig collapsed; Toggle per Button und Hotkey; Inhalt unverändert, aber mit Filter „Nur Errors", Copy-as-JSON pro Eintrag und Sticky-Scroll (Wiederverwendung der Composable aus #130).

## Sub-Slice-Plan

### SUB1 — Polling-Composable + Sticky-Scroll für Console-Pane (1 Commit)
- `useIncrementalLogPolling` bekommt optionalen `stickyScroll`-Parameter; wenn vorhanden, `stickyScroll.markAppended(deltaCount)` statt blind `scrollTop = scrollHeight`.
- Default-Verhalten (kein `stickyScroll`) bleibt rückwärts-kompatibel.
- `Step3Simulation.vue` verdrahtet eine zweite `useStickyScroll`-Instanz für `consoleScrollEl` und übergibt sie an `useIncrementalLogPolling`. Banner unter dem Console-Pane.
- Tests: 1 neuer Composable-Test, dass `stickyScroll.markAppended` statt `scrollTop = scrollHeight` aufgerufen wird.
- **Akzeptanz:** Auch Console-Pane scrollt nicht mehr blind ans Ende.
- **Commit:** `feat(logs): sticky-scroll im incremental-log-polling (SUB1, Refs #131)`

### SUB2 — Collapsible Tool-Panel mit Toggle/Hotkey/Badge (1 Commit)
- Console-Pane wird in einen Collapsible-Container verpackt; Default = collapsed.
- Persistenz `localStorage` (`agora.ui.toolPanel.open`).
- Toggle-Button im Card-Head mit `aria-expanded`, Panel mit `role="region"` + `aria-label`.
- Hotkey `Ctrl+L` (mit `event.preventDefault()`); registriert nur, wenn der Karten-Container im DOM ist.
- Badge mit Counter ungesehener Errors. „Gesehen" = Panel war seit letztem Error mind. 1× geöffnet.
- i18n-Keys `step3.toolPanel.{toggle,show,hide,unread}`.
- **Akzeptanz:** Tool-Panel ist standardmäßig zu, lässt sich per Knopf oder `Ctrl+L` toggeln, Badge zählt ungesehene Errors korrekt.
- **Commit:** `feat(simulation): tool-panel collapsible mit hotkey/badge (SUB2, Refs #131)`

### SUB3 — Filter „Nur Errors" + Copy-as-JSON (1 Commit)
- Filter-Toggle im Tool-Panel-Head: `[Alle | Nur Fehler]`. Heuristik: line matched `/(error|exception|traceback|fatal|warn|warning)/i`.
- Copy-as-JSON pro Eintrag: kleiner `📋`-Button; legt `{"line": "...", "ts": Date.now()}` ins Clipboard via `navigator.clipboard.writeText`.
- i18n-Keys `step3.toolPanel.{filterAll,filterErrors,copyAsJson,copied}`.
- Tests: kleine Filter-Heuristik-Tests.
- **Akzeptanz:** Filter blendet Nicht-Error-Lines aus, Copy-Button kopiert JSON-Wrap; Issue #131 wird hier abgeschlossen.
- **Commit:** `feat(simulation): tool-panel filter + copy-as-json (SUB3, Closes #131)`

## Dependencies / Risiken
- `useIncrementalLogPolling` wird auch in `Step4Report.vue` genutzt — muss rückwärts-kompatibel bleiben (kein `stickyScroll` → Auto-Scroll wie heute).
- `navigator.clipboard.writeText` braucht Secure Context; im Dev-Server (HTTP) auf localhost ist das OK, sonst Fallback auf `document.execCommand('copy')` (deprecated, aber funktioniert).

## Out of Scope
- Step4-Report-Logs auf Sticky-Scroll umstellen → Folge-Issue [#141](https://github.com/arn0ld87/agora/issues/141).
- Strukturierte Tool-Call-Erfassung im Backend (heute streamen wir Plain-Text-stdout/stderr; ein „echtes" JSON-Tool-Call-Schema wäre eigenes Vorhaben).

## Tests / Quality Gate
- `npm run check` muss grün sein.
- Manuelles Klicken im Browser nach jedem Sub-Slice.

## Status

### SUB1 — abgeschlossen 2026-05-01
- [x] Implementiert: `useIncrementalLogPolling` mit optionalem `stickyScroll`-Param, `Step3Simulation` verdrahtet zweite Sticky-Instanz für Console-Pane
- [x] Tests grün (4 neue Vitest-Cases, `npm run check`: 744 Backend + 69 Frontend)
- [x] Commit erstellt
- [ ] Browser-Smoke (durch User)

### SUB2 + SUB3 — abgeschlossen 2026-05-01 (zusammengeführt)
- [x] Implementiert: collapsible Tool-Panel als eigene Card (`role="region"`, `aria-label`), Toggle-Button mit `aria-expanded` + Badge, Hotkey Ctrl+L/Cmd+L (mit `preventDefault()`), `localStorage`-Persistenz (`agora.ui.toolPanel.open`, default `false`), Watcher zählt ungesehene Errors via `/(error|exception|traceback|fatal|warn|warning)/i`-Heuristik. Filter-Toggle Alle/Nur Fehler, Copy-as-JSON pro Zeile via `navigator.clipboard.writeText` (Fallback `document.execCommand`). i18n DE/EN für `step3.toolPanel.*`.
- [x] Tests grün (`npm run check`: 744 Backend + 69 Frontend)
- [x] Commit erstellt (`Closes #131`)
- [ ] Browser-Smoke (durch User)

## CHANGELOG-Eintrag (Vorschau)
```
### Added
- Inkrementelles Log-Polling unterstützt optional Sticky-Scroll; Console-Pane in Step3 nutzt es (#131).
- Tool-Panel in Step3 ist standardmäßig collapsed mit Toggle (Ctrl+L), Badge für ungesehene Errors, A11y-Attributen (#131).
- Tool-Panel: Filter „Nur Errors" + Copy-as-JSON pro Log-Zeile (#131).
```
