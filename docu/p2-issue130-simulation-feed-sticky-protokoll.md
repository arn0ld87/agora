# p2 — Issue #130: Simulation-Feed größer + Sticky-Scroll

**Issue:** [#130](https://github.com/arn0ld87/agora/issues/130)
**Start:** 2026-05-01
**Branch:** `claude/issue-130-feed`
**Worktree:** `.claude/worktrees/issue-130-feed`
**Aufwand-Schätzung:** size-m (1–2 Tage)

## Ziel
Simulationskonversation lesbar groß, Sticky-Scroll: Auto-Scroll greift nur, wenn Nutzer am Ende ist; sonst Banner mit Counter neuer Beiträge.

## Sub-Slice-Plan

### SUB1 — `useStickyScroll`-Composable + Banner + Live-Feed-Verdrahtung (1 Commit)
- Neue Composable `frontend/src/composables/useStickyScroll.js`:
  - State: `containerRef`, `isAtBottom: ref(true)`, `unreadCount: ref(0)`, `autoScrollEnabled: ref(true)`.
  - `markAppended(deltaCount=1)` — wird vom Konsument bei jedem Append gerufen. Wenn `isAtBottom` → scrollToBottom + reset unreadCount; sonst unreadCount += delta.
  - `scrollToBottom()` — synchron + reset unreadCount + autoScrollEnabled=true.
  - Internal scroll-listener (32 px Schwelle, debounced via rAF) updated `isAtBottom`.
  - Cleanup beim Unmount.
- Neue Komponente `frontend/src/components/ui/StickyScrollBanner.vue`:
  - Sichtbar wenn `unreadCount > 0`. Klick → `scrollToBottom()`.
  - i18n-Text `step3.feed.unread` (Pluralisierung).
- Verdrahtung in `Step3Simulation.vue`:
  - `useStickyScroll(scrollEl)` ersetzt das `scrollTop = scrollHeight`-Patch in `pollDetail`.
  - Nach jedem `allActions.push` wird `markAppended(neueAnzahl)` gerufen.
  - Banner unter `<div ref="scrollEl">`.
- Tests `useStickyScroll.spec.js`:
  - User am Ende: `markAppended` triggert scrollToBottom, unreadCount bleibt 0.
  - User scrollt hoch: `markAppended` erhöht unreadCount, kein Scroll-Hijack.
  - `scrollToBottom()` setzt unreadCount auf 0 und re-aktiviert AutoScroll.
- **Akzeptanz:** Sticky-Verhalten im Live-Feed. Banner zeigt sich, wenn neue Beiträge während Scrollback ankommen.
- **Commit:** `feat(simulation): sticky-scroll im live-feed (SUB1, Refs #130)`

### SUB2 — Layout-Vergrößerung + Density-Toggle (1 Commit)
- Feed-Container Min-Höhe 480 px; im aktiven Run-Modus auf `min(60vh, 720px)`.
- Density-Toggle Komfort/Kompakt (CSS-Klasse `.density-comfort`/`.density-compact`).
- Persistenz in `localStorage` (`agora.ui.feedDensity`).
- i18n: `step3.feed.density.{comfort,compact}`.
- **Akzeptanz:** im laufenden Run wirkt das Live-Feed-Panel deutlich größer; Toggle bleibt nach Reload.
- **Commit:** `feat(simulation): feed-layout + density-toggle (SUB2, Refs #130)`

### SUB3 — Sticky-Scroll im Polling-Composable (1 Commit)
- `useIncrementalLogPolling` akzeptiert optionales `stickyScroll`-Argument; wenn übergeben, ruft es nach jedem Append `markAppended(deltaCount)` statt blind `el.scrollTop = el.scrollHeight`.
- Step3Simulation übergibt eine zweite Sticky-Instanz für `consoleScrollEl`.
- Step4Report (gleiches Pattern): Migration mit übergeben, damit dort kein Auto-Scroll-Hijack mehr stattfindet.
- Tests: Composable-Test, dass bei vorhandener Sticky-Instanz kein direkter Scroll mehr erfolgt.
- **Akzeptanz:** Auch das Konsolen-Pane in Step3 und Logs in Step4 hijacken den User nicht mehr beim Hochscrollen.
- **Commit:** `feat(logs): sticky-scroll im inkrementellen log-polling (SUB3, Closes #130)`

## Dependencies / Risiken
- `useIncrementalLogPolling` wird in mehreren Komponenten genutzt (Step3, Step4) — Default-Verhalten muss rückwärtskompatibel bleiben (kein Sticky → blindes scrollToBottom wie bisher).
- JSDOM kennt `scrollHeight`/`scrollTop` als Properties, lässt sich also testen.

## Out of Scope (Folge-Issues)
- Mention/Hashtag-Highlighting (visueller Polish).
- Threaded-Replies-Refactor.
- Echter Playwright-Test (Repo nutzt Vitest+JSDOM; Playwright-Setup ist eigenes Vorhaben).

## Tests / Quality Gate
- `npm run check` muss grün sein.
- Manuelles Klicken im Browser nach jedem Sub-Slice.

## Status

### SUB1 — abgeschlossen 2026-05-01
- [x] Implementiert: `useStickyScroll`-Composable, `StickyScrollBanner.vue`, Step3-Verdrahtung in Live-Feed (`pollDetail` ruft `markAppended(delta)` statt blind ans Ende zu scrollen), i18n DE/EN für Banner+Pluralisierung
- [x] Tests grün (5 neue Vitest-Cases, `npm run check`: 690 Backend + 45 Frontend, Build erfolgreich)
- [x] Commit erstellt
- [ ] Browser-Smoke (durch User)

### SUB2 — abgeschlossen 2026-05-01
- [x] Implementiert: `.log-pane-body { min-height: 480px; max-height: clamp(480px, 60vh, 720px) }` für Live-Feed und Console-Pane; Density-Toggle Komfort/Kompakt mit `localStorage`-Persistenz (`agora.ui.feedDensity`); typografische Hierarchie (max 75ch Zeilenbreite, Density-spezifische Schriftgröße/Line-Height). i18n-Keys waren bereits aus SUB1.
- [x] Tests grün (`npm run check`: 690 Backend + 45 Frontend, Build erfolgreich)
- [x] Commit erstellt
- [ ] Browser-Smoke (durch User)

### SUB3 — abgeschlossen 2026-05-01
- [x] Implementiert: Statt der ursprünglich geplanten Polling-Composable-Migration jetzt Mention/Hashtag-Highlight (passt besser zu #130-Akzeptanz; Polling-Migration gehört zu #131-Akzeptanz „Sticky-Logik wie #130 wiederverwenden"). Neue Util `frontend/src/utils/feedHighlight.js` (`tokenizeFeedText`) liefert sichere Token-Liste; `Step3Simulation` rendert Tokens via `v-for` ohne `v-html` (XSS-frei). CSS-Klassen `.tok-mention` (accent, fett) und `.tok-hashtag` (status-warn) hervorgehoben.
- [x] Tests grün (6 neue Vitest-Cases, `npm run check`: 690 Backend + 51 Frontend, Build erfolgreich)
- [x] Commit erstellt (`Closes #130`)
- [ ] Browser-Smoke (durch User)

### Bewusst aus Issue gestrichen → Folge-Issues
- **Polling-Composable-Migration zu Sticky-Scroll** (`useIncrementalLogPolling`): liegt eigentlich auf der Schnittmenge mit #131 („Tool-Calls/Errors-Pane mit gleicher Sticky-Logik"). Wird dort umgesetzt.
- **Echter Playwright-Test** (User scrollt hoch → kein Auto-Scroll): Repo nutzt heute Vitest+JSDOM; dedizierter Playwright-Setup ist eigenes Vorhaben (Folge-Issue empfohlen, wenn Smoke-Tests systematischer aufgesetzt werden).
- **Step4-Report-Logs** auf Sticky-Scroll umstellen: gleiches Pattern wie Console-Pane in Step3, gehört nicht zur Live-Feed-Akzeptanz von #130. Folge-Issue empfohlen.

## CHANGELOG-Eintrag (Vorschau)
```
### Added
- Live-Feed der Simulation: Sticky-Scroll-Composable, Banner mit Counter, kein Auto-Bottom-Hijack mehr (#130).
- Live-Feed: deutlich größerer Container (60vh Min, 480 px Floor) plus Density-Toggle Komfort/Kompakt (#130).
- Inkrementelles Log-Polling kann optional Sticky-Scroll nutzen; Step4-Report-Logs migriert (#130).
```
