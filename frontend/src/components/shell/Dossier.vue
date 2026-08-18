<template>
  <div class="dossier" :data-testid="DossierTestId.root" :role="props.object ? 'region' : undefined" :aria-labelledby="props.object ? 'dossier-title' : undefined">
    <p v-if="!props.object" class="dossier__empty">{{ t('shelf.dossier.emptyHint') }}</p>

    <template v-else>
      <div class="dossier__head">
        <div class="dossier__head-main">
          <div class="dossier__kicker">{{ SHELF_KIND_TAG[props.object.kind] }}</div>
          <h2 id="dossier-title" class="dossier__title" :data-testid="DossierTestId.title">{{ props.object.title }}</h2>
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

      <div class="dossier__kpis" :data-testid="DossierTestId.kpis">
        <div class="dossier__kpi">
          <div class="dossier__kpi-value dossier__kpi-value--text">{{ props.object.statusLine }}</div>
          <div class="dossier__kpi-label">{{ t('common.status') }}</div>
        </div>
        <div class="dossier__kpi">
          <div class="dossier__kpi-value">{{ formatUpdatedAt(props.object.updatedAt) }}</div>
          <div class="dossier__kpi-label">{{ t('common.time') }}</div>
        </div>
        <div class="dossier__kpi">
          <div class="dossier__kpi-value dossier__kpi-value--mono">{{ props.object.metaId }}</div>
          <!-- "ID" ist ein technisches Kuerzel ohne shelf.*-Entsprechung (siehe Bericht) -->
          <div class="dossier__kpi-label">ID</div>
        </div>
      </div>

      <!-- Bestandteile: erst beim Auswaehlen nachgeladen. Ein Bericht
           zeigt seine Abschnitte, ein Graph seine Kennzahlen. Sorten
           ohne Detail-Endpunkt zeigen hier nichts, statt ein leeres
           Geruest zu behaupten. -->
      <section v-if="detail" class="dossier__parts" :data-testid="DossierTestId.parts">
        <p v-if="detail.summary" class="dossier__detail-summary">{{ detail.summary }}</p>
        <ul v-if="detail.parts.length" class="dossier__part-list">
          <li v-for="part in detail.parts" :key="part.title" class="dossier__part" :data-testid="DossierTestId.part">
            <span class="dossier__part-title">{{ part.title }}</span>
            <span class="dossier__part-desc">{{ part.description }}</span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { DossierTestId } from '../../contracts/testIds'
import { SHELF_KIND_TAG, type ShelfObject } from '../../types/shelf'
import { useCancelAction } from './useCancelAction'
import { useObjectDetail } from '../../composables/useObjectDetail'

/**
 * Dossier.vue — rechte Spalte (Block B3).
 *
 * Zeigt das gewaehlte ShelfObject. Die „Bestandteile"-Liste und der
 * Red-Team-Kasten aus der Design-Vorlage (01-ablage.html) fehlen hier
 * bewusst: ShelfObject (types/shelf.ts) traegt dafuer keine Felder,
 * und useShelf.ts liefert keine solche Daten — sie liessen sich nur
 * durch Fabrikation fuellen. Siehe Bericht fuer die volle Begruendung.
 */

const props = defineProps<{ object: ShelfObject | null }>()

// Details werden erst beim Auswaehlen geholt, nicht fuer jede Zeile.
const { detail } = useObjectDetail(computed(() => props.object))

const { t, locale } = useI18n()
const router = useRouter()
const cancelAction = useCancelAction()

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
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const sameDay = d.toDateString() === new Date().toDateString()
  return sameDay
    ? d.toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString(locale.value, { day: '2-digit', month: '2-digit' })
}
</script>

<style scoped>
.dossier {
  padding: var(--sp-6) var(--sp-7);
  min-width: 0;
  overflow-y: auto;
  height: 100%;
}

.dossier__empty {
  margin: 0;
  font-size: var(--fs-callout);
  color: var(--text-tertiary);
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
  margin: var(--sp-5) 0 0;
  border-top: 1px solid var(--hairline);
  border-bottom: 1px solid var(--hairline);
}

.dossier__kpi {
  flex: 1;
  min-width: 0;
  padding: 12px 16px;
  border-left: 1px solid var(--hairline);
}

.dossier__kpi:first-child {
  border-left: 0;
  padding-left: 0;
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
  margin-top: 3px;
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
</style>
