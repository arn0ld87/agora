# Agora — UX/Config Batch (Mai 2026)

## Context

Sieben unabhängige UX/Config-Bugs nach v1.0.0, gebündelt für einen Sprint. Das ergibt sieben kleine, eigenständige Commits (idealerweise auch eigene PRs nach `docs/runbooks/pr-workflow.md`).

Branch: alle Arbeit auf `claude/refine-local-plan-abVZP` (vorgegeben).

**Korrekturen ggü. dem Draft (durch Code-Lesen verifiziert):**
- `Step3Simulation.vue` hat **nicht** bereits 2 Spalten — `.logs-grid` enthält genau 1 Pane (`Live-Feed`, mixt Twitter + Reddit, Z. 586–633). Console liegt in Card 4 (collapsible Tool-Panel, Z. 637–692).
- Die `v4/sim-feed`-Komponenten (`FeedColumn.vue`, `TwitterPost.vue`, `RedditPost.vue`, `RedditThread.vue`, `SimulationPulseBar.vue`, `PersonaAvatar.vue`, `SimBadge.vue`) **existieren bereits** und werden in `views/v4/steps/StepSimulationFeedView.vue` zu einem Dual-Column-Feed verdrahtet. Wir konsolidieren: dieselben Komponenten + `useSimFeed` werden in Card 3 von `Step3Simulation.vue` eingehängt.
- `Step3Simulation.vue:205` nutzt schon `useEventStream` mit `state`/`control`-Handlern; ein `post_created`-Handler ist im selben API-Shape ergänzbar (`api/stream.ts` macht das Zod-Parsing schon).
- `SimulationRunView.vue` resettet `graphData` **nicht** beim Status-Wechsel. Der Draft-Befund „Watcher resettet graphData" ist falsch. Es gibt keinen Code-Pfad, der den Graph leert. Falls in der UI „Graph verschwindet" beobachtet wird, ist die Ursache wahrscheinlich woanders (Container-Layout, `WorkspaceSplit`-Mode-Wechsel) — daher: erst reproduzieren, dann fixen; harmlose Defensiv-Änderung + Close-Button.
- `frontend/src/api/logs.ts` (nicht `.js`).
- `Dockerfile`-Prod-Base ist `python:3.14-slim` (nicht `3.12-slim`); `tzdata` ist in Debian-`slim`-Images **nicht** enthalten.
- `backend/tests/scripts/test_sim_common_completion_params.py` testet den Token-Key-Mapper, **nicht** den Default-Wert 8192 → keine Test-Anpassung dort nötig.

## Diagram

```
Task 4 (TZ)  ──┐
Task 3 (tokens)─┤
Task 6 (HTML)  ─┤            isolated, no cross-task deps
Task 7 (logs)  ─┤
Task 5 (graph) ─┘
                 ↓
            Task 2 (Dual-Column Layout)
                 │  ┌──────────────────────────────┐
                 ├──┤ Step3Simulation.vue Card 3:  │
                 │  │   FeedColumn(reddit)│Twitter│
                 │  │   ↑      ↑                   │
                 │  │  RedditThread  TwitterPost   │
                 │  │   (already exist)            │
                 │  └──────────────────────────────┘
                 │  Wire-up: useSimFeed(simId) +
                 │  useEventStream(..., { post_created: feed.ingest })
                 ↓
            Task 1 (Sim-Zeit · Layer-0)
                 │  Backend                 Frontend
                 │  ───────                 ────────
                 │  post_event_contract.py  postEventContract.ts
                 │   + sim_time field        + sim_time field
                 │  run_parallel_simulation  useSimClock.ts
                 │   compute sim_time per   Step3Simulation header
                 │   CREATE_POST emit
                 │  schemas/post-created-event.schema.json (re-dump)
```

---

## Task 1 — Virtuelle Sim-Zeit (Layer-0)

**Files:**
- `backend/app/contracts/post_event_contract.py:44` (PostCreatedEvent)
- `backend/scripts/run_parallel_simulation.py:217-283` (`_emit_post_created_to_redis`) und Aufrufer L1604-1624 / L1872-1892
- `backend/app/contracts/dump_schemas.py:79` (Mapping ist da; Schema neu dumpen)
- `frontend/src/contracts/postEventContract.ts` (Zod-Spiegel)
- Neu: `frontend/src/composables/useSimClock.ts`
- `frontend/src/components/Step3Simulation.vue` (Header-Anzeige)
- Neu: `backend/tests/contracts/test_post_event_contract_sim_time.py`
- Neu: `frontend/src/composables/__tests__/useSimClock.spec.ts`

**Backend:**

`PostCreatedEvent` bekommt:
```python
sim_time: datetime | None = Field(
    default=None,
    description="Simulierte Agenten-Wallclock (Sim-Round → Wallclock, tz-aware). None bei Pre-Slice-5-Daten.",
)
```
Optional, kein Default-Wert → kompatibel mit alten Persistenz-Snapshots. `model_config = ConfigDict(extra="forbid", frozen=True)` bleibt.

In `run_parallel_simulation.py` existiert bereits eine Sim-Clock-Logik (`simulated_minutes = round_num * minutes_per_round`, `simulated_hour = (start_hour_offset + simulated_minutes // 60) % 24`, `simulated_day = simulated_minutes // (60*24) + 1`, siehe L1549-1551 / L1817-1819). Diese Werte bleiben Quelle der Wahrheit; wir leiten daraus den ISO-Timestamp ab.

Anker-Datum: `start_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)` einmal am Sim-Start, dann pro CREATE_POST:
```python
sim_dt = start_time + timedelta(minutes=start_hour_offset * 60 + simulated_minutes)
payload["sim_time"] = sim_dt.isoformat()
```
`start_time` + `start_hour_offset` + `simulated_minutes` werden über `_emit_post_created_to_redis(..., sim_time_iso=…)` reingereicht (neuer kwarg, default None → no-op falls Caller alt). Beide Aufrufstellen (Twitter L1619-1624, Reddit L1887-1892) anpassen.

Schema-Dump:
```bash
cd backend && uv run python -m app.contracts.dump_schemas
git add schemas/post-created-event.schema.json
```
Drift-Gate (MAI-04) prüft byte-genau — ohne re-dump scheitert CI.

**Frontend Zod-Spiegel** (`postEventContract.ts:31` nach `timestamp`):
```ts
sim_time: z.string().datetime({ offset: true }).nullable().optional(),
```

**Composable `useSimClock.ts`** (singleton-pro-simulationId wie `useSimFeed`):
- Exportiert `currentSimTime: Ref<Date | null>`, `start: Ref<Date | null>`, `elapsed: ComputedRef<number>` (Sekunden seit `start`).
- Methode `ingest(post: PostCreatedEvent)`: setzt `start` beim ersten `sim_time != null`, aktualisiert `currentSimTime`, falls neuer Wert > letzter.
- `setInterval(1_000)`-Forecast: extrapoliert zwischen Events linear via `lastWallReceivedAt` (bewusst nicht abhängig von der Sim-Rate, ein ruhiger Tick pro Sekunde reicht für die UI).
- Stop-Funktion gibt Interval frei.

**UI-Anzeige in `Step3Simulation.vue`:**
- Composable im `<script setup>` initialisieren und im `useEventStream`-Handler `post_created` (Task 2) füttern.
- Im Status-Bereich (vor `.stats-grid`, ca. Z. 540, also direkt unter Card 3 Header oder als kleiner Chip in Card 2) anzeigen:
  ```html
  <div v-if="currentSimTime" class="sim-clock" :title="$t('step3.simClock.tooltip')">
    <span class="meta">SIM</span>
    <time :datetime="currentSimTime.toISOString()">
      {{ formatBerlin(currentSimTime) }}
    </time>
    <span class="meta">({{ formatElapsed(elapsed) }})</span>
  </div>
  ```
  `formatBerlin`: `Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'medium', timeZone: 'Europe/Berlin' })`.

**Tests:**
- `backend/tests/contracts/test_post_event_contract_sim_time.py` — `sim_time` optional, tz-aware-Validierung, JSON-Schema-Snapshot enthält neues Feld.
- `frontend/src/composables/__tests__/useSimClock.spec.ts` (Vitest + `vi.useFakeTimers`) — Tick monoton, ignoriert kleinere Werte, Forecast tickt 1× pro Sekunde, Reset bei `null`.

**Hartanker-Check:** `PostCreatedEvent` ist **kein** Hartanker (ADR-0002 schützt nur `EvidenceSourceKind`/`cross_stakeholder_for_high`/`reject_inferred_in_high_confidence`/`<evidence_gating>`-Block/Hedge-Snapshot). Kein Supersedes-ADR nötig.

---

## Task 2 — Dual-Column Sim-Feed in Step3Simulation Card 3 (Twitter | Reddit oben, Console unten)

**Files:**
- `frontend/src/components/Step3Simulation.vue` (Card 3-Markup Z. 586-633; Console-Card Z. 637-692; ggf. CSS-Anpassungen)
- `frontend/src/components/v4/sim-feed/{FeedColumn,TwitterPost,RedditPost,RedditThread}.vue` (existieren — nicht ändern, nur einbinden)
- `frontend/src/composables/useSimFeed.ts` (existiert — Singleton-Store mit `ingest/clear/redditTree/twitterPosts/redditPosts/activityRate`; nicht ändern)

**Layout-Umbau in `Step3Simulation.vue`:**

Card 3 (`.logs-grid` → `.feed-grid`): jetzt **zwei** FeedColumns nebeneinander. Console bleibt in Card 4 (collapsible Tool-Panel), unverändert in der DOM-Position — sitzt durch die Card-Reihenfolge automatisch unter dem Feed.

```vue
<article v-if="phase >= 1" class="card feed-card" role="region" :aria-label="t('step3.feed.title')">
  <header class="card-head">
    <Kicker num="03">{{ t('step3.feed.title') }}</Kicker>
    <!-- Density-Toggle + Tool-Panel-Button bleiben hier -->
  </header>
  <div class="feed-grid">
    <FeedColumn :title="t('feed.twitter')" channel="twitter">
      <TransitionGroup name="slide-in" tag="div" class="post-list">
        <TwitterPost
          v-for="post in feed.twitterPosts.value"
          :key="post.post_id"
          :post="post"
        />
      </TransitionGroup>
      <p v-if="!feed.twitterPosts.value.length" class="meta">{{ t('feed.empty') }}</p>
    </FeedColumn>
    <FeedColumn :title="t('feed.reddit')" channel="reddit">
      <TransitionGroup name="slide-in" tag="div" class="post-list">
        <RedditThread
          v-for="node in feed.redditTree.value"
          :key="node.post_id"
          :node="node"
        />
      </TransitionGroup>
      <p v-if="!feed.redditPosts.value.length" class="meta">{{ t('feed.empty') }}</p>
    </FeedColumn>
  </div>
</article>
```

CSS:
```css
.feed-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-3); min-height: 0; }
@media (max-width: 880px) { .feed-grid { grid-template-columns: 1fr; } }
```

`.logs-grid`-Klasse + alte Live-Feed-Pane-Markup (Z. 586-633 inkl. `density-toggle` und Sticky-Scroll-Hooks für den gemixten Feed) wird **entfernt**, weil `FeedColumn.vue` schon eigene Sticky/Pause-Logik mit `IntersectionObserver` mitbringt. Density-Toggle bleibt erhalten, wird aber zur `feed-grid` als Kontroll-Element refactored (Klassen `density-comfort` / `density-compact` auf `.feed-grid`, in `TwitterPost`/`RedditPost` via `:host-context` o.ä. nicht möglich → einfach am Container per `data-density` und CSS-Vars).

**SSE-Verdrahtung:** `useEventStream` (Z. 205) bekommt einen `post_created`-Handler. Der `feed`-Store wird im `<script setup>` initialisiert:
```js
import { useSimFeed, clearSimFeed } from '../composables/useSimFeed'
import { useSimClock } from '../composables/useSimClock'  // Task 1
import FeedColumn from './v4/sim-feed/FeedColumn.vue'
import TwitterPost from './v4/sim-feed/TwitterPost.vue'
import RedditThread from './v4/sim-feed/RedditThread.vue'

const feed = useSimFeed(props.simulationId)
const simClock = useSimClock(props.simulationId)

const statusStream = useEventStream(() => props.simulationId, {
  state: (msg) => applyRunStateEvent(msg?.payload),
  control: (msg) => applyControlEvent(msg?.payload),
  post_created: (data) => { feed.ingest(data); simClock.ingest(data) },
})
```
Cleanup in `onUnmounted` (existiert noch nicht im File; ein lokaler `watch(() => props.simulationId, …)`-Reset + `onBeforeUnmount(() => clearSimFeed(props.simulationId))` ergänzen).

**`allActions`-Kompatibilität:** das HTTP-Polling in `pollDetail()` (L370-414) füttert weiter `allActions` (Stats `twitterActions`/`redditActions` in der Stats-Grid, Z. 435-436). Wir lassen es unverändert — Stats nutzen weiter `allActions`, der visuelle Feed wechselt auf `useSimFeed`.

**Tests:** Die existierenden Specs unter `frontend/src/components/v4/sim-feed/__tests__/` (`FeedColumn.spec.ts`, `TwitterPost.spec.ts`, `RedditPost.spec.ts`, `RedditThread.spec.ts`, `SimulationPulseBar.spec.ts`, `PersonaAvatar.spec.ts`, `SimBadge.spec.ts`) müssen weiter durchlaufen. Neuer Smoke-Test in `frontend/src/components/__tests__/Step3Simulation.feedColumns.spec.ts` — mountet Step3Simulation mit gestubbtem EventStream, simuliert 2 post_created (1 reddit, 1 twitter) per `feed.ingest`, prüft Existenz beider FeedColumns + jeweils 1 Post.

---

## Task 3 — `completion_max_tokens` Default auf 16384

**Files:**
- `backend/scripts/run_reddit_simulation.py:486` (Default `"8192"` → `"16384"`)
- `backend/scripts/run_twitter_simulation.py:473` (analog)
- `docker-compose.yml:69-100` (agora-Service `environment:`-Block): `LLM_MAX_OUTPUT_TOKENS=${LLM_MAX_OUTPUT_TOKENS:-16384}` ergänzen, sodass der ENV-Override in `.env` durchläuft.
- `docker-compose.prod.yml:53-72`: dito.
- `.env.example`: auskommentierten Block ergänzen mit Erklärung + Hinweis auf CAMEL-Issue (verhindert silent OOM bei Multi-Agent + großem `num_ctx`).

**Keine Test-Änderung** in `backend/tests/scripts/test_sim_common_completion_params.py` — die Datei testet den Token-Key-Mapper (max_tokens vs max_completion_tokens), nicht den Default-Wert. Falls eine Default-Regression abgesichert werden soll, neuer Mini-Test in einer neuen Datei `backend/tests/scripts/test_run_simulation_default_tokens.py` der die Konstante via `re.search` aus den Sim-Scripts liest (kein Subprocess-Spawn).

---

## Task 4 — Container-TZ Europe/Berlin

**Files:**
- `Dockerfile` (Stage `prod`, Z. 116-141): vor `USER agora`:
  ```dockerfile
  RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
      && rm -rf /var/lib/apt/lists/* \
      && ln -snf /usr/share/zoneinfo/Europe/Berlin /etc/localtime \
      && echo "Europe/Berlin" > /etc/timezone
  ENV TZ=Europe/Berlin
  ```
  (Stage `dev` mit `python:3.14` enthält `tzdata` bereits; trotzdem `ENV TZ=Europe/Berlin` einmalig in Stage `base` Z. 15 ergänzen, damit Dev + Prod identisches Verhalten haben.)
- `docker-compose.yml`: im `agora.environment:` (Z. 69) `- TZ=Europe/Berlin` ergänzen.
- `docker-compose.prod.yml`: im `agora.environment:` (Z. 53) dito.

**Verification:** `docker compose up -d && docker compose exec agora date` → muss CEST (Sommerzeit, Mai = `+0200`) zeigen.

**Hinweis:** Task 1 macht `sim_time` tz-aware via `datetime.now(timezone.utc)`-Anker + ISO mit Offset → unabhängig von der Container-TZ. Container-TZ wirkt aber auf alle anderen `datetime.now()`-Naiv-Calls (es gibt viele, siehe `grep` in `backend/app/services/*.py`), inkl. den Log-Filename in `backend/app/utils/logger.py:233` → indirekt löst Task 4 auch eventuelle Date-Roll-Probleme im LogDrawer (Task 7).

---

## Task 5 — Graph nach Sim-Ende erhalten + Close-Button

**Files:**
- `frontend/src/views/SimulationRunView.vue:155-172`
- `frontend/src/components/GraphPanel.vue` (Close-Button, Emit `@close`)
- `frontend/src/components/graph/GraphToolbar.vue` (neuer Button neben `.png`/`.pdf`/Maximize)

**Befund:** Code resettet `graphData` nicht. Aktuelle Logik:
- `loadGraph(graphId)` (L155): `graphLoading.value = true` nur wenn `!isSimulating` — das ist defensiv für die finale Refresh-Runde, blockiert die Anzeige nicht.
- `watch(isSimulating, ...)` (L169): startet/stoppt nur das 30-s-Polling, leert nichts.
- `GraphCanvas.vue:4`: `<div v-if="graphData">` rendert solange `graphData` truthy ist.

→ Wenn der User „Graph verschwindet" beobachtet, ist die Ursache wahrscheinlich anderswo (z. B. `viewMode === 'workbench'` wird beim Sim-Ende getoggelt — aktuell aber nicht im Code zu finden). **Fix-Approach:**
1. Defensiv absichern, dass beim Übergang `processing → completed/failed/stopped` `graphData` nie zurückgesetzt wird, indem `loadGraph` bei `!res.success` **explizit** nichts macht (aktuell schon der Fall; dokumentieren via Code-Kommentar).
2. Close-Button in `GraphToolbar.vue` ergänzen — Emit `@close-graph`, `GraphPanel.vue` reicht durch nach oben.
3. `SimulationRunView.vue`: lokales `graphClosed = ref(false)`; binde an `WorkspaceSplit` so, dass bei `graphClosed === true` der Left-Panel-Style `HIDDEN` ist (analog `useWorkspaceMode`-Pattern). Click → `graphClosed = true`. Reset auf `false` bei explizitem „Wieder einblenden"-Button im Step3Simulation-Header.

**Tests:**
- `frontend/src/views/__tests__/SimulationRunView.spec.ts` (existiert): neue Cases — Graph bleibt nach `status==='completed'`, verschwindet erst nach `@close-graph`-Emit.

---

## Task 6 — Graph als standalone HTML herunterladen

**Files:**
- `frontend/src/components/graph/GraphCanvas.vue:175-269` (neue Methode `downloadHtml()`)
- `frontend/src/components/graph/GraphToolbar.vue` (neuer `.html`-Button + Emit)
- `frontend/src/components/GraphPanel.vue:3-15` (`@download-html="canvasRef?.downloadHtml()"`)

**Implementation:** `printPdf()` (L237-269) baut **bereits** ein standalone HTML mit eingebettetem SVG für den Print-Dialog. Wir refactoren: Helper `_buildStandaloneHtml(): string` extrahieren, `printPdf()` nutzt ihn weiter und ruft `window.print()`, `downloadHtml()` nutzt ihn und triggert Blob-Download via `_triggerBlobDownload` (existiert L115).

```js
function _buildStandaloneHtml() {
  const out = _buildStandaloneSvg()
  if (!out) return null
  const gid = props.graphData?.graph_id || 'graph'
  const html = `<!doctype html>...
${out.body}
</body></html>`
  return { html, gid }
}

function downloadHtml() {
  const built = _buildStandaloneHtml()
  if (!built) return
  _triggerBlobDownload(
    new Blob([built.html], { type: 'text/html;charset=utf-8' }),
    `agora-graph-${built.gid}.html`,
  )
}
```
`defineExpose` (L271-278) bekommt `downloadHtml` dazu.

`GraphToolbar.vue`: Button-Reihe nach `.pdf`:
```vue
<button v-if="hasGraphData" class="tool-btn" title="Export as standalone HTML" @click="$emit('download-html')">
  <span class="btn-text">.html</span>
</button>
```
`defineEmits` um `'download-html'` ergänzen.

**Tests:** Vitest-Spec `frontend/src/components/graph/__tests__/GraphCanvas.downloadHtml.spec.ts` — mockt `URL.createObjectURL` + `document.createElement('a')`, verifiziert MIME `text/html`, Body enthält `<svg`, `<!doctype html>`, Filename matcht `agora-graph-…\.html`.

---

## Task 7 — LogDrawer Placeholder-Bug

**Files:**
- `frontend/src/components/LogDrawer.vue` (L37-49 Body, L101-113 `reload()`, L92-96 `filteredLines`)
- `backend/app/api/logs.py:140-164` (`get_logs`)

**Befund:** `filteredLines` (L92) ist `lines.value` ohne `level`-Filter (Level-Vorfilterung läuft im Backend `_filter_lines`). Wenn `lines` leer ist, zeigt L39 den `logs.drawer.empty`-Placeholder. Plausibelste Ursachen:
1. Backend: `_resolve_log_path()` (L60-74) liefert `None`, wenn die heutige Logdatei (`YYYY-MM-DD.log`) noch nicht existiert. Im Docker-Container, der gerade hochgefahren wurde, kommt der erste Log-Eintrag erst nach dem ersten Request — bis dahin gibt es kein File. Antwort: `{"lines":[],"offset":0,"file":null}` → Drawer leer. Task 4 (TZ) macht zusätzlich die Datumsschwelle stabil.
2. `fetchLogs` schluckt Fehler still (L112 `catch { /* swallow */ }`). Auth-Fehler (`AGORA_AUTH_TOKEN` gesetzt, Token im Request fehlt → 401) sind dadurch unsichtbar.

**Fix (defensive, ohne neue Backend-Endpoints):**
- `LogDrawer.vue` `reload()` (L101-113) Loading/Error-State exposen:
  ```js
  const loading = ref(false)
  const error = ref(null)
  async function reload() {
    loading.value = true
    error.value = null
    try {
      const res = await fetchLogs({ tail: 500, level: level.value || null })
      if (res?.data?.success) {
        const data = res.data.data || {}
        lines.value = data.lines || []
        lastOffset = Number.isInteger(data.offset) ? data.offset : null
        nextTick(() => sticky.scrollToBottom())
      } else {
        error.value = res?.data?.error || t('logs.drawer.unknownError')
      }
    } catch (err) {
      error.value = err?.message || String(err)
    } finally {
      loading.value = false
    }
  }
  ```
- Template (L37-49):
  ```vue
  <div ref="scrollEl" class="drawer-body">
    <div v-if="loading && !lines.length" class="meta">{{ t('logs.drawer.loading') }}</div>
    <div v-else-if="error" class="meta error">{{ error }}</div>
    <div v-else-if="!filteredLines.length" class="meta">{{ t('logs.drawer.empty') }}</div>
    <div v-else v-for="…">…</div>
  </div>
  ```
- `frontend/src/i18n/locales/{de,en}.json`: `logs.drawer.loading` + `logs.drawer.unknownError` ergänzen.

**Backend:** `_resolve_log_path` darf nicht silent `None` zurückgeben, wenn die Datei „noch nicht existiert" — der Frontend-Drawer sieht so nicht, dass das Backend selber lebt. Wir liefern bei `None` einen aussagekräftigen Marker:
```python
return json_success({
    'lines': [],
    'offset': 0,
    'file': None,
    'message': 'log file for today not yet written',
})
```
Frontend: wenn `data.file === null` und `data.message` gesetzt → als `meta`-Hinweis statt `empty`-Placeholder rendern. (Optional — kleiner Cherry-on-Top, nicht harten Fix-Pfad blockierend.)

**Tests:** `frontend/src/components/__tests__/LogDrawer.spec.ts` (existiert) erweitern um Loading-, Error-, Lines- und „file: null"-Cases.

---

## Reihenfolge

Sieben unabhängige Commits in dieser Order (risikoarm → Layer-0):

1. **Task 4** Docker-TZ (Config-only).
2. **Task 3** Token-Default (ENV-Default + Compose-Wiring).
3. **Task 6** Graph HTML-Export (isolierter Frontend-Touch).
4. **Task 5** Graph-Persistenz + Close-Button.
5. **Task 7** LogDrawer Loading/Error/Empty + Backend-Marker.
6. **Task 2** Dual-Column Feed in Step3Simulation (FE-Komponenten existieren, nur Verdrahtung).
7. **Task 1** Sim-Zeit Backend + Frontend + Schema-Dump + Tests (**Opus-Trigger** lt. CLAUDE.md, Layer-0 + Cross-Layer).

---

## Verification (End-to-End)

```bash
# Backend Lint + Tests
cd backend && uv run ruff check app/ tests/ scripts/ && uv run pytest -q

# Frontend Tests + Type-Check
cd frontend && pnpm test && pnpm typecheck

# Schema-Drift (Task 1 — MAI-04 Gate)
cd backend && uv run python -m app.contracts.dump_schemas --check

# Docker Up + TZ-Check (Task 4)
docker compose up -d --build agora
docker compose exec agora date  # erwartet CEST (Mai 2026: +0200)

# Manuelle UI-Tests (`pnpm dev` oder Docker)
# Task 1: SIM-Clock tickt im Step3-Header, Format HH:MM:SS DE-Locale
# Task 2: Card 3 zeigt Twitter | Reddit als 2 FeedColumns, Console drunter (Tool-Panel öffnen)
# Task 5: Sim laufen lassen → stoppen → Graph bleibt → Close-Button blendet aus
# Task 6: GraphToolbar `.html`-Button → standalone .html in Downloads, lokal öffnen = renderter Graph
# Task 7: LogDrawer (Ctrl+Shift+L) zeigt entweder Logs ODER Loading/Error/Empty mit Meta-Hinweis

# Task 3 ENV-Override
LLM_MAX_OUTPUT_TOKENS=32768 docker compose up -d
docker compose logs agora | grep -i "completion_max_tokens"  # erwartet 32768
```

## Hartanker-Check (ADR-0002)

Keiner der fünf Hartanker (`<evidence_gating priority="hard">`-Block in `report_prompts.py`, Hedge-Snapshot `tests/eval/snapshots/evidence-gating-hedge-words.txt`, `EvidenceSourceKind`-Enum, `cross_stakeholder_for_high`-Validator, `reject_inferred_in_high_confidence`-Validator) wird berührt. Kein Supersedes-ADR nötig.