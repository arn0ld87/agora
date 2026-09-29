# Simulations-Feed und Diskursansicht — Design-Spezifikation

> Slice UI-2b (Epic #1713). Verbindliche Spezifikation für den Umbau der
> Schritt-3-Ansicht von der Dual-Column-„Blase" auf einen kanonischen Feed
> mit Diskurs-, Strang-, Runden- und Protokollansichten.
>
> Basis: `SimulationLayout.vue` (#1714), `PostCreatedEvent` v1
> (`backend/app/contracts/post_event_contract.py`).  Backend-Vertrag v2,
> `SimActionRecord`, `SimActionPage`, `RoundSummary` entstehen parallel zu
> dieser Umsetzung — die UI benutzt ausschließlich Vertragsfelder.
>
> Kein Vue-Code in diesem Dokument; nur Signaturen und Deltas.

## 1. Routen und Informationsarchitektur

Elternroute bleibt `SimulationLayout.vue`.  Der Feed-Tab hat fünf
Kind-Routen, plus einen Redirect für Deep-Links auf `/live`:

| Path (unter `/v4/simulation/:simulationId`) | Route-Name              | View-Datei                       |
| ------------------------------------------- | ----------------------- | -------------------------------- |
| ``               (Index, Pipeline)          | `StepSimulation`        | `StepSimulationView.vue`         |
| `feed`                                      | `StepSimulationFeed`    | `StepSimulationFeedView.vue`     |
| `threads`                                   | `SimThreads`            | `SimThreadsView.vue`             |
| `thread/:postId`                            | `SimThreadFocus`        | `SimThreadFocusView.vue`         |
| `rounds`                                    | `SimRounds`             | `SimRoundsView.vue`              |
| `actions`                                   | `SimActions`            | `SimActionsView.vue`             |
| `live` (Bestand)                            | Redirect                | → `SimRounds`, Query mitnehmen   |

Die bisherige Weiche `/live → StepSimulationFeed` in `router/index.ts`
wird angepasst: neues Ziel ist `SimRounds`, Query bleibt erhalten.
`StepSimulation` (Index-Kind) ist die Pipeline-Ansicht und ändert sich
nicht.

`SimulationLayout.vue` erweitert seine `PipelineStepper`-Tabs auf
`Pipeline | Feed | Diskurs | Runden | Protokoll`.  Der bisherige
`activeTab`-Computed schaut jetzt auf einen Namens-Prefix
(`route.name.startsWith('SimThread')` → `threads`).  Der Tab-Wechsel
verwendet weiterhin `router.push` und trägt die aktuelle Query mit.

### Query-Filter (persistieren via URL)

Alle Filter leben in `route.query`, damit ein Reload den Zustand behält
und ein Link teilbar ist:

- `platform` — `reddit | twitter | all` (default `all`)
- `round` — `\d+` (default leer = alle Runden)
- `persona` — `persona_id` (default leer)
- `q` — Freitext (client-seitig, nur Feed/Diskurs)
- `type` — nur `actions`-View: `post | repost | comment | quote | like | follow | ...`
- `since` — ISO-Zeitstempel für „nur ab", nur `feed`/`actions`

### History-Verhalten

- Filter-Änderungen: `router.replace` (kein neuer Back-Eintrag).
- Tab-Wechsel: `router.push` (Back springt zurück in vorherigen Tab).
- Öffnen eines Strang-Fokus aus `feed` oder `threads`:
  `router.push({ name: 'SimThreadFocus', params: { postId } })` — Back
  bringt den Nutzer auf die Herkunftsansicht zurück.
- Browser-Back darf nie in eine leere Simulation zurückführen:
  `SimulationLayout` schreibt weiterhin `projectId` in die Query, bevor
  Kind-Routen ihren Zustand aufbauen (vorhandenes Verhalten, unverändert).

## 2. Komponenten

Jede Komponente wird gegen die Vertragsfelder von `PostCreatedEvent` v2,
`SimActionRecord` und `RoundSummary` signiert.  Vertragstypen kommen aus
`@/contracts/postEventContract` bzw. den beim Bau parallel entstehenden
`@/contracts/simActionContract` und `@/contracts/roundSummaryContract`.
Vertragsfelder werden **nie** durch handgeschriebene Interfaces gespiegelt.

### 2.1  `SimTabsBar` — Tabsleiste unterhalb des `PipelineStepper`

Datei: `frontend/src/components/v4/sim-feed/SimTabsBar.vue` (neu).
Ersetzt die bestehende `Tabs`-Instanz in `SimulationLayout.vue`
(`sim-view-tabs`) für die fünf neuen Tabs.

Props:
- `activeTab: 'pipeline' | 'feed' | 'threads' | 'rounds' | 'actions'`
- `simulationId: string`

Zustand: keiner — reines gestyltes Wrapper-Element über der Bestands-
`Tabs`-Primitive.  A11y: `role="tablist"`, jeder Tab `role="tab"`,
`aria-current="page"` auf dem aktiven; Tastatur: `←/→` wechselt Tab
(`Tabs` liefert das schon), `Home/End` erster/letzter, `Enter/Space`
aktiviert.

### 2.2  `SimFilterBar` — Filter oberhalb Feed/Diskurs/Runden/Protokoll

Datei: `frontend/src/components/v4/sim-feed/SimFilterBar.vue` (neu).
Ersetzt konzeptionell den `SimulationPulseBar`-Kopfbereich; die
Aktivitätsanzeige wandert in einen kompakteren `SimRunHeader` (2.3).

Props:
```ts
interface SimFilterBarProps {
  platform: 'all' | 'reddit' | 'twitter'
  round: number | null
  persona: string | null
  q: string
  personas: Array<{ id: string; name: string }>   // aus Snapshot
  rounds: number[]                                 // 1..max, aus RoundSummary
  scope: 'feed' | 'threads' | 'rounds' | 'actions' // steuert sichtbare Filter
}
```
Events: `update:platform`, `update:round`, `update:persona`, `update:q`.
Persona- und Runden-Select verwenden die bestehenden `SelectPrimitive`
und `Field`-Komponenten aus `components/ui/`.  Freitext ist ein
`input[type=search]` mit `aria-label`.  A11y: alle Selects mit
Label-Elementen, Freitext hat `role="searchbox"`.

Zustände: `loading` (Selects `disabled` + Skeleton-Style), `empty`
(Personas-Liste leer → Feld disabled, Hilfetext „Noch keine Personen im
Feed").

### 2.3  `SimRunHeader` — Kompakter Statusstreifen

Datei: `frontend/src/components/v4/sim-feed/SimRunHeader.vue` (neu).
Ersetzt `SimulationPulseBar.vue` in Feed/Diskurs/Runden/Protokoll und
zeigt: aktuelle Runde `n/N`, letzte Sim-Zeit (`sim_time`), Anzahl
Beiträge total, Live-Punkt (grün = Stream offen, gelb = Reconnect,
grau = beendet), Degradations-Hinweis.

Props:
```ts
interface SimRunHeaderProps {
  simulationId: string
  currentRound: number | null
  totalRounds: number | null
  simTime: string | null                 // ISO
  postCount: number
  streamState: 'connecting' | 'open' | 'reconnecting' | 'closed' | 'ended'
  degradation: null | {
    kind: 'snapshot_missing' | 'stream_lost' | 'legacy_run'
    hint: string    // vom Backend geliefert (i18n-Key), sonst deutscher Fallback
  }
}
```
Zustände: `loading` (Werte durch `—` ersetzt, `aria-busy="true"`),
`degraded` (Streifen behält Struktur, ein Chip zeigt den Text; nicht als
Erfolg färben — `--status-amber` bzw. `--status-red`).

`SimulationPulseBar.vue` bleibt vorerst im Baum, wird aber nirgends mehr
importiert; Löschung im letzten Commit der Serie.

### 2.4  `FeedItem` — Einzelbeitrag im Feed

Datei: `frontend/src/components/v4/sim-feed/FeedItem.vue` (neu).
Ersetzt die bisherige Direktdarstellung `TwitterPost`/`RedditPost` an
den Feed-Wurzeln.  Beide Basiskomponenten bleiben Bausteine, `FeedItem`
ist der Rahmen mit Plattform-Markierung, Trennlinie unten (keine Karte)
und Kind-Slots.

Props:
```ts
interface FeedItemProps {
  post: PostCreatedEvent          // v2
  isNew?: boolean                 // markiert neu eingetroffen (fade-in + Punkt links)
  showContext?: boolean           // im Strang-Fokus: false; im Feed/Diskurs: true
}
```
Rendering-Regeln je `post.kind`:
- `post` → `TwitterPost` (Twitter) bzw. `RedditPost` (Reddit) Body.
- `comment` → wie `post`, aber Zeile darüber:
  „Antwort an @{{ parent_persona_name }}" (Link zum Strang-Fokus über
  `parent_post_id`).  Fällt `parent_persona_name` in Altläufen weg,
  Text „Antwort auf früheren Beitrag" (Degradations-Wortlaut, kein
  stiller Fallback auf „unbekannt").
- `quote` → gerahmter Nested-Block (`quote_body`, `quoted_post_id`
  klickbar).  Ist `quote_body` leer, Text „Zitat nicht mehr auffindbar"
  aus i18n.
- `repost` → einzeiliger Vorsatz „@X hat geteilt", darunter der
  ursprüngliche Body (aus `reposted_post_id`-Referenz, geladen über
  `useSimFeed().byId(reposted_post_id)`).  Ist der Ursprung nicht
  bekannt: „Bezug nicht erfasst".

Zustände: `isNew=true` blendet einen 2px Kupfer-Punkt am linken
Rand ein und markiert den Item-Rahmen für 1500ms mit
`background: var(--sim-item-new-bg)`.  Kein Autoscroll.

Tastatur/A11y: `role="article"`, `tabindex="0"`, `Enter/Space` öffnet
`SimThreadFocus`.  Kontext-Zeile hat `aria-describedby` auf den
sichtbaren Text.

### 2.5  `FeedTimeline` — virtualisierte Liste

Datei: `frontend/src/components/v4/sim-feed/FeedTimeline.vue` (neu).
Ersetzt die Dual-Column-Struktur in `StepSimulationFeedView.vue`
(`.sf-columns`) und retiriert `FeedColumn.vue` als Root-Element (bleibt
als Primitive für Diskurs- und Protokoll-Panels erhalten).

Virtualisierung über `@tanstack/vue-virtual` mit `overscan: 6`,
`estimateSize: 120`.  Kein Autoscroll bei neuen Elementen; stattdessen
`NewItemsPill` (2.6).

Props:
```ts
interface FeedTimelineProps {
  items: PostCreatedEvent[]              // vorgefiltert, chronologisch aufsteigend
  streamState: 'open' | 'reconnecting' | 'closed' | 'ended'
  isSnapshotLoading: boolean
  error: null | { code: string; message: string }
}
```
Events: `openThread(postId: string)`.

Zustände:
- `loading` (Snapshot pendent) → drei Skeleton-Zeilen, `aria-busy`.
- `empty` → deutsche Zeile „Noch keine Beiträge in diesem Lauf" +
  Kurzhinweis auf `SimRounds`.
- `error` → Fehlerbanner (nicht die Liste selbst leeren), Retry-Button
  ruft `getSimulationFeedSnapshot` erneut.
- `degraded` (Stream lost) → Banner oben in der Liste mit
  „Verbindung verloren — versuche Reconnect (n)".

### 2.6  `NewItemsPill` — „N neue Beiträge" in Feed und Diskurs

Datei: `frontend/src/components/v4/sim-feed/NewItemsPill.vue` (neu).
Ersetzt die stille Slide-in-Animation aus `StepSimulationFeedView.vue`
und übernimmt das Prinzip des bestehenden `fc-pause-chip` in
`FeedColumn.vue` (das Chip wandert in diese Komponente).

Props: `count: number`, `visible: boolean`.  Event: `click` → Timeline
scrollt an die neuen Elemente heran (`scrollBy` bis das erste neue
Element im Viewport ist) und der Zähler fällt auf 0.

Anzeige: fixiert oberhalb der Liste (nicht overlay über die Kopfzeile),
`--r-pill`, Text `„{{ count }} neue Beiträge"`.  Auto-Verstecken nach
20 s wenn der Nutzer die Timeline nicht bewegt.

### 2.7  `SimThreadList` — Diskurs-Übersicht

Datei: `frontend/src/components/v4/sim-feed/SimThreadList.vue` (neu).
Ersetzt in `SimThreadsView.vue` die (heute nicht existierende) Ansicht.

Liste aller Strang-Wurzeln (`kind='post'`, kein `parent_post_id`),
sortiert nach zuletzt aktivem Reply, mit:
- Wurzel-Persona + Kurztext (2 Zeilen mit `text-wrap: pretty`)
- Anzahl Replies, Anzahl Reposts, Anzahl Quotes
- Runden-Chip (kleinste und größte `round_num`, in der der Strang aktiv war)
- Plattform-Marker („R" / „T", neutrales `--gray-3`, kein Markenlogo)

Props:
```ts
interface SimThreadListProps {
  threads: Array<{
    root: PostCreatedEvent
    replyCount: number
    repostCount: number
    quoteCount: number
    lastActivityAt: string          // ISO
    activeRounds: number[]
  }>
  loading: boolean
  emptyReason: 'no_data' | 'filter' | null
}
```
Event: `open(postId: string)` → `SimThreadFocus`.

### 2.8  `SimThreadTree` — Strang-Fokus (baumartig)

Datei: `frontend/src/components/v4/sim-feed/SimThreadTree.vue` (neu).
Baut die bestehende `RedditThread.vue`-Rekursion aus und wird für beide
Plattformen genutzt.  Twitter-Antworten (`kind='comment'`, nur
`parent_post_id`) ergeben eine flache Reply-Liste unter der Wurzel;
Reddit-Antworten mit `parent_comment_id` ergeben einen Baum.

Die Kanten werden aus `parent_comment_id ?? parent_post_id` gebaut —
das ist die einzige Kante-Regel, sie funktioniert mit und ohne
Slice-5-Backfill.

Props:
```ts
interface SimThreadTreeProps {
  root: PostCreatedEvent
  nodes: PostCreatedEvent[]        // alle Beiträge des Strangs
  maxDepth?: number                // default 6
  loading: boolean
}
```
Zustände: `loading` (nur Wurzel + Skeleton), `orphan` (`root` hat
`parent_post_id`, das der Snapshot nicht kennt: sichtbarer Chip
„Übergeordneter Beitrag nicht erfasst").

### 2.9  `SimRoundsList` — Runden-Ansicht

Datei: `frontend/src/components/v4/sim-feed/SimRoundsList.vue` (neu).
Ersetzt in `SimRoundsView.vue` die Aktivitätsleiste aus `SimulationPulseBar.vue`.

Datenquelle: `GET /api/simulation/<id>/rounds` (`RoundSummary[]`).
Zeigt pro Runde: `round_num`, Zeitfenster (`start`/`end` als
`sim_time`), Aktionsbilanz (Posts, Comments, Reposts, Quotes, Likes),
Domänen-/Persona-Highlights (Feldnamen kommen aus dem Vertrag).

Props:
```ts
interface SimRoundsListProps {
  rounds: RoundSummary[]
  activeRound: number | null
  streamState: SimRunHeaderProps['streamState']
}
```
Event: `select(round: number)` → schreibt `?round=` in Query, tab wechselt
NICHT — es filtert alle vier Ansichten.

Zustände: `loading` (5 Skeleton-Zeilen), `empty` („Noch keine Runden
gestartet"), `error` (Banner mit Retry).

### 2.10  `SimActionsTable` — Protokoll

Datei: `frontend/src/components/v4/sim-feed/SimActionsTable.vue` (neu).
Datenquelle: `GET /api/simulation/<id>/actions?...` (`SimActionPage`).

Tabellenkopf: `round_num`, `sim_time`, `persona_name`, `platform`,
`action_type`, `target_post_id`, `payload_preview`.
Serverseitige Pagination via `cursor`; Filter aus `SimFilterBar`.

Props:
```ts
interface SimActionsTableProps {
  page: SimActionPage
  loading: boolean
  filters: { round?: number; personaId?: string; platform?: Platform; actionType?: string }
}
```
Events: `loadMore()`, `openPost(postId: string)`.
Tastatur: Zeilen `tabindex="0"`, `Enter` öffnet `SimThreadFocus` wenn
`target_post_id` gesetzt.

## 3. Token-Ergänzungen (`tokens-v3.css`)

Der Feed setzt heute Pixelwerte direkt in den `sim-feed/*.vue`-Dateien
(Zeilenmaße `padding: 10px 12px`, `font-size: 13px`, `gap: 6px`,
`box-shadow: 0 2px 8px rgba(0,0,0,0.1)`, Farb-Literale `#…`).  Sie
werden gegen die folgenden neuen Tokens ersetzt:

| Token                        | Wert                               | Ersetzt (Datei)                                        |
| ---------------------------- | ---------------------------------- | ------------------------------------------------------ |
| `--sim-item-py`              | `12px`                             | `TwitterPost.vue .tw-root padding`, `RedditPost.vue`   |
| `--sim-item-px`              | `16px`                             | dito                                                   |
| `--sim-item-gap`             | `12px`                             | `.tw-root gap`, `.rp-root gap`                         |
| `--sim-item-divider`         | `1px solid var(--hairline)`        | `.tw-root border-bottom`, `FeedColumn.vue .fc-header`  |
| `--sim-item-new-bg`          | `color-mix(in oklab, var(--accent) 12%, transparent)` | Fade-Hinterlegung neuer Beiträge      |
| `--sim-thread-indent`        | `20px`                             | `RedditThread.vue paddingLeft: depth*16` (auf 20 setzen) |
| `--sim-thread-rule`          | `1px solid var(--border-subtle)`   | vertikale Linie im Strang, heute inline in `RedditPost`|
| `--sim-header-py`            | `10px`                             | `SimulationPulseBar .spb-root padding`, `FeedColumn .fc-header` |
| `--sim-header-px`            | `16px`                             | dito                                                   |
| `--sim-badge-fg-reddit`      | `var(--text-primary)`              | Buchstaben-Chip „R" (kein Reddit-Orange)               |
| `--sim-badge-fg-twitter`     | `var(--text-primary)`              | Buchstaben-Chip „T" (kein Twitter-Blau)                |
| `--sim-badge-bg`             | `var(--gray-3)`                    | neutraler Hintergrund für Plattform-Chip               |
| `--sim-pill-shadow`          | `var(--shadow-2)`                  | `FeedColumn .fc-pause-chip box-shadow` (Hard-Wert weg) |
| `--sim-new-dot`              | `var(--accent-warm)`               | Marker links neben neuem Item                          |
| `--sim-live-dot-open`        | `var(--status-green)`              | Bestand, nur benennen                                   |
| `--sim-live-dot-reconnect`   | `var(--status-amber)`              | neu                                                    |
| `--sim-live-dot-closed`      | `var(--text-tertiary)`             | neu                                                    |
| `--sim-time-fs`              | `var(--fs-small)`                  | `.tw-time font-size: 11px` — an Skala anschließen      |
| `--sim-persona-fs`           | `var(--fs-body)`                   | `.tw-handle font-size: 13px`                           |

Radien werden **nicht** ergänzt: Beiträge sind trennlinien-getrennt,
keine Karten.  Der einzige Pill bleibt `NewItemsPill` (nutzt `--r-pill`).

## 4. Live-Verhalten und Skalierung

**Kein Scroll-Sprung.**  `FeedTimeline` beobachtet die Scroll-Position:
solange der Nutzer den unteren Sichtbereich (`bottom - 120px`)
verlassen hat, bleibt die Liste stehen.  Neue Elemente werden hinten
angehängt, `NewItemsPill` erscheint mit dem Zähler.  Erst ein Klick auf
den Pill scrollt heran.  Am unteren Rand (Sichtbereich am Anker):
Anhängen ohne Scroll-Sprung (die neue Zeile schiebt sich in den
Viewport, wie Twitter-Web es tut).

**Markierung neuer Beiträge.**  Ein Beitrag gilt `isNew`, wenn er
über den Stream kam (nicht aus dem initialen Snapshot).  Marker läuft
1500 ms, dann fällt er ab.  Ein am unteren Rand angehängter Beitrag
zeigt den Marker ebenfalls, damit auch „auto-sichtbare" Zugänge lesbar
werden.

**Virtualisierung.**  `@tanstack/vue-virtual` mit `estimateSize=120`
(entspricht durchschnittlicher Beitragshöhe im aktuellen Layout,
`overscan=6`).  `SimThreadTree` virtualisiert nicht — Stränge sind
typischerweise <50 Knoten und Sprungziele über `postId` müssen sofort
DOM-präsent sein.

**Serverseitige Pagination.**  `SimActionsTable` lädt via Cursor.
`SimRoundsList` lädt in einem Rutsch (Rundenzahl ist beschränkt).
`FeedTimeline`: initialer Snapshot ist die einzige Server-Ladung; der
Stream liefert danach inkrementell.  Fällt der Stream aus, holt
`SimRunHeader` alle 15 s per `GET /api/simulation/<id>/feed?since=<last>`
den Delta-Snapshot.

**Degradation sichtbar.**  Alle drei Zustände (`snapshot_missing`,
`stream_lost`, `legacy_run`) werden im `SimRunHeader.degradation` als
Chip geführt.  Zusätzlich blendet die betroffene View ein
Kontextbanner ein (z.B. „Bezug nicht erfasst" in `FeedItem` für
Kanten, die die Wurzel nicht kennen).  Keine dieser Zustände wird
farblich als Erfolg dargestellt.

## 5. Umsetzungsreihenfolge (fünf Commits)

Alle fünf Commits gehören in einen PR gegen `main`.  Vertragsänderungen
kommen im ersten Commit; alles Weitere baut darauf auf.

### Commit 1 — Verträge und Zod-Spiegel

Files: `backend/app/contracts/post_event_contract.py`,
`backend/app/contracts/sim_action_contract.py` (neu),
`backend/app/contracts/round_summary_contract.py` (neu),
`backend/app/contracts/__init__.py`, `backend/tests/contracts/*`,
`backend/app/contracts/dump_schemas.py`, `frontend/schemas/*.schema.json`
(generiert), `frontend/src/contracts/postEventContract.ts`,
`frontend/src/contracts/simActionContract.ts` (neu),
`frontend/src/contracts/roundSummaryContract.ts` (neu).

Akzeptanz:
- `PostCreatedEvent` besitzt `kind: Literal['post','repost','comment','quote']`,
  `round_num: int >= 0`, `parent_comment_id: str | None`,
  `root_post_id: str | None`, `quoted_post_id: str | None`,
  `reposted_post_id: str | None`, `quote_body: str | None`,
  `parent_persona_id: str | None`, `parent_persona_name: str | None`,
  `like_count: int >= 0`.  `sim_time` und `parent_post_id` bleiben.
- `SimActionRecord` (Cursor-Filter `round_num`, `agent_id`, `platform`,
  `action_type`) und `SimActionPage` (Cursor, Items) existieren.
- `RoundSummary` mit `round_num`, `sim_time_start`, `sim_time_end`,
  Aktionszählern.
- `uv run python -m app.contracts.dump_schemas` läuft grün,
  `frontend/schemas/` ist aktualisiert, der Zod-Spiegel deckt jedes
  Vertragsfeld ab.
- Regressionstest in `backend/tests/contracts/test_post_event_contract.py`
  für `kind`/Kante-Kombinationen (`comment` ohne `parent_post_id`
  → Validation-Error).

### Commit 2 — Routen und Layout-Tabs

Files: `frontend/src/router/index.ts`,
`frontend/src/views/v4/steps/SimulationLayout.vue`,
`frontend/src/views/v4/steps/SimThreadsView.vue` (Platzhalter, leer),
`frontend/src/views/v4/steps/SimThreadFocusView.vue` (Platzhalter),
`frontend/src/views/v4/steps/SimRoundsView.vue` (Platzhalter),
`frontend/src/views/v4/steps/SimActionsView.vue` (Platzhalter),
`frontend/src/components/v4/sim-feed/SimTabsBar.vue` (neu),
`frontend/src/i18n/de.json`, `frontend/src/i18n/en.json`.

Akzeptanz:
- Fünf Kind-Routen unter `SimulationLayout` sind erreichbar; leere
  Views zeigen konsistente Empty-States.
- `/v4/simulation/:id/live` redirected auf `SimRounds`.
- Tabsleiste mit Tastatur bedienbar (Playwright oder Vitest+
  `@vue/test-utils` Regressionstest).
- Query-Persistenz beim Tab-Wechsel erhalten (Regressionstest).

### Commit 3 — Feed als kanonische Timeline

Files: `frontend/src/views/v4/steps/StepSimulationFeedView.vue`,
`frontend/src/components/v4/sim-feed/FeedTimeline.vue` (neu),
`frontend/src/components/v4/sim-feed/FeedItem.vue` (neu),
`frontend/src/components/v4/sim-feed/NewItemsPill.vue` (neu),
`frontend/src/components/v4/sim-feed/SimRunHeader.vue` (neu),
`frontend/src/components/v4/sim-feed/SimFilterBar.vue` (neu),
`frontend/src/composables/useSimFeed.ts` (`kind`-aware Kante-Auflösung,
`byId`, `flatTimeline`).

Akzeptanz:
- Dual-Column entfällt; Beiträge erscheinen chronologisch mit
  Plattform-Chip.
- Virtualisierung greift ab 50 Items (Test misst DOM-Knoten).
- `isNew`-Markierung und `NewItemsPill` funktionieren; kein Autoscroll.
- Alle Zustände (`loading`, `empty`, `error`, `degraded`) haben eigene
  Snapshots (Vitest + Testing-Library).

### Commit 4 — Diskurs, Strang-Fokus, Runden

Files: `frontend/src/views/v4/steps/SimThreadsView.vue`,
`frontend/src/views/v4/steps/SimThreadFocusView.vue`,
`frontend/src/views/v4/steps/SimRoundsView.vue`,
`frontend/src/components/v4/sim-feed/SimThreadList.vue` (neu),
`frontend/src/components/v4/sim-feed/SimThreadTree.vue` (neu),
`frontend/src/components/v4/sim-feed/SimRoundsList.vue` (neu),
`frontend/src/api/simulation.ts` (neuer Endpoint `getRounds`).

Akzeptanz:
- Diskurs-Liste sortiert nach `lastActivityAt`; Klick öffnet Strang-Fokus.
- Strang-Fokus baut Baum aus `parent_comment_id ?? parent_post_id`
  (Regressionstest mit gemischtem Snapshot).
- Runden-Auswahl schreibt `?round=` in Query und beeinflusst
  Feed/Diskurs/Protokoll.
- Legacy-Snapshot ohne `parent_comment_id` rendert weiterhin einen
  Reddit-Baum via `parent_post_id`.

### Commit 5 — Protokoll (Actions) und Aufräumen

Files: `frontend/src/views/v4/steps/SimActionsView.vue`,
`frontend/src/components/v4/sim-feed/SimActionsTable.vue` (neu),
`frontend/src/api/simulation.ts` (Cursor-basierter `listActions`),
`frontend/src/components/v4/sim-feed/SimulationPulseBar.vue` (Löschung),
`frontend/src/components/v4/sim-feed/index.ts` (Exporte aktualisieren),
`docs/STATUS.md`, `changelog.d/1713-simulation-feed.md`.

Akzeptanz:
- Protokoll-Tabelle lädt seitenweise via Cursor, Filter aus `SimFilterBar`.
- Deep-Link `?type=repost&round=3` filtert korrekt.
- `SimulationPulseBar.vue` und `.fc-pause-chip` in `FeedColumn.vue`
  sind entfernt; `FeedColumn.vue` existiert nur noch als leichter
  Wrapper (oder wird ganz entfernt, wenn Diskurs/Fokus sie nicht mehr
  brauchen).
- `docs/STATUS.md` und Changelog synchron; `bash scripts/pre-push-gate.sh`
  grün.

Optional Commit 6 — nur falls Token-Umzug (`tokens-v3.css`) sich nicht
sauber in Commit 3 mitziehen lässt (großer Diff):

- Files: `frontend/src/assets/styles/tokens-v3.css`,
  alle `sim-feed/*.vue` mit Literalen.
- Akzeptanz: `designTokens.spec.ts` grün, kein Pixelwert in
  `components/v4/sim-feed/*.vue`.

## 6. Prüfliste nach Umsetzung (Design-Lead-Abnahme)

1. **Routen**: alle fünf Kind-Routen direkt aufrufbar, `/live`
   redirected auf `rounds`, Browser-Back respektiert Herkunft.
2. **Filter-Persistenz**: Reload behält `platform`, `round`, `persona`,
   `q`, `type`, `since`; Filter-Wechsel benutzt `router.replace`.
3. **Layout**: keine Karten pro Beitrag, nur Trennlinien; keine
   Gradients, kein Glassmorphism, Radius maximal `--r-pill` für
   `NewItemsPill`.
4. **Plattform-Marker**: „R" und „T" auf `--sim-badge-bg`; kein Reddit-
   Orange, kein Twitter-Blau irgendwo im Baum (`git grep` in
   `frontend/src`).
5. **Live-Verhalten**: neue Beiträge lösen kein Scroll-Sprung aus;
   `NewItemsPill` zeigt genauen Zähler; Marker `isNew` erlischt nach
   1500 ms.
6. **Virtualisierung**: `FeedTimeline` hat bei 500 Beiträgen ≤ 40 DOM-
   Rows; `SimThreadTree` bleibt nicht-virtualisiert.
7. **Degradation**: `snapshot_missing`, `stream_lost`, `legacy_run`
   erzeugen sichtbaren Chip im `SimRunHeader` und kein grünes Signal;
   fehlende Kanten rendern „Bezug nicht erfasst".
8. **A11y**: axe-core-Lauf über Feed, Diskurs, Strang-Fokus, Runden,
   Protokoll ohne critical-Findings; `role="feed"` nur bei nicht-leerer
   Liste, sonst `region` (bestehendes Muster aus `FeedColumn.vue`).
9. **Tastatur**: Tab-Reihenfolge Filter → Timeline → Pill;
   `Enter/Space` auf `FeedItem` öffnet Strang-Fokus; `Esc` im
   Strang-Fokus geht zurück (Route-basiert, nicht History-hack).
10. **i18n**: alle sichtbaren Strings in `de.json`/`en.json`, keine
    hartcodierten deutschen Wörter mehr in `sim-feed/*.vue`.
11. **Sprache**: keine Verhaltensvorhersage-Formulierung („X wird
    reagieren"), Wortlaut passt zu `CONTEXT.md` (Lauf, Runde, Beitrag,
    Strang).
12. **Gates**: `bash scripts/pre-push-gate.sh` grün; Vitest-Snapshots
    aktualisiert; Backend-Contract-Tests grün.
