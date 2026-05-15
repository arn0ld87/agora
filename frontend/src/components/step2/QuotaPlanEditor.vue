<script setup lang="ts">
/**
 * QuotaPlanEditor — Persona-Quota-Plan-UI, extrahiert aus Step2EnvSetup.vue.
 *
 * Sub-Slice 31 (Phase 1, Refs #203): Isoliert den Quoten-Editor-Block
 * aus Sub-Slice 20c/24, um Step2EnvSetup.vue von 1817 auf < 1500 LOC
 * zu bringen.
 *
 * Props/Emits sind Zod-typisiert via personaQuotaContract.ts.
 * Keine hartkodierten UI-Strings — alle Labels via vue-i18n.
 */
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  PersonaQuotaPlanSchema,
  buildQuotaPlanFromEntries,
} from '../../contracts/personaQuotaContract'
import type { PersonaQuotaPlan } from '../../contracts/personaQuotaContract'
import Button from '@/components/v4/forms/Button.vue'

const { t } = useI18n()

// ---------------------------------------------------------------------------
// Props & Emits
// ---------------------------------------------------------------------------

interface QuotaEntry {
  id: string
  segment: string
  count: number
}

interface Props {
  /** Whether the quota plan feature is enabled (checkbox toggle). */
  enabled: boolean
  /** Current list of quota entries (ordered, stable id per entry). */
  entries: QuotaEntry[]
  /** Disable all editing controls (e.g. while a prepare is running). */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
})

const emit = defineEmits<{
  /** Emitted when the enabled checkbox is toggled. */
  'update:enabled': [value: boolean]
  /** Emitted when the entries list changes (add, remove, or value edit). */
  'update:entries': [entries: QuotaEntry[]]
}>()

// ---------------------------------------------------------------------------
// Internal state — local working copies to avoid mutating props directly
// ---------------------------------------------------------------------------

const localEnabled = ref(props.enabled)
const localEntries = ref<QuotaEntry[]>(props.entries.map((e) => ({ ...e })))

// Sync prop → local when parent changes programmatically.
watch(
  () => props.enabled,
  (v) => { localEnabled.value = v },
)
watch(
  () => props.entries,
  (v) => { localEntries.value = v.map((e) => ({ ...e })) },
  { deep: true },
)

// Sync local → parent.
watch(localEnabled, (v) => emit('update:enabled', v))
watch(localEntries, (v) => emit('update:entries', v.map((e) => ({ ...e }))), { deep: true })

// ---------------------------------------------------------------------------
// Computed
// ---------------------------------------------------------------------------

const quotaTotal = computed(() =>
  localEntries.value.reduce((acc, e) => acc + (Number(e.count) || 0), 0),
)

/**
 * Client-seitige Validierung via PersonaQuotaPlanSchema.
 * Gibt leeren String zurück wenn valide, sonst erste Issue-Message.
 */
const validationError = computed((): string => {
  if (!localEnabled.value) return ''
  const plan: PersonaQuotaPlan = buildQuotaPlanFromEntries(localEntries.value)
  const result = PersonaQuotaPlanSchema.safeParse(plan)
  if (result.success) return ''
  const issue = result.error.issues[0]
  return issue?.message ?? t('step2.quota.invalid')
})

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

let _counter = 0
function _newEntryId(): string {
  _counter += 1
  return `q_${Date.now()}_${_counter}`
}

function addSegment(): void {
  localEntries.value = [
    ...localEntries.value,
    { id: _newEntryId(), segment: '', count: 5 },
  ]
}

function removeSegment(idx: number): void {
  const next = [...localEntries.value]
  next.splice(idx, 1)
  localEntries.value = next
}

function onToggleChange(event: Event): void {
  const target = event.target
  if (target instanceof HTMLInputElement) {
    localEnabled.value = target.checked
  }
}
</script>

<template>
  <div class="quota-editor">
    <!-- Toggle checkbox -->
    <label class="quota-toggle">
      <input
        type="checkbox"
        :checked="localEnabled"
        :disabled="disabled"
        @change="onToggleChange($event)"
      />
      <span>{{ t('step2.quota.toggle') }}</span>
    </label>

    <!-- Hint: disabled state -->
    <p v-if="!localEnabled" class="hint">{{ t('step2.quota.hintOff') }}</p>

    <!-- Quota plan editor -->
    <div v-if="localEnabled" class="quota-plan">
      <p class="hint">{{ t('step2.quota.hintOn') }}</p>

      <div
        v-for="(entry, idx) in localEntries"
        :key="entry.id"
        class="quota-row"
      >
        <input
          type="text"
          v-model.trim="localEntries[idx].segment"
          :placeholder="t('step2.quota.segmentPlaceholder')"
          :disabled="disabled"
          class="quota-segment"
          :aria-label="t('step2.quota.segmentPlaceholder')"
        />
        <input
          type="number"
          v-model.number="localEntries[idx].count"
          min="1"
          max="200"
          :disabled="disabled"
          class="quota-count"
          :aria-label="t('step2.quota.total', { count: entry.count })"
        />
        <Button
          variant="ghost"
          :disabled="disabled"
          @click="removeSegment(idx)"
        >−</Button>
      </div>

      <!-- Footer: add button + running total -->
      <div class="quota-row">
        <Button
          variant="ghost"
          :disabled="disabled"
          @click="addSegment"
        >{{ t('step2.quota.addSegment') }}</Button>
        <span class="meta">{{ t('step2.quota.total', { count: quotaTotal }) }}</span>
      </div>

      <!-- Validation error -->
      <p
        v-if="validationError"
        class="hint quota-error"
        role="alert"
      >
        {{ validationError }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.quota-editor {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.quota-toggle {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg);
  cursor: pointer;
}

.quota-plan {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.quota-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.quota-segment {
  flex: 1;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  font-family: var(--ff-mono);
  font-size: var(--fs-14);
  padding: 4px 0;
  color: var(--fg);
  outline: none;
}
.quota-segment:focus { border-bottom-color: var(--accent); }

.quota-count {
  width: 70px;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  font-family: var(--ff-mono);
  font-size: var(--fs-14);
  padding: 4px 0;
  color: var(--fg);
  outline: none;
  text-align: right;
}
.quota-count:focus { border-bottom-color: var(--accent); }

.hint {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  margin: 0;
}

.quota-error {
  color: var(--color-err, #d73a49);
}

.meta {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}

/* Design v3 quota editor. */
.quota-toggle,
.quota-segment,
.quota-count,
.hint,
.meta {
  font-family: var(--font-sans, var(--ff-sans));
  letter-spacing: 0;
  text-transform: none;
}
.quota-toggle {
  color: var(--text-primary, var(--fg));
}
.quota-segment,
.quota-count {
  background: var(--surface-elevated, transparent);
  border: 1px solid var(--hairline, var(--rule-strong));
  border-radius: var(--r-5, var(--r-1));
  color: var(--text-primary, var(--fg));
  padding: 7px 10px;
}
.quota-segment:focus,
.quota-count:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring, var(--accent-soft));
}
.hint,
.meta {
  color: var(--text-secondary, var(--fg-muted));
}
.quota-error {
  color: var(--status-red, var(--color-err, #d73a49));
}
</style>
