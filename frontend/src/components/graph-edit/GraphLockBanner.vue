<script setup lang="ts">
/**
 * Sperrzustand des Graphen als sichtbares Band (#1808, Entscheid 3; ADR-0022 §6).
 *
 * Ein gesperrter Graph darf nicht bearbeitet werden — der Maintainer-Entscheid
 * sagt aber ausdruecklich, dass das sichtbar und begruendet sein muss, nicht nur
 * als deaktivierter Knopf. Deshalb stehen hier Grund, Liste der nutzenden
 * Laeufe und der Ausweg im Text — und der Ausweg ist ein Knopf: „Kopie
 * anlegen“ startet den Auftrag und zeigt seinen Zustand. Der Auftrag laeuft im
 * Hintergrund, also behauptet die Ansicht nie eine fertige Kopie, bevor der
 * Server `completed` gemeldet hat; erst dann nennt sie das Zielprojekt.
 *
 * `unknown` und `error` gelten als gesperrt: solange der Zustand nicht bekannt
 * ist, wird nicht geschrieben (`useGraphLock` sperrt vorsorglich).
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { GraphEditTestId } from '@/contracts/testIds'
import type { GraphLockStatus, GraphLock } from '@/composables/graph-library/useGraphLock'
import type { GraphDuplicate } from '@/composables/graph-library/useGraphDuplicate'
import type { GraphDuplicateErrorKind } from '@/composables/graph-library/useGraphDuplicate'
import type { GraphDuplicateRun, GraphLockUser } from '@/contracts/graphEditContract'

/** Fehlerart -> i18n-Schluessel. Wie `GraphEditErrors`, nur fuer den Kopierpfad. */
const DUPLICATE_ERROR_KEY: Partial<Record<GraphDuplicateErrorKind, string>> = {
  build_running: 'buildRunning',
  migration_running: 'migrationRunning',
  unavailable: 'unavailable',
  invalid_input: 'invalidInput',
}

const props = defineProps<{
  status: GraphLockStatus
  usedBy: GraphLockUser[]
  loading: boolean
  error: string | null
  /** Der Auftrag, mit dem der Ausweg verbunden ist. Ohne ihn bleibt nur der Text. */
  duplicate?: GraphDuplicate
  /** Vorschlag fuer den Namen der Kopie (Anzeigename des Graphen). */
  duplicateName?: string
}>()

const emit = defineEmits<{ reload: []; duplicate: [name: string] }>()

const { t } = useI18n()

const blocked = computed(() => props.status !== 'editable')
// `error` hat keinen eigenen Kurzsatz; dafuer steht `checkFailed` bereit.
const badge = computed(() =>
  props.status === 'error' ? t('views.graphEdit.lock.checkFailed') : t(`views.graphEdit.lock.${props.status}`),
)

const dup = computed(() => props.duplicate ?? null)
const canDuplicate = computed(() => props.status === 'locked' && dup.value !== null)
const dupStatus = computed<GraphDuplicateRun['status'] | null>(() => dup.value?.status.value ?? null)
const dupCompleted = computed(() => dup.value?.completed.value === true)
const dupFailed = computed(() => dup.value?.failed.value === true)
const dupSettled = computed(() => dupCompleted.value || dupFailed.value)
const dupBusy = computed(() => dup.value?.busy.value === true)
const dupPercent = computed(() => dup.value?.progress.value.percent ?? 0)
const dupMessage = computed(() => dup.value?.progress.value.message ?? '')
const dupError = computed(() => dup.value?.error.value ?? null)
const copyProjectId = computed(() => dup.value?.copyProjectId.value ?? null)

/**
 * Der Name steht im Feld, damit die Kopie benennbar bleibt und der Vertrag
 * (Name pflicht) erfuellt ist. Er schlaegt nicht bei jedem Rendern um: nur wenn
 * sich der Vorschlag aendert und der Nutzer nichts getippt hat.
 */
const nameDraft = ref('')
const touched = ref(false)
watch(
  () => props.duplicateName ?? '',
  (value) => {
    if (!touched.value) nameDraft.value = value
  },
  { immediate: true },
)

function onNameInput(event: Event): void {
  touched.value = true
  nameDraft.value = (event.target as HTMLInputElement).value
}

function submitDuplicate(): void {
  const name = nameDraft.value.trim()
  // Der Vertrag verlangt einen Namen; ein leerer Auftrag würde scheitern.
  if (!name || !canDuplicate.value || dupBusy.value) return
  emit('duplicate', name)
}
</script>

<template>
  <div
    class="glb"
    :class="{ 'glb--blocked': blocked, 'glb--failed': status === 'error' }"
    :data-testid="GraphEditTestId.lockBanner"
    :role="status === 'error' ? 'alert' : 'status'"
  >
    <span class="glb__mark" aria-hidden="true">{{ blocked ? '🔒' : '✎' }}</span>
    <span class="glb__body">
      <strong
        class="glb__badge"
        :data-testid="GraphEditTestId.lockBadge"
        :aria-busy="loading ? 'true' : undefined"
      >
        {{ badge }}
      </strong>
      <span v-if="status === 'locked'" class="glb__text">{{ t('views.graphEdit.lock.locked') }}</span>
      <span v-if="status === 'error'" class="glb__text">
        {{ t('views.graphEdit.lock.checkFailed') }}
        <span v-if="error" class="glb__err">{{ error }}</span>
      </span>
      <span v-if="status === 'locked' && usedBy.length" class="glb__used">
        <span class="glb__usedlabel">{{ t('views.graphEdit.lock.usedBy') }}:</span>
        <span :data-testid="GraphEditTestId.lockUsedBy">
          {{ usedBy.map((user) => t('views.graphEdit.lock.simulation', { id: user.simulation_id })).join(', ') }}
        </span>
      </span>

      <!-- Der Zustand des Kopierauftrags. Fertig heisst „fertig“, nicht „läuft
           noch“: solange kein Endzustand da ist, gibt es hier keine Kopie. -->
      <span
        v-if="dupStatus"
        class="glb__copy"
        :data-testid="GraphEditTestId.duplicateState"
        :data-status="dupStatus"
      >
        <template v-if="dupCompleted">
          <RouterLink
            class="glb__copylink"
            :data-testid="GraphEditTestId.duplicateOpen"
            :to="{ name: 'GraphLibraryDetail', params: { projectId: copyProjectId } }"
          >
            {{ t('views.graphEdit.duplicate.done') }}
          </RouterLink>
        </template>
        <template v-else-if="dupFailed">
          {{ t('views.graphEdit.duplicate.failed') }}
          <span v-if="dupMessage" class="glb__err">{{ dupMessage }}</span>
        </template>
        <template v-else>
          <progress
            class="glb__bar"
            max="100"
            :value="dupPercent"
            :aria-label="t('views.graphEdit.duplicate.running')"
          />
          {{ t('views.graphEdit.duplicate.running') }}
          <span class="glb__percent">{{ dupPercent }}&nbsp;%</span>
          <span v-if="dupMessage" class="glb__err">{{ dupMessage }}</span>
        </template>
      </span>
      <span
        v-if="dupError"
        class="glb__err"
        role="alert"
        :data-testid="GraphEditTestId.duplicateError"
      >
        {{ t(`views.graphEdit.duplicate.error.${DUPLICATE_ERROR_KEY[dupError.kind] ?? 'other'}`) }}
        <span v-if="dupError.message" class="glb__errmsg">{{ dupError.message }}</span>
      </span>
    </span>
    <span class="glb__actions">
      <!-- Nur bei gesperrtem Graphen: das Duplizieren ist der Ausweg. Ohne
           gesicherten Zustand gibt es keinen Knopf, der ins Leere liefe. -->
      <template v-if="canDuplicate">
        <label class="glb__field">
          <span class="glb__fieldlabel">{{ t('views.graphEdit.duplicate.nameLabel') }}</span>
          <input
            class="glb__input"
            type="text"
            :value="nameDraft"
            :disabled="dupSettled"
            :data-testid="GraphEditTestId.duplicateName"
            @input="onNameInput"
          />
        </label>
        <button
          type="button"
          class="glb__btn"
          :disabled="dupBusy || dupSettled"
          :data-testid="GraphEditTestId.duplicateStart"
          @click="submitDuplicate"
        >
          {{ t('views.graphEdit.duplicate.start') }}
        </button>
      </template>
      <!-- Kein gesperrter Zustand: nur neu laden anbieten. -->
      <button
        v-if="status === 'error' || status === 'unknown'"
        type="button"
        class="glb__btn"
        data-testid="graph-edit-lock-reload"
        @click="emit('reload')"
      >
        {{ t('views.graphEdit.lock.reload') }}
      </button>
    </span>
  </div>
</template>

<style scoped>
.glb {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
  font-size: 13px;
}

.glb--blocked {
  background: var(--warn-soft);
  color: var(--warn);
}

.glb--failed {
  background: var(--err-soft);
  color: var(--err);
}

.glb__mark {
  font-size: 14px;
  line-height: 1.4;
}

.glb__body {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  flex: 1;
  min-width: 0;
}

.glb__badge {
  font-size: 13px;
  font-weight: 650;
}

.glb__text,
.glb__used {
  color: var(--fg);
  font-weight: 400;
}

.glb__usedlabel {
  color: var(--fg2);
}

.glb__err {
  font-family: var(--ag-font-mono);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.glb__copy {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
  width: 100%;
  color: var(--fg);
}

.glb__bar {
  width: 90px;
  height: 8px;
  accent-color: var(--acc);
}

.glb__percent {
  color: var(--fg2);
  font-variant-numeric: tabular-nums;
}

.glb__copylink {
  color: var(--acc-text);
  font-weight: 600;
  text-decoration: underline;
}

.glb__errmsg {
  color: var(--fg);
  font-family: var(--ag-font-mono);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.glb__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 8px;
  flex-shrink: 0;
}

.glb__field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.glb__fieldlabel {
  color: var(--fg2);
  font-size: 11.5px;
}

.glb__input {
  height: 28px;
  max-width: 190px;
  padding: 0 8px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--field);
  color: var(--fg);
  font: inherit;
  font-size: 12.5px;
}

.glb__btn {
  height: 28px;
  padding: 0 12px;
  border: none;
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.glb__btn:disabled {
  color: var(--fg2);
  cursor: not-allowed;
}

.glb__btn:focus-visible,
.glb__input:focus-visible,
.glb__copylink:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}
</style>
