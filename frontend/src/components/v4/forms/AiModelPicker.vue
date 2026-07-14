<script setup lang="ts">
/**
 * AiModelPicker — einheitliche Modellauswahl (Slice 5.1).
 *
 * - Headless Combobox aus `reka-ui` (ComboboxRoot + ComboboxInput +
 *   ComboboxItem + ComboboxGroup + ComboboxEmpty + ComboboxViewport).
 * - Provider-Gruppierung via ComboboxGroup, alphabetisch sortiert.
 * - Capability-Badges, Status-Indicator (verfuegbar/degraded/unavailable),
 *   Workspace-Default-Stern.
 * - Suche ueber reka-ui ComboboxInput (eingebautes TextValue-Matching).
 * - Tastatur (Pfeile, Enter, Esc, Tab) und ARIA out-of-the-box von reka-ui.
 * - Mock-Daten ueber Prop `options` ueberschreibbar (fuer Tests).
 *
 * Slice 5.0+5.1: noch keine Store-Anbindung. In 5.2 wird die
 * `useAvailableModels()`-Datenquelle angebunden und die Mock-Liste
 * durch ProviderConnection-Discovery ersetzt.
 *
 * Master-Prompt §6.1-6.3, ADR-0009, docs/epics/onboarding-provider-unification/slice-5-subplan.md
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { AiModelPickerTestId as testIds } from '@/contracts/testIds'
import {
  ComboboxAnchor,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxGroup,
  ComboboxInput,
  ComboboxItem,
  ComboboxItemIndicator,
  ComboboxLabel,
  ComboboxPortal,
  ComboboxRoot,
  ComboboxTrigger,
  ComboboxViewport,
} from 'reka-ui'
import {
  aiModelItemId,
  parseAiModelItemId,
  type AiCapability,
  type AiModelStatus,
  type AiModelPickerMode,
  type AiModelRef,
  type AiModelRefInput,
  type AiModelSource,
} from '@/contracts/aiModelRef'
import { useAvailableModels } from '@/composables/useAvailableModels'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    modelValue?: AiModelRef | null
    mode?: AiModelPickerMode
    placeholder?: string
    disabled?: boolean
    allowWorkspaceDefault?: boolean
    capabilityFilter?: AiCapability
    options?: readonly AiModelRefInput[]
  }>(),
  {
    modelValue: null,
    mode: 'chat',
    placeholder: '',
    disabled: false,
    allowWorkspaceDefault: true,
    capabilityFilter: undefined,
    options: undefined,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: AiModelRef | null]
}>()

const { models: discoveredModels, loading, error, refresh: refreshDiscovery } = useAvailableModels()
const refresh = (): Promise<void> => refreshDiscovery({ force: true })

/** Required-Capability je mode (Master-Prompt §5.4). */
const REQUIRED_CAPABILITY: Record<AiModelPickerMode, AiCapability> = {
  chat: 'chat',
  embedding: 'embeddings',
}

/**
 * Gefilterte + sortierte Optionen:
 * - Capability-Filter (mode + optional capabilityFilter-Prop)
 * - Provider-Gruppen alphabetisch nach display_name
 * - innerhalb einer Gruppe: is_workspace_default zuerst, dann nach model_id
 *
 * Gemini-Review (PR #697, MEDIUM): "Provider-Gruppen alphabetisch
 * sicherstellen, nicht global nach is_workspace_default sortieren" — der
 * Default-Pin gilt jetzt **innerhalb** seiner Provider-Gruppe, nicht
 * quer durch alle Optionen. So bleibt die Provider-Reihenfolge
 * vorhersagbar und der Default ist trotzdem sichtbar vorne.
 */
const filteredOptions = computed<readonly AiModelRefInput[]>(() => {
  const base = props.options ?? discoveredModels.value
  const required = REQUIRED_CAPABILITY[props.mode]
  return base
    .filter((o) => {
      if (props.mode === 'chat') {
        // chat: 'unknown' gilt als geeignet — nur explizit 'unsupported' ausfiltern.
        if (o.unsupported_capabilities?.includes(required)) return false
      } else {
        // embedding: positive Capability verlangt (Backend setzt 'supported').
        if (!o.capabilities.includes(required)) return false
      }
      if (props.capabilityFilter && !o.capabilities.includes(props.capabilityFilter)) {
        return false
      }
      return true
    })
    .slice()
    .sort((a, b) => {
      // Innerhalb derselben Provider-Gruppe: Default zuerst, dann model_id.
      if (a.display_name === b.display_name) {
        if (a.is_workspace_default && !b.is_workspace_default) return -1
        if (!a.is_workspace_default && b.is_workspace_default) return 1
        return a.model_id.localeCompare(b.model_id)
      }
      // Provider-uebergreifend: strikt alphabetisch.
      return a.display_name.localeCompare(b.display_name)
    })
})

/**
 * Provider-Gruppen (fuer ComboboxGroup).
 *
 * Slice 5.6-Prep: `provider_connection_id` ist neu in der Group-Struktur
 * und wird als data-Provider-connection-id auf dem Group-Root
 * gerendert. E2E-Selektoren koennen damit gezielt auf eine
 * Provider-Gruppe zugreifen, ohne sich auf den (i18n-lokalisierbaren)
 * `name` verlassen zu muessen. Aenderungsgruende in 5.6: stable
 * Selektoren fuer Specs, unabhängig von Display-Namen.
 */
const providerGroups = computed(() => {
  const groups = new Map<string, { name: string; provider_connection_id: string; status: AiModelStatus; items: AiModelRefInput[] }>()
  for (const o of filteredOptions.value) {
    const key = o.provider_connection_id
    if (!groups.has(key)) {
      groups.set(key, {
        name: o.display_name,
        provider_connection_id: o.provider_connection_id,
        status: o.status,
        items: [],
      })
    }
    groups.get(key)!.items.push(o)
  }
  return Array.from(groups.values()).sort((left, right) => left.name.localeCompare(right.name))
})

/** Current selection als stable ID. */
const selectedId = computed(() => {
  if (!props.modelValue) return null
  return `${props.modelValue.provider_connection_id}\u0000${props.modelValue.model_id}`
})

/** Source-derivation: workspace-default | explicit | fallback. */
const deriveSource = (input: AiModelRefInput): AiModelSource => {
  if (input.is_workspace_default) return 'workspace-default'
  if (input.status === 'unavailable' || input.status === 'degraded') {
    return 'fallback'
  }
  return 'explicit'
}

const fallbackReason = (input: AiModelRefInput): string | undefined => {
  if (input.status === 'unavailable') return 'provider_offline'
  if (input.status === 'degraded') return 'provider_degraded'
  return undefined
}

function onUpdate(value: string | null | undefined): void {
  if (!value) {
    emit('update:modelValue', null)
    return
  }
  // Gemini-Review (PR #697, MEDIUM): defensive Validierung der Item-ID.
  // ComboboxItem kann bei externer Mutation eine ID ohne Separator liefern;
  // ein Wurf waere hier ein Runtime-Crash im Live-Run. Stattdessen: null
  // emittieren und mit console.warn auf das Problem hinweisen.
  const sep = value.indexOf('\u0000')
  if (sep < 0) {
    console.warn('[AiModelPicker] invalid item id, no separator:', value)
    emit('update:modelValue', null)
    return
  }
  const input = filteredOptions.value.find((o) => aiModelItemId(o) === value)
  if (!input) {
    // Unbekannte ID (z.B. Provider offline) — Auswahl beibehalten als fallback
    const parsed = parseAiModelItemId(value)
    emit('update:modelValue', {
      provider_connection_id: parsed.provider_connection_id,
      model_id: parsed.model_id,
      source: 'fallback',
      fallback_reason: 'unknown_provider',
    })
    return
  }
  const ref: AiModelRef = {
    provider_connection_id: input.provider_connection_id,
    model_id: input.model_id,
    source: deriveSource(input),
    ...(input.is_workspace_default ? {} : { capability_filter: REQUIRED_CAPABILITY[props.mode] }),
    ...(fallbackReason(input) ? { fallback_reason: fallbackReason(input) } : {}),
  }
  emit('update:modelValue', ref)
}

/** Anzeige-Label des aktuell ausgewaehlten Modells (fuer Trigger). */
const selectedLabel = computed(() => {
  if (!props.modelValue) return ''
  const found = filteredOptions.value.find(
    (o) => aiModelItemId(o) === selectedId.value,
  )
  if (found) return `${found.display_name} — ${found.model_id}`
  // Fallback: model_id reicht, wenn Provider offline
  return props.modelValue.model_id
})

const placeholderText = computed(
  () => props.placeholder || t('aiModelPicker.placeholder', 'Modell wählen …'),
)

const searchPlaceholder = computed(() =>
  t('aiModelPicker.searchPlaceholder', 'Modell suchen …'),
)

const emptyText = computed(() => t('aiModelPicker.empty', 'Keine Modelle verfügbar.'))

const workspaceDefaultLabel = computed(() =>
  t('aiModelPicker.workspaceDefault', 'Workspace-Standard'),
)

const localBadge = computed(() => t('aiModelPicker.badge.local', 'lokal'))
const cloudBadge = computed(() => t('aiModelPicker.badge.cloud', 'Cloud'))
const degradedBadge = computed(() => t('aiModelPicker.badge.degraded', 'eingeschränkt'))
const unavailableBadge = computed(() =>
  t('aiModelPicker.badge.unavailable', 'nicht verfügbar'),
)
const unsupportedBadge = computed(() => t('aiModelPicker.badge.unsupported', 'nicht unterstützt'))
const providerStatusLabel = (status: AiModelStatus): string =>
  t(`aiModelPicker.status.${status}`, status)

function statusTone(input: AiModelRefInput): 'green' | 'orange' | 'red' | 'gray' {
  switch (input.status) {
    case 'available':
      return 'green'
    case 'degraded':
    case 'invalid_credentials':
      return 'orange'
    case 'unavailable':
    case 'unsupported':
      return 'red'
    // Gemini-Review (PR #697, MEDIUM): expliziter Default-Branch, damit
    // ein neuer AiModelStatus-Wert (z. B. "unknown") nicht undefined
    // liefert und das CSS-Tone-Attribut leer bleibt.
    default:
      return 'gray'
  }
}

function isDisabled(input: AiModelRefInput): boolean {
  return input.status === 'unavailable' || input.status === 'unsupported'
}

defineExpose({ filteredOptions, providerGroups, selectedId, selectedLabel, loading, error, refresh, isDisabled })
</script>

<template>
  <div
    class="ai-model-picker"
    :data-mode="mode"
    :data-disabled="disabled || undefined"
    :data-testid="testIds.root"
  >
    <ComboboxRoot
      :model-value="selectedId ?? ''"
      :disabled="disabled"
      :open-on-focus="true"
      @update:model-value="onUpdate"
    >
      <ComboboxAnchor class="ai-model-picker__anchor">
        <ComboboxInput
          class="ai-model-picker__input"
          :placeholder="placeholderText"
          :disabled="disabled"
          :display-value="() => selectedLabel"
          autocomplete="off"
          spellcheck="false"
          :data-testid="testIds.input"
        />
        <ComboboxTrigger class="ai-model-picker__trigger" :aria-label="placeholderText" tabindex="-1">
          <span aria-hidden="true">▾</span>
        </ComboboxTrigger>
      </ComboboxAnchor>

      <ComboboxPortal>
        <ComboboxContent class="ai-model-picker__content">
          <ComboboxViewport class="ai-model-picker__viewport">
            <ComboboxInput
              class="ai-model-picker__search"
              :placeholder="searchPlaceholder"
              autocomplete="off"
              spellcheck="false"
              :data-testid="testIds.search"
            />

            <ComboboxEmpty class="ai-model-picker__empty" :data-testid="testIds.empty">
              {{ emptyText }}
            </ComboboxEmpty>

            <ComboboxGroup
              v-for="group in providerGroups"
              :key="group.name"
              class="ai-model-picker__group"
              :data-testid="testIds.group"
              :data-provider-connection-id="group.provider_connection_id"
            >
              <ComboboxLabel class="ai-model-picker__group-label">
                <span class="ai-model-picker__provider-name">{{ group.name }}</span>
                <span
                  class="ai-model-picker__provider-status"
                  :data-status="group.status"
                  role="status"
                >
                  {{ providerStatusLabel(group.status) }}
                </span>
              </ComboboxLabel>

              <ComboboxItem
                v-for="item in group.items"
                :key="aiModelItemId(item)"
                :value="aiModelItemId(item)"
                :disabled="isDisabled(item)"
                :text-value="`${item.display_name} ${item.model_id}`"
                class="ai-model-picker__item"
                :data-status="item.status"
                :data-testid="testIds.option"
                :data-provider-connection-id="item.provider_connection_id"
                :data-model-id="item.model_id"
              >
                <span class="ai-model-picker__item-row">
                  <span
                    class="ai-model-picker__status-dot"
                    :data-tone="statusTone(item)"
                    aria-hidden="true"
                  />
                  <span class="ai-model-picker__item-label">
                    <span class="ai-model-picker__model-name">{{ item.model_id }}</span>
                    <span v-if="item.is_workspace_default" class="ai-model-picker__badge ai-model-picker__badge--default">
                      {{ workspaceDefaultLabel }}
                    </span>
                    <span class="ai-model-picker__badge">
                      {{ item.local_or_cloud === 'local' ? localBadge : cloudBadge }}
                    </span>
                    <span
                      v-if="item.status === 'degraded'"
                      class="ai-model-picker__badge ai-model-picker__badge--warn"
                    >
                      {{ degradedBadge }}
                    </span>
                    <span
                      v-if="item.status === 'unavailable'"
                      class="ai-model-picker__badge ai-model-picker__badge--err"
                    >
                      {{ unavailableBadge }}
                    </span>
                    <span
                      v-if="item.status === 'unsupported'"
                      class="ai-model-picker__badge ai-model-picker__badge--err"
                    >
                      {{ unsupportedBadge }}
                    </span>
                  </span>
                </span>
                <ComboboxItemIndicator class="ai-model-picker__indicator">
                  <span aria-hidden="true">✓</span>
                </ComboboxItemIndicator>
              </ComboboxItem>
            </ComboboxGroup>
          </ComboboxViewport>
        </ComboboxContent>
      </ComboboxPortal>
    </ComboboxRoot>
  </div>
</template>

<style scoped>
.ai-model-picker {
  position: relative;
  display: block;
  inline-size: 100%;
  min-inline-size: 0;
}

.ai-model-picker__anchor {
  display: flex;
  align-items: center;
  min-block-size: max(var(--ctl-h-md, 36px), 44px);
  padding-inline: 8px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-5, 10px);
  background: var(--surface-elevated, #fff);
  box-shadow: var(--shadow-control);
  transition:
    border-color var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease),
    box-shadow var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease),
    background var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease);
}

.ai-model-picker__anchor:hover {
  border-color: var(--hairline-strong);
}

.ai-model-picker__anchor:focus-within {
  border-color: var(--accent);
  box-shadow:
    0 0 0 var(--v4-state-focus-ring-strong-width)
    var(--v4-state-focus-ring-strong),
    var(--shadow-control);
}

.ai-model-picker__input {
  flex: 1 1 auto;
  min-inline-size: 0;
  padding: 10px 6px;
  border: 0;
  background: transparent;
  font-family: var(--font-sans);
  font-size: var(--fs-callout, 14px);
  color: var(--text-primary);
  outline: none;
}

.ai-model-picker__input::placeholder,
.ai-model-picker__search::placeholder {
  color: var(--text-tertiary, var(--text-secondary));
}

.ai-model-picker__trigger {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  inline-size: 32px;
  block-size: 32px;
  padding: 0;
  border: 0;
  border-radius: var(--r-3, 6px);
  background: transparent;
  cursor: pointer;
  color: var(--text-secondary);
  transition:
    background var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease),
    color var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease);
}

.ai-model-picker__trigger:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.ai-model-picker__content {
  inline-size: var(--reka-combobox-trigger-width, min(360px, calc(100vw - 16px)));
  min-inline-size: min(300px, calc(100vw - 16px));
  max-inline-size: calc(100vw - 16px);
  background: var(--surface-elevated, #fff);
  border: 1px solid var(--hairline);
  border-radius: var(--r-6, 12px);
  box-shadow: var(--shadow-popover, var(--shadow-3));
  overflow: hidden;
  z-index: 50;
}

.ai-model-picker__viewport {
  max-block-size: min(360px, var(--reka-combobox-content-available-height, 360px));
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 6px;
  scrollbar-gutter: stable;
}

.ai-model-picker__search {
  inline-size: calc(100% - 8px);
  min-block-size: 40px;
  margin: 4px;
  padding: 8px 10px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-inset);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: var(--fs-callout, 14px);
  outline: none;
}

.ai-model-picker__search:focus-visible {
  border-color: var(--accent);
  box-shadow: 0 0 0 var(--v4-state-focus-ring-strong-width)
    var(--v4-state-focus-ring-strong);
}

.ai-model-picker__empty {
  padding: 20px 12px;
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--fs-footnote, 13px);
}

.ai-model-picker__group {
  margin-block-start: 4px;
  padding-block: 2px 4px;
  border-block-start: 1px solid var(--hairline);
}

.ai-model-picker__group:first-of-type {
  border-block-start: 0;
}

.ai-model-picker__group-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px 6px;
  font-size: var(--fs-footnote, 12px);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ai-model-picker__provider-name {
  min-inline-size: 0;
  overflow-wrap: anywhere;
}

.ai-model-picker__provider-status {
  flex: 0 0 auto;
  padding: 2px 7px;
  border-radius: var(--r-pill, 9999px);
  background: var(--status-gray-bg);
  color: var(--status-gray);
  font-size: 10px;
  font-weight: 650;
  line-height: 1.4;
  letter-spacing: 0.03em;
}

.ai-model-picker__provider-status[data-status='available'] {
  background: var(--status-green-bg);
  color: var(--status-green);
}

.ai-model-picker__provider-status[data-status='degraded'],
.ai-model-picker__provider-status[data-status='invalid_credentials'] {
  background: var(--status-orange-bg);
  color: var(--status-orange);
}

.ai-model-picker__provider-status[data-status='unavailable'],
.ai-model-picker__provider-status[data-status='unsupported'] {
  background: var(--status-red-bg);
  color: var(--status-red);
}

.ai-model-picker__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-block-size: 44px;
  padding: 8px 10px;
  border-radius: var(--r-4, 8px);
  cursor: pointer;
  user-select: none;
  outline: none;
  transition:
    background var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease),
    box-shadow var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease);
}

.ai-model-picker__item[data-highlighted] {
  background: var(--accent-tint-bg);
  box-shadow: inset 0 0 0 var(--v4-state-focus-ring-strong-width)
    var(--v4-state-focus-ring-strong);
}

.ai-model-picker__item[data-state='checked'] {
  background: var(--accent-tint-bg);
}

.ai-model-picker__item[data-disabled] {
  opacity: var(--v4-state-disabled-opacity, 0.45);
  cursor: var(--v4-state-disabled-cursor, not-allowed);
}

.ai-model-picker__item-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 auto;
  min-width: 0;
}
.ai-model-picker__status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: 0 0 auto;
}
.ai-model-picker__status-dot[data-tone='green'] { background: var(--status-green); }
.ai-model-picker__status-dot[data-tone='orange'] { background: var(--status-orange); }
.ai-model-picker__status-dot[data-tone='red'] { background: var(--status-red); }
.ai-model-picker__status-dot[data-tone='gray'] { background: var(--status-gray); }

.ai-model-picker__item-label {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  min-width: 0;
}
.ai-model-picker__model-name {
  font-size: var(--fs-callout, 14px);
  color: var(--text-primary);
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.ai-model-picker__badge {
  display: inline-block;
  padding: 1px 6px;
  font-size: 11px;
  background: var(--surface-inset);
  color: var(--text-secondary);
  border-radius: var(--r-pill, 9999px);
  font-weight: 500;
}

.ai-model-picker__badge--default {
  background: var(--accent-tint-bg);
  color: var(--accent-tint-text, var(--accent));
}

.ai-model-picker__badge--warn {
  background: var(--status-orange-bg);
  color: var(--status-orange);
}

.ai-model-picker__badge--err {
  background: var(--status-red-bg);
  color: var(--status-red);
}

.ai-model-picker__indicator {
  flex: 0 0 auto;
  color: var(--accent);
  margin-inline-start: 8px;
}

@media (max-width: 320px) {
  .ai-model-picker__content {
    min-inline-size: 0;
  }

  .ai-model-picker__viewport {
    padding: 4px;
  }

  .ai-model-picker__group-label,
  .ai-model-picker__item {
    padding-inline: 8px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ai-model-picker__anchor,
  .ai-model-picker__trigger,
  .ai-model-picker__item {
    transition: none;
  }
}
</style>
