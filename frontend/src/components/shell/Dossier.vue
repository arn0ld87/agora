<template>
  <div
    class="dossier"
    :data-testid="DossierTestId.root"
    role="region"
    :aria-labelledby="props.object ? 'dossier-title' : undefined"
    :aria-label="props.object ? undefined : t('views.shelf.overview.ariaLabel')"
  >
    <div v-if="!props.object" class="dossier__overview" :data-testid="DossierTestId.overview">
      <div class="dossier__ov-head">
        <div class="dossier__ov-head-main">
          <h2 class="dossier__ov-title">{{ t(overviewHeadingKey, { live: liveItems.length, attn: attentionItems.length }) }}</h2>
          <p class="dossier__ov-subtitle">{{ t('views.shelf.overview.subtitle') }}</p>
        </div>
        <button type="button" class="dossier__btn dossier__btn--primary" :data-testid="DossierTestId.overviewNewSource" @click="goToNewObject">
          {{ t('views.shelf.overview.newSource') }}
        </button>
      </div>

      <div class="dossier__ov-grid">
        <div class="dossier__ov-col">
          <section class="dossier__ov-section">
            <div class="dossier__ov-section-head">
              <h3 class="dossier__ov-heading">{{ t('views.shelf.overview.attentionTitle') }}</h3>
              <span v-if="attentionItems.length" class="dossier__ov-count">{{ t('views.shelf.overview.attentionCount', { n: attentionItems.length }) }}</span>
            </div>
            <ul v-if="attentionItems.length" class="dossier__ov-attn-list">
              <li v-for="item in attentionItems" :key="`${item.kind}:${item.id}`" class="dossier__ov-attn" :data-testid="DossierTestId.overviewAttentionItem">
                <span class="dossier__ov-attn-sig" aria-hidden="true">!</span>
                <span class="dossier__ov-attn-main">
                  <span class="dossier__ov-attn-title" :title="item.title">{{ item.title }}</span>
                  <span class="dossier__ov-attn-status">{{ item.statusLine }}</span>
                </span>
                <button v-if="item.nextAction" type="button" class="dossier__btn dossier__btn--ghost" @click="goTo(item.nextAction.to)">
                  {{ item.nextAction.label }}
                </button>
              </li>
            </ul>
            <p v-else class="dossier__ov-empty">{{ t('views.shelf.overview.attentionEmpty') }}</p>
          </section>

          <section class="dossier__ov-section">
            <div class="dossier__ov-section-head">
              <h3 class="dossier__ov-heading">{{ t('views.shelf.overview.recentTitle') }}</h3>
            </div>
            <ul v-if="recentItems.length" class="dossier__ov-list">
              <li v-for="item in recentItems" :key="`${item.kind}:${item.id}`">
                <button
                  type="button"
                  class="dossier__ov-list-row"
                  :data-testid="DossierTestId.overviewRecentItem"
                  @click="openObject(item)"
                >
                  <span class="dossier__ov-list-title" :title="item.title">{{ item.title }}</span>
                  <span class="dossier__ov-list-status">{{ item.statusLine }}</span>
                  <span class="dossier__ov-list-time">{{ formatUpdatedAt(item.updatedAt) }}</span>
                </button>
              </li>
            </ul>
            <p v-else class="dossier__ov-empty">{{ t('views.shelf.overview.recentEmpty') }}</p>
          </section>
        </div>

        <div class="dossier__ov-col">
          <section class="dossier__ov-section">
            <div class="dossier__ov-section-head">
              <h3 class="dossier__ov-heading">{{ t('views.shelf.overview.liveTitle') }}</h3>
              <span v-if="liveItems.length" class="dossier__ov-count dossier__ov-count--live">{{ t('shelf.activity', { n: liveItems.length }) }}</span>
            </div>
            <div v-if="liveItems.length" class="dossier__ov-live-list">
              <div v-for="item in liveItems" :key="`${item.kind}:${item.id}`" class="dossier__ov-live-card" :data-testid="DossierTestId.overviewLiveItem">
                <div class="dossier__ov-live-head"><i class="dossier__ov-dot dossier__ov-dot--live" aria-hidden="true"></i><span class="dossier__ov-live-title" :title="item.title">{{ item.title }}</span></div>
                <p class="dossier__ov-live-status">{{ item.statusLine }}</p>
                <div v-if="item.active && item.active.progress !== null" class="dossier__ov-bar">
                  <i :style="{ width: `${item.active.progress}%` }"></i>
                </div>
                <div class="dossier__ov-live-actions">
                  <button
                    v-if="item.active?.pausable && item.active.simulationId"
                    type="button"
                    class="dossier__btn dossier__btn--ghost"
                    @click="togglePause(item.active)"
                  >
                    {{ item.active.status === 'paused' ? t('shelf.resume') : t('shelf.pause') }}
                  </button>
                  <button type="button" class="dossier__btn dossier__btn--ghost" @click="cancelAction.cancel(item.active!.runId)">
                    {{ t('shelf.cancel') }}
                  </button>
                  <button v-if="item.nextAction" type="button" class="dossier__btn dossier__btn--primary" @click="goTo(item.nextAction.to)">
                    {{ item.nextAction.label }}
                  </button>
                </div>
              </div>
            </div>
            <p v-else class="dossier__ov-empty">{{ t('views.shelf.overview.liveEmpty') }}</p>
          </section>

          <section v-if="systemRows.length" class="dossier__ov-section">
            <div class="dossier__ov-section-head">
              <h3 class="dossier__ov-heading">{{ t('dashboard.system.title') }}</h3>
            </div>
            <ul class="dossier__ov-system-list">
              <li v-for="row in systemRows" :key="row.key" class="dossier__ov-system-row" :data-testid="DossierTestId.overviewSystemRow">
                <i class="dossier__ov-dot" :class="row.ok ? 'dossier__ov-dot--ok' : 'dossier__ov-dot--err'" aria-hidden="true"></i>
                <span class="dossier__ov-system-label">{{ row.label }}</span>
                <span v-if="row.hint" class="dossier__ov-system-hint">{{ row.hint }}</span>
              </li>
            </ul>
            <router-link :to="{ name: 'SettingsGeneral' }" class="dossier__ov-link">{{ t('views.shelf.overview.openSettings') }}</router-link>
          </section>
        </div>
      </div>
    </div>

    <template v-else>
      <div class="dossier__head">
        <div class="dossier__head-main">
          <div class="dossier__kicker">{{ SHELF_KIND_TAG[props.object.kind] }}</div>
          <h2 id="dossier-title" class="dossier__title" :title="props.object.title" :data-testid="DossierTestId.title">{{ props.object.title }}</h2>
          <p class="dossier__summary" :data-testid="DossierTestId.summary">{{ props.object.statusLine }}</p>
        </div>
        <div class="dossier__head-actions">
          <template v-if="props.object.active">
            <button
              type="button"
              class="dossier__btn dossier__btn--ghost"
              :data-testid="DossierTestId.cancel"
              @click="cancelAction.cancel(props.object.active.runId)"
            >
              {{ t('shelf.cancel') }}
            </button>
            <button
              v-if="props.object.active.pausable && props.object.active.simulationId"
              type="button"
              class="dossier__btn dossier__btn--ghost"
              :data-testid="DossierTestId.pause"
              @click="togglePause(props.object.active)"
            >
              {{ props.object.active.status === 'paused' ? t('shelf.resume') : t('shelf.pause') }}
            </button>
          </template>
          <!-- Aus einem Bericht laesst sich ein neuer Lauf ableiten: die
               Personas des Vorlaufs bleiben, die Auswertung wird neu.
               Der Weg existierte laengst, lag aber im vierten Schritt
               der alten Prozesskette und war praktisch unauffindbar. -->
          <!-- Ein Personasatz ist damit nicht nur Archivgut: aus ihm
               laesst sich direkt ein Lauf starten — ohne Dokument,
               ohne Graph (Block B4). -->
          <button
            v-if="props.object.kind === 'personasatz'"
            type="button"
            class="dossier__btn dossier__btn--primary"
            :data-testid="DossierTestId.startFromPersona"
            :disabled="startBusy"
            @click="onStartFromPersona"
          >
            {{ t('shelf.dossier.startFromPersona') }}
          </button>
          <button
            v-if="canDerive"
            type="button"
            class="dossier__btn dossier__btn--ghost"
            :data-testid="DossierTestId.derive"
            :disabled="deriveBusy"
            @click="onDerive"
          >
            {{ t('shelf.dossier.derive') }}
          </button>
          <button
            v-if="props.object.nextAction"
            type="button"
            class="dossier__btn dossier__btn--primary"
            :data-testid="DossierTestId.openFull"
            @click="openFull"
          >
            {{ props.object.nextAction.label }} &#9166;
          </button>
        </div>
      </div>

      <p v-if="deriveError" class="dossier__error" role="alert">{{ deriveError }}</p>

      <!-- Kennzahlstreifen: Status/Zeit/ID gelten fuer jede Sorte, der
           Rest ist kind-spezifisch und nur sichtbar wenn der Wert bekannt
           ist (Redesign PR 4, "was kein Feld hat, weglassen"). `dl` statt
           Divs: Label/Wert sind semantisch Begriff/Beschreibung. -->
      <dl class="dossier__kpis" :data-testid="DossierTestId.kpis">
        <div class="dossier__kpi">
          <dt class="dossier__kpi-label">{{ t('common.status') }}</dt>
          <dd class="dossier__kpi-value dossier__kpi-value--text">{{ props.object.statusLine }}</dd>
        </div>
        <div class="dossier__kpi">
          <dt class="dossier__kpi-label">{{ t('common.time') }}</dt>
          <dd class="dossier__kpi-value">{{ formatUpdatedAt(props.object.updatedAt) }}</dd>
        </div>
        <div class="dossier__kpi">
          <dt class="dossier__kpi-label">{{ t('shelf.dossier.idLabel') }}</dt>
          <dd class="dossier__kpi-value dossier__kpi-value--mono">{{ props.object.metaId }}</dd>
        </div>
        <div v-if="props.object.kind === 'lauf' && props.object.personaCount != null" class="dossier__kpi">
          <dt class="dossier__kpi-label">{{ t('views.dossier.kpiPersonas') }}</dt>
          <dd class="dossier__kpi-value">{{ props.object.personaCount }}</dd>
        </div>
        <div v-if="props.object.kind === 'lauf' && (props.object.jobs?.length ?? 0) > 0" class="dossier__kpi">
          <dt class="dossier__kpi-label">{{ t('views.dossier.kpiJobs') }}</dt>
          <dd class="dossier__kpi-value">{{ props.object.jobs!.length }}</dd>
        </div>
        <div v-if="props.object.kind === 'bericht' && detail?.parts.length" class="dossier__kpi">
          <dt class="dossier__kpi-label">{{ t('views.dossier.kpiSections') }}</dt>
          <dd class="dossier__kpi-value">{{ detail!.parts.length }}</dd>
        </div>
        <div v-if="props.object.kind === 'bericht' && detail?.evidenceSections != null" class="dossier__kpi">
          <dt class="dossier__kpi-label">{{ t('views.dossier.kpiEvidence') }}</dt>
          <dd class="dossier__kpi-value">{{ detail!.evidenceSections }}</dd>
        </div>
        <div v-if="props.object.kind === 'bericht' && detail?.claimsCount != null" class="dossier__kpi">
          <dt class="dossier__kpi-label">{{ t('views.dossier.kpiClaims') }}</dt>
          <dd class="dossier__kpi-value">{{ detail!.claimsCount }}</dd>
        </div>
      </dl>

      <!-- Bestandteile: erst beim Auswaehlen nachgeladen. Ein Bericht
           zeigt seine Abschnitte, ein Graph seine Kennzahlen, ein Lauf
           seine Akteure/Ausgabe mit Zahl + Weiter-Link (Redesign PR 4).
           Sorten ohne Detail-Endpunkt zeigen hier nichts, statt ein
           leeres Geruest zu behaupten. -->
      <section v-if="detail" class="dossier__parts" :data-testid="DossierTestId.parts">
        <p v-if="detail.summary" class="dossier__detail-summary">{{ detail.summary }}</p>
        <ul v-if="detail.parts.length" class="dossier__part-list">
          <li v-for="part in detail.parts" :key="part.title" class="dossier__part" :data-testid="DossierTestId.part">
            <span class="dossier__part-main">
              <span class="dossier__part-title">{{ part.title }}</span>
              <span class="dossier__part-desc">{{ part.description }}</span>
            </span>
            <span v-if="part.count !== undefined" class="dossier__part-count">{{ part.count }}</span>
            <button v-if="part.to" type="button" class="dossier__btn dossier__btn--ghost" @click="goTo(part.to)">
              {{ t('views.dossier.partsOpen') }}
            </button>
          </li>
        </ul>
      </section>

      <!-- Jobs-Zeitleiste (nur Lauf, Redesign PR 4): alle Jobs des
           Vorhabens, neuestes zuerst — kommt direkt aus obj.jobs, kein
           Nachladen. -->
      <section
        v-if="props.object.kind === 'lauf' && (props.object.jobs?.length ?? 0) > 0"
        class="dossier__timeline"
        :data-testid="DossierTestId.jobsTimeline"
      >
        <h3 class="dossier__section-title">{{ t('views.dossier.jobsTimelineTitle') }}</h3>
        <ol class="dossier__timeline-list">
          <li v-for="job in props.object.jobs" :key="job.runId" class="dossier__timeline-item">
            <time class="dossier__timeline-time" :datetime="job.updatedAt">{{ formatUpdatedAt(job.updatedAt) }}</time>
            <span class="dossier__timeline-type">{{ job.runType }}</span>
            <span class="dossier__timeline-status">{{ job.message || statusText(t, `shelf.status.${job.status}`, job.status) }}</span>
          </li>
        </ol>
      </section>

      <!-- Vertrauensverteilung (nur Bericht, Redesign PR 4): Anzahl Claims
           je Confidence-Label aus der Evidence-Map. -->
      <section
        v-if="props.object.kind === 'bericht' && confidenceEntries.length > 0"
        class="dossier__confidence"
        :data-testid="DossierTestId.confidenceDistribution"
      >
        <h3 class="dossier__section-title">{{ t('views.dossier.confidenceTitle') }}</h3>
        <dl class="dossier__confidence-list">
          <div v-for="entry in confidenceEntries" :key="entry.label" class="dossier__confidence-row">
            <dt>{{ t(`views.dossier.confidence.${entry.label}`) }}</dt>
            <dd>{{ entry.count }}</dd>
          </div>
        </dl>
      </section>

      <!-- Red-Team-Befunde (nur Bericht, Redesign PR 4): direkt aus dem
           Report-Contract, keine Herleitung. -->
      <section
        v-if="props.object.kind === 'bericht' && (detail?.redTeamFindings?.length ?? 0) > 0"
        class="dossier__redteam"
        :data-testid="DossierTestId.redTeamFindings"
      >
        <h3 class="dossier__section-title">{{ t('views.dossier.redTeamTitle') }}</h3>
        <ul class="dossier__redteam-list">
          <li v-for="(finding, i) in detail!.redTeamFindings" :key="i">{{ finding }}</li>
        </ul>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { DossierTestId } from '../../contracts/testIds'
import { SHELF_KIND_TAG, type ShelfObject } from '../../types/shelf'
import { useCancelAction } from './useCancelAction'
import { useObjectDetail } from '../../composables/useObjectDetail'
import { useDeriveSimulation } from '../../composables/useDeriveSimulation'
import { useStartFromPersona } from '../../composables/useStartFromPersona'
import { useSystemStatus } from '../../composables/useSystemStatus'
import { formatShelfDate, statusText, type useShelf } from '../../composables/useShelf'
import type { ConfidenceLabel } from '../../contracts/reportContract'

/**
 * Dossier.vue — rechte Spalte (Block B3).
 *
 * Ohne Auswahl (props.object === null) zeigt die Komponente seit
 * Redesign PR 3 die Ablage-Uebersicht (Audit-Befund „Leere Startflaeche"):
 * was braucht dich, was laeuft, was ist zuletzt fertig geworden, dazu ein
 * knapper Systemstatus. Alle Daten kommen aus props.shelf (derselbe
 * useShelf()-Rueckgabewert wie in Shelf.vue) — kein zweiter Request.
 *
 * Mit Auswahl zeigt sie das gewaehlte ShelfObject. Die „Bestandteile“-
 * Liste und der Red-Team-Kasten aus der Design-Vorlage (01-ablage.html)
 * fehlen hier weiterhin bewusst — das ist Redesign PR 4 (Kennzahlstreifen,
 * Jobs-Zeitleiste, Bericht-Summary), nicht Teil dieses Slices.
 */

const props = defineProps<{ object: ShelfObject | null; shelf: ReturnType<typeof useShelf> }>()

const { t, locale } = useI18n()
const router = useRouter()
const cancelAction = useCancelAction()

// Details werden erst beim Auswaehlen geholt, nicht fuer jede Zeile.
const { detail } = useObjectDetail(
  computed(() => props.object),
  t,
)

const { busy: deriveBusy, derive } = useDeriveSimulation()
const startFromPersona = useStartFromPersona()
const startBusy = computed(() => startFromPersona.busy.value)
const deriveError = ref('')

// ── Uebersichtszustand (kein Objekt gewaehlt) ──────────────────────
const attentionItems = computed(() => props.shelf.objects.value.filter((o) => o.nextAction?.kind === 'warn').slice(0, 5))
const liveItems = computed(() => props.shelf.activeObjects.value)
const recentItems = computed(() =>
  props.shelf.objects.value.filter((o) => o.active === null && o.nextAction?.kind !== 'warn').slice(0, 3),
)

const overviewHeadingKey = computed(() => {
  const live = liveItems.value.length
  const attn = attentionItems.value.length
  if (live > 0 && attn > 0) return 'views.shelf.overview.headingBoth'
  if (live > 0) return 'views.shelf.overview.headingLive'
  if (attn > 0) return 'views.shelf.overview.headingAttention'
  return 'views.shelf.overview.headingIdle'
})

const systemStatus = useSystemStatus()
onMounted(() => {
  void systemStatus.refresh()
})

/** Kompakter Systemstatus — nur die Quellen, die es auch bei Reachable/Unreachable meint (Ollama idle = kein Fehler, wird ausgelassen). */
const systemRows = computed(() => {
  const s = systemStatus.status.value
  if (!s) return []
  const rows: { key: string; label: string; ok: boolean; hint: string }[] = [
    { key: 'neo4j', label: t('dashboard.system.neo4j'), ok: s.neo4j.reachable, hint: s.neo4j.reachable ? '' : (s.neo4j.error ?? '') },
  ]
  if (s.ollama.reachable !== null) {
    rows.push({ key: 'ollama', label: t('dashboard.system.ollama'), ok: s.ollama.reachable, hint: s.ollama.reachable ? '' : (s.ollama.error ?? '') })
  }
  return rows
})

function goTo(to: NonNullable<ShelfObject['nextAction']>['to']): void {
  void router.push(to)
}

function openObject(obj: ShelfObject): void {
  void router.push({ name: 'ShelfObject', params: { kind: obj.kind, objectId: obj.id } })
}

function goToNewObject(): void {
  void router.push({ name: 'Dashboard' })
}

/** Ableiten gibt es nur beim Bericht, und nur wenn seine Simulation bekannt ist. */
const canDerive = computed(
  () => props.object?.kind === 'bericht' && Boolean(props.object.simulationId),
)

// ── Vertrauensverteilung (nur Bericht, Redesign PR 4) ──────────────
const CONFIDENCE_ORDER: ConfidenceLabel[] = ['speculative', 'low', 'medium', 'high', 'verified']
const confidenceEntries = computed(() => {
  const dist = detail.value?.confidenceDistribution
  if (!dist) return []
  return CONFIDENCE_ORDER.filter((label) => (dist[label] ?? 0) > 0).map((label) => ({ label, count: dist[label] ?? 0 }))
})

async function onStartFromPersona(): Promise<void> {
  const obj = props.object
  if (!obj || obj.kind !== 'personasatz') return
  deriveError.value = ''
  const res = await startFromPersona.start(obj.id, t('shelf.dossier.startName', { title: obj.title }))
  if (res) router.push({ name: 'StepEnvSetup', params: { projectId: res.simulationId } })
  else deriveError.value = t('shelf.dossier.startFailed')
}

async function onDerive(): Promise<void> {
  const obj = props.object
  if (!obj?.simulationId) return
  deriveError.value = ''
  const res = await derive(obj.simulationId, t('shelf.dossier.deriveName', { title: obj.title }))
  if (res) {
    router.push({ name: 'StepEnvSetup', params: { projectId: res.simulationId } })
  } else {
    deriveError.value = t('shelf.dossier.deriveFailed')
  }
}

function openFull(): void {
  if (!props.object?.nextAction) return
  void router.push(props.object.nextAction.to)
}

function togglePause(active: NonNullable<ShelfObject['active']>): void {
  if (!active.simulationId) return
  if (active.status === 'paused') void cancelAction.resume(active.simulationId)
  else void cancelAction.pause(active.simulationId)
}

function formatUpdatedAt(iso: string): string {
  return formatShelfDate(iso, locale.value, t)
}
</script>

<style scoped>
.dossier {
  padding: var(--sp-6) var(--sp-7);
  min-width: 0;
  overflow-y: auto;
  height: 100%;
}

.dossier__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-5);
}

.dossier__head-main {
  min-width: 0;
}

.dossier__kicker {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  margin-bottom: 6px;
}

.dossier__title {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--fs-title-1);
  font-weight: 600;
  letter-spacing: var(--tr-title-1);
  color: var(--text-primary);
}

.dossier__summary {
  margin: 6px 0 0;
  font-family: var(--font-serif);
  font-size: var(--fs-body);
  line-height: var(--lh-body);
  color: var(--text-secondary);
  max-width: 76ch;
}

.dossier__head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.dossier__btn {
  height: 32px;
  padding: 0 14px;
  border-radius: var(--r-3);
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}

.dossier__btn--ghost {
  background: transparent;
  border: 1px solid var(--hairline);
  color: var(--text-secondary);
}

.dossier__btn--ghost:hover {
  color: var(--text-primary);
  border-color: var(--hairline-strong);
}

.dossier__btn--primary {
  background: transparent;
  border: 1px solid var(--hairline-strong);
  color: var(--text-primary);
  font-weight: 600;
}

.dossier__btn--primary:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.dossier__btn:disabled {
  opacity: var(--v4-state-disabled-opacity, 0.45);
  cursor: default;
}

.dossier__btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.dossier__kpis {
  display: flex;
  flex-wrap: wrap;
  margin: var(--sp-5) 0 0;
  border-top: 1px solid var(--hairline);
  border-bottom: 1px solid var(--hairline);
}

.dossier__kpi {
  /* dt (Label) steht im Markup vor dd (Wert) — semantisch korrekt fuer
     dl, aber die Vorlage zeigt den Wert oben. column-reverse dreht nur
     die Darstellung, nicht die DOM-/Vorlesereihenfolge. */
  display: flex;
  flex-direction: column-reverse;
  flex: 1;
  min-width: 96px;
  padding: 12px 16px;
  border-left: 1px solid var(--hairline);
}

.dossier__kpi:first-child {
  border-left: 0;
  padding-left: 0;
}

.dossier__kpi > dt,
.dossier__kpi > dd {
  margin: 0;
}

.dossier__kpi-value {
  font-family: var(--font-mono);
  font-size: var(--fs-title-3);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dossier__kpi-value--text {
  font-family: var(--font-sans);
  font-size: var(--fs-callout);
}

.dossier__kpi-value--mono {
  font-size: var(--fs-footnote);
}

.dossier__kpi-label {
  font-family: var(--font-mono);
  font-size: 9.5px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  margin-bottom: 3px;
}

@media (prefers-reduced-motion: reduce) {
  .dossier__btn {
    transition: none;
  }
}

.dossier__parts {
  margin-top: var(--sp-6);
  border-top: 1px solid var(--hairline);
  padding-top: var(--sp-5);
}

.dossier__detail-summary {
  font-family: var(--font-serif);
  font-size: var(--fs-body);
  line-height: var(--lh-body);
  color: var(--text-secondary);
  margin: 0 0 var(--sp-4);
}

.dossier__part-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.dossier__part {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.dossier__part-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

.dossier__part-title {
  font-size: var(--fs-subhead);
  color: var(--text-primary);
  font-weight: 600;
}

.dossier__part-desc {
  font-size: var(--fs-footnote);
  line-height: var(--lh-footnote);
  color: var(--text-tertiary);
}

.dossier__part-count {
  font-family: var(--font-mono);
  font-size: var(--fs-title-3);
  color: var(--text-primary);
  flex-shrink: 0;
}

.dossier__section-title {
  margin: 0 0 var(--sp-3);
  font-family: var(--font-sans);
  font-size: var(--fs-subhead);
  font-weight: 600;
  color: var(--text-primary);
}

.dossier__timeline,
.dossier__confidence,
.dossier__redteam {
  margin-top: var(--sp-6);
  border-top: 1px solid var(--hairline);
  padding-top: var(--sp-5);
}

.dossier__timeline-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.dossier__timeline-item {
  display: grid;
  grid-template-columns: 80px minmax(0, 140px) minmax(0, 1fr);
  gap: var(--sp-3);
  padding: var(--sp-2) 0;
  border-top: 1px solid var(--hairline);
  font-size: var(--fs-footnote);
}

.dossier__timeline-list > .dossier__timeline-item:first-child {
  border-top: 0;
}

.dossier__timeline-time {
  font-family: var(--font-mono);
  color: var(--text-tertiary);
}

.dossier__timeline-type {
  font-family: var(--font-mono);
  color: var(--text-secondary);
}

.dossier__timeline-status {
  color: var(--text-secondary);
}

.dossier__confidence-list {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.dossier__confidence-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-3);
  font-size: var(--fs-footnote);
}

.dossier__confidence-row dt {
  margin: 0;
  color: var(--text-secondary);
}

.dossier__confidence-row dd {
  margin: 0;
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.dossier__redteam-list {
  margin: 0;
  padding-left: 1.1em;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  font-size: var(--fs-footnote);
  color: var(--text-secondary);
}

.dossier__error {
  margin: var(--sp-3) 0 0;
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-3);
  background: var(--status-red-bg);
  color: var(--status-red);
  font-size: var(--fs-footnote);
}

/* ── Uebersichtszustand (Redesign PR 3) ──────────────────────────── */

.dossier__ov-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-6);
}

.dossier__ov-head-main {
  min-width: 0;
}

.dossier__ov-title {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--fs-title-1);
  font-weight: 600;
  letter-spacing: var(--tr-title-1);
  color: var(--text-primary);
  text-wrap: balance;
}

.dossier__ov-subtitle {
  margin: var(--sp-2) 0 0;
  font-size: var(--fs-callout);
  color: var(--text-secondary);
  max-width: 62ch;
}

.dossier__ov-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--sp-7);
  margin-top: var(--sp-6);
}

.dossier__ov-col {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-7);
}

.dossier__ov-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-3);
}

.dossier__ov-heading {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--fs-title-3);
  font-weight: 600;
  color: var(--text-primary);
}

.dossier__ov-count {
  font-size: var(--fs-caption-1);
  color: var(--text-tertiary);
}

.dossier__ov-count--live {
  color: var(--status-teal);
}

.dossier__ov-empty {
  margin: var(--sp-3) 0 0;
  font-size: var(--fs-callout);
  color: var(--text-tertiary);
}

.dossier__ov-attn-list {
  list-style: none;
  margin: var(--sp-3) 0 0;
  padding: 0;
}

.dossier__ov-attn {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) 0;
  border-top: 1px solid var(--hairline);
}

.dossier__ov-attn:last-child {
  border-bottom: 1px solid var(--hairline);
}

.dossier__ov-attn-sig {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 10.5px;
  background: var(--status-orange-bg);
  color: var(--status-orange);
}

.dossier__ov-attn-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dossier__ov-attn-title {
  display: block;
  min-width: 0;
  font-size: var(--fs-callout);
  color: var(--text-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dossier__ov-attn-status {
  font-size: var(--fs-caption-1);
  color: var(--text-secondary);
}

.dossier__ov-list {
  list-style: none;
  margin: var(--sp-3) 0 0;
  padding: 0;
}

.dossier__ov-list-row {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  column-gap: var(--sp-3);
  row-gap: 2px;
  align-items: baseline;
  padding: var(--sp-2) 0;
  border-top: 1px solid var(--hairline);
  background: transparent;
  border-left: 0;
  border-right: 0;
  border-bottom: 0;
  text-align: left;
  cursor: pointer;
  font-family: var(--font-sans);
}

.dossier__ov-list-title {
  min-width: 0;
  font-size: var(--fs-callout);
  color: var(--text-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dossier__ov-list-status {
  grid-column: 1;
  font-size: var(--fs-caption-1);
  color: var(--text-secondary);
}

.dossier__ov-list-time {
  grid-row: 1 / span 2;
  align-self: center;
  font-family: var(--font-mono);
  font-size: var(--fs-footnote);
  color: var(--text-tertiary);
  white-space: nowrap;
}

.dossier__ov-list-row:hover {
  background: var(--surface-hover);
}

.dossier__ov-list-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.dossier__ov-live-list {
  margin-top: var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.dossier__ov-live-card {
  border: 1px solid var(--status-teal-bg);
  border-radius: var(--r-5);
  padding: var(--sp-4);
  background: var(--status-teal-bg);
}

.dossier__ov-live-head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  min-width: 0;
}

.dossier__ov-live-title {
  flex: 1;
  min-width: 0;
  font-size: var(--fs-callout);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dossier__ov-live-status {
  margin: var(--sp-1) 0 0;
  font-size: var(--fs-caption-1);
  color: var(--text-secondary);
}

.dossier__ov-bar {
  margin-top: var(--sp-3);
  height: 4px;
  border-radius: var(--r-pill);
  background: var(--hairline);
  overflow: hidden;
}

.dossier__ov-bar i {
  display: block;
  height: 100%;
  background: var(--status-teal);
}

.dossier__ov-live-actions {
  display: flex;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
}

.dossier__ov-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--status-teal);
}

.dossier__ov-dot--live {
  background: var(--status-teal);
}

.dossier__ov-dot--ok {
  background: var(--status-green);
}

.dossier__ov-dot--err {
  background: var(--status-red);
}

.dossier__ov-system-list {
  list-style: none;
  margin: var(--sp-3) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.dossier__ov-system-row {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  font-size: var(--fs-caption-1);
}

.dossier__ov-system-label {
  color: var(--text-primary);
  font-weight: 500;
}

.dossier__ov-system-hint {
  color: var(--text-tertiary);
}

.dossier__ov-link {
  display: inline-block;
  margin-top: var(--sp-3);
  font-size: var(--fs-caption-1);
  color: var(--text-secondary);
}

.dossier__ov-link:hover {
  color: var(--text-primary);
}

@media (max-width: 1279px) {
  .dossier__ov-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
