# Worklog: FE-Redesign Slice 5 — Sim-Feed Dual-Column

**Datum:** 2026-05-15  
**Branch:** feat/fe-redesign-5-sim-feed  
**Commit:** bbaf360

---

## Was die View kann

StepSimulationFeedView rendert eine Dual-Column-Ansicht:

- **Reddit-Column (links):** threaded via `parent_post_id`, max-depth 4 visuell, "Weitere Replies"-Button bei Tiefe >= 4. Jeder Root-Thread als `<RedditThread>` mit rekursiver Einrückung (16px pro Ebene). Identitätsrail (2px farbige Linie) ab depth 1.
- **Twitter-Column (rechts):** flat, neueste Posts oben (DESC), `<TransitionGroup name="slide-in">` mit 200ms ease, `prefers-reduced-motion`-aware.
- **SimulationPulseBar:** Oben, zeigt Live-Dot (pulsiert, reduced-motion-aware), activityRate (Posts/min, EMA über letzte 30 Posts), Reddit-Count, Twitter-Count. Heatbar einfarbig (Accent) — Sentiment-Feld folgt in Followup-Slice.
- **PersonaAvatar:** 32px Kreis, Initialen aus `persona_id`, farbiger Ring nach `voice_register` (formal=blau, casual=grün, jugendsprache=lila), Badge-Buchstabe unten rechts.
- **SimBadge:** Amber-Pill "SIM" auf jedem `is_simulated=true`-Post — Wording-Glossar v1 konform.
- **FeedColumn:** Generischer Container mit `role="feed"`, Auto-Scroll-Pin via `IntersectionObserver` auf unterem Anker, Pause-Chip bei manuellem Scroll.
- **Tab-Switch:** StepSimulationView hat nun Tabs-Komponente mit "Pipeline" / "Live-Feed" — schaltet zwischen Step3Simulation und StepSimulationFeedView.
- **Route:** `/v4/simulation/:simulationId/feed` → `StepSimulationFeed`.

---

## useEventStream-API

useEventStream hat **kein** `.on()`-Pattern. Die handlers werden im Constructor als zweites Argument `{ post_created, state, control, ... }` übergeben. Plan Step 5.1 zeigte `stream.on('post_created', cb)` — das ist falsch. Tatsächliche Implementierung:

```typescript
const stream = useEventStream(simulationId, {
  post_created: (data) => feed.ingest(data),
})
```

---

## Test-Delta

| File | Tests |
|---|---|
| useSimFeed.spec.ts | 8 |
| PersonaAvatar.spec.ts | 2 |
| SimBadge.spec.ts | 2 |
| TwitterPost.spec.ts | 4 |
| RedditThread.spec.ts | 3 |
| FeedColumn.spec.ts | 3 |
| SimulationPulseBar.spec.ts | 4 |
| StepSimulationFeedView.spec.ts | 3 |
| **Gesamt neu** | **29** |

Gesamt-Suite: 869 Tests, alle grün (vorher 840).

---

## Bundle-Delta

- `StepSimulationFeedView-*.js`: 7.51 kB / **2.78 kB gzip** (lazy-loaded Chunk)
- Unter Budget (+50 kB gz).
- sim-feed-Komponenten sind in StepSimulationView direkt importiert → landen im SimulationView-Chunk (lazy).

---

## Followups

1. **Sentiment-Feld:** `PostCreatedEvent` hat kein `sentiment`-Feld. Pulse-Bar zeigt deshalb nur Activity-Counter, Heatbar bleibt einfarbig. Sobald Backend das Feld liefert → Stripe-Colors in SimulationPulseBar eintragen.
2. **Voting auf RedditPost:** Backend-Feld `upvotes`/`downvotes` fehlt im Contract. RedditPost zeigt keine Vote-Bar.
3. **Auto-Scroll-Pin:** IntersectionObserver-Integration in FeedColumn — jsdom hat keinen IO, daher Mock im Test. In Produktion getestet via manuellem Scroll.
4. **Tab-Route-Sync:** Aktiver Tab wechselt nicht per URL — `urlSync=false` gewählt weil Feed-Route bereits eigene URL hat. Könnte in Followup auf `useRouter.push` umgestellt werden.

---

## Skip-Begründungen

- `code-review-graph get_minimal_context_tool`: MCP nicht verfügbar im Session-Kontext → direkt Read/Bash.
- `context7` für Vue 3: Composition-API-Pattern aus bestehendem Repo-Code abgeleitet (useEventStream, Tabs.vue, RunsDashboard.spec.ts).
- `sequential-thinking`: Task war klar durch Plan + Pre-Flight-Read erschlossen, kein ambiger Multi-Layer-Scope.
