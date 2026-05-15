# FE-Redesign Slice 5 — Sim-Feed Dual-Column (Reddit + Twitter)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Eine neue View `StepSimulationFeedView` zeigt die Live-Diskussion einer Simulation in zwei nebeneinander stehenden Spalten — **links Reddit** (threaded mit eingerückten Replies), **rechts Twitter** (flat chronologisch). Posts kommen live über den SSE-Stream `post_created` (Slice 5-pre). Sentiment-Pulse-Bar oben, Activity-Counter, Persona-Avatar mit voice_register-Badge, SIM-Badge auf jedem Post (Wording-Glossar v1). Auto-Scroll mit Pause-Pin.

**Architecture:** SSE-Subscribe via existing `useEventStream`. Frames mit `event === 'post_created'` (typed durch Zod-Spiegel aus Slice 5-pre). Routing nach `platform` → Reddit-Column (Threading über `parent_post_id`) oder Twitter-Column (flach, neueste oben). State in einer per-View-Pinia-Store-Instanz (oder Composable, je nach existing-Pattern). Animation: `<TransitionGroup>` mit slide-in (200 ms, `prefers-reduced-motion`-aware).

**Tech Stack:** Vue 3.5, TS, Pinia, Zod, vue-i18n, reka-ui (Tabs/Tooltip), Vitest, MSW oder vergleichbarer SSE-Mock.

**Spec-Quelle:** [`docu/plans/2026-05-15-frontend-redesign-shadcn-feel.md`](2026-05-15-frontend-redesign-shadcn-feel.md), Section "Slice 5".
**Contract-Quelle:** `frontend/src/contracts/postEventContract.ts` (Slice 5-pre, schon im Epic).

**Worktree:** `/private/tmp/agora-fe-redesign-5` (Lead legt an).
**Branch:** `feat/fe-redesign-5-sim-feed` basiert auf `feat/fe-redesign-epic` post-Slice-5-pre.
**Push-Verbot.**

**Blocked by:** Slice 5-pre (✅ gemerged) — `PostCreatedEvent`-Zod-Schema + SSE-Frame `event: post_created` müssen vorhanden sein.

---

## File Structure

**Create:**
- `frontend/src/components/v4/sim-feed/FeedColumn.vue` — generischer Column-Container mit Header (Channel-Name, Live-Indicator, Auto-Scroll-Pin)
- `frontend/src/components/v4/sim-feed/RedditPost.vue` — Post mit Voting-Visualisierung und Comment-Indent
- `frontend/src/components/v4/sim-feed/RedditThread.vue` — Rekursive Reply-Tree-Komponente (max-depth 4 visuell, deeper als "show more")
- `frontend/src/components/v4/sim-feed/TwitterPost.vue` — Flat Post mit Avatar+Handle+Body+Reactions
- `frontend/src/components/v4/sim-feed/PersonaAvatar.vue` — Initialen-Avatar mit voice_register-Badge
- `frontend/src/components/v4/sim-feed/SimulationPulseBar.vue` — Sentiment-Heatbar (last-N-window) + Activity-Counter
- `frontend/src/components/v4/sim-feed/SimBadge.vue` — kleines "SIM"-Pill für Wording-Glossar-Konformität
- `frontend/src/components/v4/sim-feed/index.ts` — Re-Exports
- `frontend/src/composables/useSimFeed.ts` — State-Management pro Simulation (Posts + Threading + Activity-EMA)
- `frontend/src/composables/__tests__/useSimFeed.spec.ts`
- `frontend/src/views/v4/steps/StepSimulationFeedView.vue` — Layout-Host für die zwei Columns + Pulse-Bar
- `frontend/src/components/v4/sim-feed/__tests__/` — Specs für jede Component-Family (mind. 1 pro File)
- `docu/2026-05-15-fe-redesign-slice-5-worklog.md`

**Modify:**
- `frontend/src/router/index.ts` — neue Route `/v4/simulation/:simulationId/feed`
- `frontend/src/views/v4/steps/StepSimulationView.vue` — Tab-Switch zwischen "Pipeline" und "Feed" im Header
- `frontend/src/locales/de.json` + `en.json` — i18n-Keys für die Feed-View

**Do NOT touch:**
- `useEventStream.ts` / `stream.ts` — Slice 5-pre hat schon typisierte Variants gebaut, hier nur konsumieren.
- Backend.
- Andere Slice-Komponenten (forms, data, shell außer der Route).

---

## Pre-Flight

- [ ] **Step 0.1: Worktree-Check + Slice-5-pre-Verfügbarkeit**

```bash
cd /private/tmp/agora-fe-redesign-5
git branch --show-current
test -L frontend/node_modules && echo OK || echo FEHLT
test -f frontend/src/contracts/postEventContract.ts && echo "5-pre verfügbar" || echo "MISSING 5-pre"
grep -n "post_created" frontend/src/api/stream.ts || echo "stream.ts hat noch kein post_created — STOP"
bun run typecheck && echo "Baseline OK"
```

Expected: alles ok. Bei MISSING → STOP an Lead.

---

## Task 1: useSimFeed Composable (RED → GREEN)

State-Manager pro Simulation. Verwaltet zwei Listen (Reddit/Twitter), Threading-Index für Reddit, Sentiment-EMA, Activity-Counter.

**Files:**
- Create: `frontend/src/composables/__tests__/useSimFeed.spec.ts`
- Create: `frontend/src/composables/useSimFeed.ts`

- [ ] **Step 1.1: Spec**

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { useSimFeed } from '../useSimFeed'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

function mkPost(overrides: Partial<PostCreatedEvent>): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'sim-1',
    post_id: 'p-1',
    parent_post_id: null,
    platform: 'reddit',
    persona_id: 'alice',
    voice_register: 'casual',
    is_simulated: true,
    body: 'hi',
    timestamp: '2026-05-15T12:00:00Z',
    ...overrides,
  }
}

describe('useSimFeed', () => {
  beforeEach(() => {
    /* Pinia-Reset oder Composable-Singleton-Reset, je nach Pattern */
  })

  it('Default: leere Reddit- und Twitter-Listen', () => {
    const feed = useSimFeed('sim-1')
    expect(feed.redditPosts.value).toEqual([])
    expect(feed.twitterPosts.value).toEqual([])
  })

  it('post_created mit platform=reddit landet in redditPosts', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'p-1' }))
    expect(feed.redditPosts.value).toHaveLength(1)
    expect(feed.twitterPosts.value).toHaveLength(0)
  })

  it('post_created mit platform=twitter landet in twitterPosts', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'twitter', post_id: 'p-1' }))
    expect(feed.twitterPosts.value).toHaveLength(1)
  })

  it('Reddit-Posts mit parent_post_id werden als Reply-Tree gruppiert', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'p-1', parent_post_id: null }))
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'p-2', parent_post_id: 'p-1' }))
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'p-3', parent_post_id: 'p-1' }))

    const tree = feed.redditTree.value
    expect(tree).toHaveLength(1) // 1 Top-Level-Post
    expect(tree[0].children).toHaveLength(2)
    expect(tree[0].children.map((c) => c.post_id)).toEqual(['p-2', 'p-3'])
  })

  it('Posts werden nicht dupliziert bei doppeltem post_id', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ post_id: 'p-1' }))
    feed.ingest(mkPost({ post_id: 'p-1' }))
    expect(feed.redditPosts.value).toHaveLength(1)
  })

  it('Twitter sortiert nach timestamp DESC (neueste oben)', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'twitter', post_id: 'p-old', timestamp: '2026-05-15T12:00:00Z' }))
    feed.ingest(mkPost({ platform: 'twitter', post_id: 'p-new', timestamp: '2026-05-15T12:01:00Z' }))
    expect(feed.twitterPosts.value.map((p) => p.post_id)).toEqual(['p-new', 'p-old'])
  })

  it('activityRate berechnet Posts/min (EMA über last 30 Posts)', () => {
    const feed = useSimFeed('sim-1')
    for (let i = 0; i < 5; i++) {
      feed.ingest(
        mkPost({ post_id: `p-${i}`, timestamp: new Date(Date.now() - (5 - i) * 1000).toISOString() }),
      )
    }
    expect(feed.activityRate.value).toBeGreaterThan(0)
  })

  it('clear() leert beide Listen', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'reddit' }))
    feed.ingest(mkPost({ platform: 'twitter', post_id: 'p-x' }))
    feed.clear()
    expect(feed.redditPosts.value).toEqual([])
    expect(feed.twitterPosts.value).toEqual([])
  })
})
```

- [ ] **Step 1.2: Tests rot**

```bash
bun test -- --run src/composables/__tests__/useSimFeed.spec.ts
```

- [ ] **Step 1.3: Composable schreiben (GREEN)**

```typescript
/**
 * useSimFeed — State pro Simulation: Reddit-Thread + Twitter-Flow.
 *
 * Slice FE-Redesign-5 · 2026-05-15
 *
 * Konsumiert PostCreatedEvent (Slice 5-pre), routet nach platform,
 * dedupliziert per post_id, baut Reddit-Reply-Tree, sortiert Twitter
 * nach timestamp DESC.
 */

import { computed, ref } from 'vue'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

export interface RedditNode extends PostCreatedEvent {
  children: RedditNode[]
}

const stores = new Map<string, ReturnType<typeof createStore>>()

function createStore(simulationId: string) {
  const all = ref<PostCreatedEvent[]>([])
  const seen = new Set<string>()

  function ingest(post: PostCreatedEvent): void {
    if (post.simulation_id !== simulationId) return
    if (seen.has(post.post_id)) return
    seen.add(post.post_id)
    all.value.push(post)
  }

  function clear(): void {
    all.value = []
    seen.clear()
  }

  const redditPosts = computed(() => all.value.filter((p) => p.platform === 'reddit'))
  const twitterPosts = computed(() =>
    [...all.value.filter((p) => p.platform === 'twitter')].sort(
      (a, b) => b.timestamp.localeCompare(a.timestamp),
    ),
  )

  const redditTree = computed<RedditNode[]>(() => {
    const byId = new Map<string, RedditNode>()
    const roots: RedditNode[] = []
    for (const p of redditPosts.value) {
      byId.set(p.post_id, { ...p, children: [] })
    }
    for (const p of redditPosts.value) {
      const node = byId.get(p.post_id)!
      if (p.parent_post_id && byId.has(p.parent_post_id)) {
        byId.get(p.parent_post_id)!.children.push(node)
      } else {
        roots.push(node)
      }
    }
    return roots
  })

  const activityRate = computed(() => {
    const recent = all.value.slice(-30)
    if (recent.length < 2) return 0
    const first = Date.parse(recent[0].timestamp)
    const last = Date.parse(recent[recent.length - 1].timestamp)
    const minutes = Math.max((last - first) / 60_000, 1 / 60)
    return recent.length / minutes
  })

  return { redditPosts, twitterPosts, redditTree, activityRate, ingest, clear }
}

export function useSimFeed(simulationId: string) {
  if (!stores.has(simulationId)) {
    stores.set(simulationId, createStore(simulationId))
  }
  return stores.get(simulationId)!
}
```

- [ ] **Step 1.4: Tests grün + Commit**

---

## Task 2: PersonaAvatar + SimBadge (kleine Bausteine)

**Files:**
- Create: `frontend/src/components/v4/sim-feed/PersonaAvatar.vue`
- Create: `frontend/src/components/v4/sim-feed/SimBadge.vue`
- Create: `frontend/src/components/v4/sim-feed/__tests__/PersonaAvatar.spec.ts`
- Create: `frontend/src/components/v4/sim-feed/__tests__/SimBadge.spec.ts`

- [ ] **Step 2.1: PersonaAvatar**

```vue
<script setup lang="ts">
import type { VoiceRegister } from '@/contracts/postEventContract'

const props = defineProps<{
  personaId: string
  voiceRegister: VoiceRegister
}>()

const initials = computed(() => props.personaId.slice(0, 2).toUpperCase())

const registerColor: Record<VoiceRegister, string> = {
  formal: 'var(--accent-blue, #2563eb)',
  casual: 'var(--accent-green, #10b981)',
  jugendsprache: 'var(--accent-purple, #a855f7)',
}

import { computed } from 'vue'
</script>

<template>
  <div class="pa-root" :title="`${personaId} · ${voiceRegister}`">
    <div class="pa-circle" :style="{ '--ring': registerColor[voiceRegister] }">
      {{ initials }}
    </div>
    <span class="pa-register" aria-hidden="true">{{ voiceRegister.charAt(0) }}</span>
  </div>
</template>

<style scoped>
.pa-root {
  position: relative;
  width: 32px;
  height: 32px;
}
.pa-circle {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: var(--surface-muted, #f3f4f6);
  border: 2px solid var(--ring);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-primary);
}
.pa-register {
  position: absolute;
  bottom: -2px;
  right: -2px;
  width: 14px;
  height: 14px;
  background: var(--ring);
  color: #fff;
  border-radius: 50%;
  font-size: 9px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
```

- [ ] **Step 2.2: SimBadge**

```vue
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t, te } = useI18n()
const label = te('feed.simBadge') ? t('feed.simBadge') : 'SIM'
</script>

<template>
  <span class="sim-badge" :title="`${label} · simuliert (Wording-Glossar v1)`">{{ label }}</span>
</template>

<style scoped>
.sim-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.06em;
  border-radius: 3px;
  background: var(--status-amber-bg, rgba(255, 200, 50, 0.18));
  color: var(--status-amber, #b45309);
  text-transform: uppercase;
}
</style>
```

- [ ] **Step 2.3: Specs minimal**

```typescript
// PersonaAvatar.spec.ts
it('rendert Initialen aus persona_id', () => {
  const wrapper = mount(PersonaAvatar, { props: { personaId: 'alice42', voiceRegister: 'casual' } })
  expect(wrapper.text()).toContain('AL')
})

// SimBadge.spec.ts
it('rendert SIM-Label', () => {
  const wrapper = mount(SimBadge)
  expect(wrapper.text()).toBe('SIM')
})
```

- [ ] **Step 2.4: Tests grün + Commit**

---

## Task 3: TwitterPost + RedditPost + RedditThread

**Files:**
- Create: `frontend/src/components/v4/sim-feed/TwitterPost.vue`
- Create: `frontend/src/components/v4/sim-feed/RedditPost.vue`
- Create: `frontend/src/components/v4/sim-feed/RedditThread.vue`
- Create: `frontend/src/components/v4/sim-feed/__tests__/TwitterPost.spec.ts`
- Create: `frontend/src/components/v4/sim-feed/__tests__/RedditThread.spec.ts`

- [ ] **Step 3.1: TwitterPost**

```vue
<script setup lang="ts">
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import PersonaAvatar from './PersonaAvatar.vue'
import SimBadge from './SimBadge.vue'

defineProps<{ post: PostCreatedEvent }>()
</script>

<template>
  <article class="tw-root" role="article">
    <PersonaAvatar :persona-id="post.persona_id" :voice-register="post.voice_register" />
    <div class="tw-body">
      <header class="tw-header">
        <span class="tw-handle">@{{ post.persona_id }}</span>
        <SimBadge v-if="post.is_simulated" />
        <time class="tw-time" :datetime="post.timestamp">{{ post.timestamp.slice(11, 16) }}</time>
      </header>
      <p class="tw-content">{{ post.body }}</p>
    </div>
  </article>
</template>

<style scoped>
.tw-root {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--hairline);
}
.tw-body { flex: 1; min-width: 0; }
.tw-header {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 4px;
}
.tw-handle { font-weight: 600; font-size: 13px; }
.tw-time { font-size: 11px; color: var(--text-secondary); margin-left: auto; }
.tw-content { margin: 0; font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
</style>
```

- [ ] **Step 3.2: RedditPost + RedditThread** (rekursiv)

RedditPost (Leaf):

```vue
<script setup lang="ts">
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import PersonaAvatar from './PersonaAvatar.vue'
import SimBadge from './SimBadge.vue'

defineProps<{ post: PostCreatedEvent; depth: number }>()
</script>

<template>
  <article class="rp-root" role="article" :data-depth="depth">
    <div class="rp-rail" aria-hidden="true"></div>
    <PersonaAvatar :persona-id="post.persona_id" :voice-register="post.voice_register" />
    <div class="rp-body">
      <header class="rp-header">
        <span class="rp-user">u/{{ post.persona_id }}</span>
        <SimBadge v-if="post.is_simulated" />
      </header>
      <p class="rp-content">{{ post.body }}</p>
    </div>
  </article>
</template>
```

RedditThread (rekursiv mit max-depth 4):

```vue
<script setup lang="ts">
import RedditPost from './RedditPost.vue'
import type { RedditNode } from '@/composables/useSimFeed'

const props = defineProps<{ node: RedditNode; depth?: number }>()
const MAX_DEPTH = 4
</script>

<template>
  <div class="rt-root" :style="{ '--indent': `${(props.depth ?? 0) * 16}px` }">
    <RedditPost :post="node" :depth="depth ?? 0" />
    <template v-if="(depth ?? 0) < MAX_DEPTH">
      <RedditThread
        v-for="child in node.children"
        :key="child.post_id"
        :node="child"
        :depth="(depth ?? 0) + 1"
      />
    </template>
    <button
      v-else-if="node.children.length > 0"
      type="button"
      class="rt-show-more"
    >
      {{ node.children.length }} weitere Replies anzeigen
    </button>
  </div>
</template>
```

(Styles und Tests-Skelett analog Twitter.)

- [ ] **Step 3.3: Specs minimal (mind. 2 pro Komponente)**

- [ ] **Step 3.4: Commit**

---

## Task 4: FeedColumn + SimulationPulseBar

**Files:**
- Create: `frontend/src/components/v4/sim-feed/FeedColumn.vue`
- Create: `frontend/src/components/v4/sim-feed/SimulationPulseBar.vue`
- Create: Specs

- [ ] **Step 4.1: FeedColumn**

Generischer Column-Container:
- Header mit Channel-Name (Reddit/Twitter) + Live-Indicator-Dot
- Default-Slot für Posts
- Auto-Scroll an Default, sichtbarer "Pause"-Chip wenn User manuell scrolled (Pattern: `IntersectionObserver` auf untersten Anchor)
- `role="feed"`, `aria-busy="false"` Default

- [ ] **Step 4.2: SimulationPulseBar**

Horizontale Heatbar aus letzten 30 Posts:
- Pro Post ein Color-Stripe (rot/grau/grün — Sentiment-Heuristik aus `body`-Länge oder echtem Sentiment-Feld später)
- Aktivität: Posts/min als Text (aus `useSimFeed.activityRate`)
- **Wichtig:** Ein Sentiment-Feld ist im Slice-5-pre-Contract NICHT enthalten — als Followup markiert. Bis das Feld kommt: Pulse-Bar zeigt nur Activity-Counter, Heatbar bleibt einfarbig (Accent).

- [ ] **Step 4.3: Specs + Commit**

---

## Task 5: StepSimulationFeedView (Layout-Host)

**Files:**
- Create: `frontend/src/views/v4/steps/StepSimulationFeedView.vue`
- Modify: `frontend/src/router/index.ts` (neue Route)
- Modify: `frontend/src/views/v4/steps/StepSimulationView.vue` (Tab-Switch im Header)

- [ ] **Step 5.1: View-Datei**

```vue
<script setup lang="ts">
import { onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { useEventStream } from '@/composables/useEventStream'
import { useSimFeed } from '@/composables/useSimFeed'
import FeedColumn from '@/components/v4/sim-feed/FeedColumn.vue'
import RedditThread from '@/components/v4/sim-feed/RedditThread.vue'
import TwitterPost from '@/components/v4/sim-feed/TwitterPost.vue'
import SimulationPulseBar from '@/components/v4/sim-feed/SimulationPulseBar.vue'

const route = useRoute()
const simulationId = String(route.params.simulationId)
const feed = useSimFeed(simulationId)

const stream = useEventStream(simulationId)
const unsubscribe = stream.on('post_created', (data) => feed.ingest(data))

onMounted(() => stream.open())
onBeforeUnmount(() => {
  unsubscribe()
  stream.close()
})
</script>

<template>
  <div class="sf-root">
    <SimulationPulseBar
      :activity-rate="feed.activityRate.value"
      :reddit-count="feed.redditPosts.value.length"
      :twitter-count="feed.twitterPosts.value.length"
    />
    <div class="sf-columns">
      <FeedColumn :title="$t('feed.reddit')" channel="reddit">
        <RedditThread
          v-for="node in feed.redditTree.value"
          :key="node.post_id"
          :node="node"
        />
      </FeedColumn>
      <FeedColumn :title="$t('feed.twitter')" channel="twitter">
        <TransitionGroup name="fade-slide">
          <TwitterPost
            v-for="post in feed.twitterPosts.value"
            :key="post.post_id"
            :post="post"
          />
        </TransitionGroup>
      </FeedColumn>
    </div>
  </div>
</template>

<style scoped>
.sf-root { display: flex; flex-direction: column; height: 100%; }
.sf-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  flex: 1;
  min-height: 0;
}
.fade-slide-enter-active { transition: all 200ms ease; }
.fade-slide-enter-from { opacity: 0; transform: translateY(-8px); }
@media (prefers-reduced-motion: reduce) {
  .fade-slide-enter-active { transition: none; }
}
</style>
```

> **API-Hinweis:** `useEventStream` API ist aktuell nicht 100% klar — Worker liest `frontend/src/composables/useEventStream.ts` (Slice 5-pre hat es typisiert) und passt den `.on('post_created', cb)`-Aufruf an die existing Signatur an. Wenn API anders, Briefing zurück an Lead.

- [ ] **Step 5.2: Route + Tab-Switch**

```typescript
// router/index.ts
{
  path: '/v4/simulation/:simulationId/feed',
  name: 'StepSimulationFeed',
  component: () => import('../views/v4/steps/StepSimulationFeedView.vue'),
  props: true,
},
```

In `StepSimulationView.vue` Header: Tab-Switch zwischen Pipeline (existing) und Feed (neu) via reka-ui `Tabs`.

- [ ] **Step 5.3: i18n-Keys** (`de.json` + `en.json`):

```json
{
  "feed": {
    "reddit": "Reddit",
    "twitter": "Twitter",
    "simBadge": "SIM",
    "activity": "Posts/min",
    "live": "Live"
  }
}
```

- [ ] **Step 5.4: View-Spec** — Mock useEventStream, ingest 5 Reddit + 3 Twitter Posts, prüfe DOM-Counts.

- [ ] **Step 5.5: Commit**

---

## Task 6: Verification + Worklog

- [ ] **Step 6.1: Gates**

```bash
cd /private/tmp/agora-fe-redesign-5/frontend
bun run typecheck && bun run test:coverage && bun run build && bun run lint
```

- [ ] **Step 6.2: Manueller Smoke (wenn Backend lokal läuft)**

```bash
# Backend mit Stub-Sim starten
# Browser: http://localhost:5173/v4/simulation/<sim-id>/feed
# Beobachte: Reddit-Column threaded, Twitter-Column flat, Pulse-Bar pulst
```

Wenn kein Backend verfügbar: SSE-Mock im Browser DevTools Console:
```js
window.__simFeedMock(/* 5 Reddit + 3 Twitter Posts via Console-Helper */)
```

- [ ] **Step 6.3: Worklog**

Pflicht-Sektionen:
- Was die View kann (Dual-Column, Threading, Pulse-Bar, Animation)
- Test-Delta (mind. 7 neue Spec-Files)
- Bundle-Delta (Erwartung: +30-50 KB gz wegen Komponenten-Vielfalt)
- Followups: Sentiment-Feld (nicht im Contract), Voting auf RedditPost, Auto-Scroll-Pin
- Skip-Begründungen

- [ ] **Step 6.4: code-review-graph update + Rückmeldungs-Format**

```
Branch: feat/fe-redesign-5-sim-feed
Letzter Commit: <hash>
Test-Delta: +<N> specs (useSimFeed=8, PersonaAvatar=1, SimBadge=1, TwitterPost=2, RedditThread=2, FeedColumn=2, PulseBar=2, View=3)
Bundle-Delta: +<X> KB gz
Visual-Smoke: <Browser-DevTools-Output / not tested + Begründung>
useEventStream-API: <wie konsumiert, ggf. Anpassung dokumentieren>
Gaps: Sentiment-Feld fehlt im PostCreatedEvent (Followup), Voting-Pattern noch nicht implementiert
Worklog: docu/2026-05-15-fe-redesign-slice-5-worklog.md
```

---

## Self-Review

- ✅ Dual-Column Reddit/Twitter → Task 5
- ✅ Threading via parent_post_id → Task 1 (redditTree)
- ✅ Twitter sortiert nach timestamp DESC → Task 1
- ✅ Persona-Avatar mit voice_register-Badge → Task 2
- ✅ SIM-Badge nach Wording-Glossar v1 → Task 2 + 3 + 5
- ✅ Auto-Scroll-Pause-Pin → Task 4 (FeedColumn)
- ✅ Sentiment-Pulse-Bar → Task 4 (mit Followup-Disclaimer wegen fehlendem Sentiment-Feld)
- ✅ Activity-Counter (EMA) → Task 1
- ✅ Animation 200 ms slide-in, prefers-reduced-motion → Task 5
- ✅ role="feed", role="article" → Task 3, 4
- ⚠️ Voting-Visualisierung auf RedditPost — bewusst out-of-scope (Backend-Field fehlt)
- ⚠️ Tab-Switch im StepSimulationView.vue — Plan-Skelett, exakter Patch im Worker je nach existing Tabs-Pattern

**Type consistency:** `PostCreatedEvent`, `RedditNode`, `useSimFeed`, `feed.redditPosts`/`twitterPosts`/`redditTree`/`activityRate`/`ingest`/`clear` durchgängig.
