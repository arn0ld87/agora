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
  type AiModelPickerMode,
  type AiModelRef,
  type AiModelRefInput,
  type AiModelSource,
} from '@/contracts/aiModelRef'

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

/**
 * Mock-Daten fuer Slice 5.1. Wird in 5.2 durch `useAvailableModels()`
 * ersetzt. Tests koennen `options`-Prop setzen, um eigene Listen
 * einzuspeisen.
 */
const MOCK_OPTIONS: readonly AiModelRefInput[] = [
  {
    provider_connection_id: 'conn-ollama-local',
    provider_kind: 'ollama',
    display_name: 'Ollama (lokal)',
    model_id: 'qwen2.5:14b',
    context_window: 32768,
    capabilities: ['chat', 'streaming', 'tool_calling'],
    status: 'available',
    is_workspace_default: true,
    local_or_cloud: 'local',
  },
  {
    provider_connection_id: 'conn-ollama-local',
    provider_kind: 'ollama',
    display_name: 'Ollama (lokal)',
    model_id: 'llama3.1:8b',
    context_window: 131072,
    capabilities: ['chat', 'streaming', 'tool_calling'],
    status: 'available',
    local_or_cloud: 'local',
  },
  {
    provider_connection_id: 'conn-ollama-cloud',
    provider_kind: 'ollama_cloud',
    display_name: 'Ollama Cloud',
    model_id: 'gpt-oss:20b-cloud',
    context_window: 65536,
    capabilities: ['chat', 'streaming', 'tool_calling'],
    status: 'available',
    local_or_cloud: 'cloud',
  },
  {
    provider_connection_id: 'conn-openai',
    provider_kind: 'openai',
    display_name: 'OpenAI',
    model_id: 'gpt-4o',
    context_window: 128000,
    capabilities: ['chat', 'streaming', 'tool_calling', 'vision', 'json_schema'],
    status: 'available',
    local_or_cloud: 'cloud',
  },
  {
    provider_connection_id: 'conn-openai',
    provider_kind: 'openai',
    display_name: 'OpenAI',
    model_id: 'gpt-4o-mini',
    context_window: 128000,
    capabilities: ['chat', 'streaming', 'tool_calling', 'vision', 'json_schema'],
    status: 'available',
    local_or_cloud: 'cloud',
  },
  {
    provider_connection_id: 'conn-gemini',
    provider_kind: 'gemini',
    display_name: 'Google Gemini',
    model_id: 'gemini-2.5-pro',
    context_window: 1048576,
    capabilities: ['chat', 'streaming', 'vision', 'json_schema', 'reasoning'],
    status: 'unavailable',
    local_or_cloud: 'cloud',
  },
  {
    provider_connection_id: 'conn-anthropic',
    provider_kind: 'anthropic',
    display_name: 'Anthropic',
    model_id: 'claude-sonnet-4-5',
    context_window: 200000,
    capabilities: ['chat', 'streaming', 'tool_calling', 'vision', 'reasoning'],
    status: 'degraded',
    local_or_cloud: 'cloud',
  },
]

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
  const base = props.options ?? MOCK_OPTIONS
  const required = REQUIRED_CAPABILITY[props.mode]
  return base
    .filter((o) => {
      if (!o.capabilities.includes(required)) return false
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

/** Provider-Gruppen (fuer ComboboxGroup). */
const providerGroups = computed(() => {
  const groups = new Map<string, AiModelRefInput[]>()
  for (const o of filteredOptions.value) {
    const key = o.display_name
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(o)
  }
  return Array.from(groups.entries()).map(([name, items]) => ({ name, items }))
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

defineExpose({ filteredOptions, providerGroups, selectedId, selectedLabel })
</script>

<template>
  <div class="ai-model-picker" :data-mode="mode" :data-disabled="disabled || undefined">
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
            />

            <ComboboxEmpty class="ai-model-picker__empty">
              {{ emptyText }}
            </ComboboxEmpty>

            <ComboboxGroup
              v-for="group in providerGroups"
              :key="group.name"
              class="ai-model-picker__group"
            >
              <ComboboxLabel class="ai-model-picker__group-label">
                {{ group.name }}
              </ComboboxLabel>

              <ComboboxItem
                v-for="item in group.items"
                :key="aiModelItemId(item)"
                :value="aiModelItemId(item)"
                :disabled="isDisabled(item)"
                :text-value="`${item.display_name} ${item.model_id}`"
                class="ai-model-picker__item"
                :data-status="item.status"
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
  display: block;
  width: 100%;
  position: relative;
}
.ai-model-picker__anchor {
  display: flex;
  align-items: center;
  border: 1px solid var(--hairline, #d1d5db);
  border-radius: var(--r-4, 8px);
  background: var(--surface-elevated, #fff);
  min-height: var(--ctl-h-md, 36px);
  padding: 0 8px;
}
.ai-model-picker__anchor:focus-within {
  border-color: var(--accent, #2563eb);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent, #2563eb) 20%, transparent);
}
.ai-model-picker__input {
  flex: 1 1 auto;
  border: 0;
  background: transparent;
  font-family: var(--font-sans);
  font-size: var(--fs-callout, 14px);
  color: var(--text-primary);
  padding: 6px 4px;
  outline: none;
}
.ai-model-picker__trigger {
  flex: 0 0 auto;
  border: 0;
  background: transparent;
  cursor: pointer;
  padding: 4px 6px;
  color: var(--text-muted, #6b7280);
}
.ai-model-picker__content {
  background: var(--surface-elevated, #fff);
  border: 1px solid var(--hairline, #d1d5db);
  border-radius: var(--r-4, 8px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  z-index: 50;
}
.ai-model-picker__viewport {
  max-height: 320px;
  overflow-y: auto;
  padding: 4px;
}
.ai-model-picker__search {
  width: calc(100% - 8px);
  margin: 4px;
  padding: 6px 8px;
  border: 1px solid var(--hairline, #d1d5db);
  border-radius: var(--r-4, 6px);
  font-size: var(--fs-callout, 14px);
  outline: none;
}
.ai-model-picker__search:focus {
  border-color: var(--accent, #2563eb);
}
.ai-model-picker__empty {
  padding: 12px;
  text-align: center;
  color: var(--text-muted, #6b7280);
  font-size: var(--fs-footnote, 13px);
}
.ai-model-picker__group {
  margin-top: 4px;
}
.ai-model-picker__group-label {
  padding: 4px 8px;
  font-size: var(--fs-footnote, 12px);
  font-weight: 600;
  color: var(--text-muted, #6b7280);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.ai-model-picker__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  border-radius: var(--r-4, 6px);
  cursor: pointer;
  user-select: none;
  outline: none;
}
.ai-model-picker__item[data-highlighted] {
  background: color-mix(in srgb, var(--accent, #2563eb) 12%, transparent);
}
.ai-model-picker__item[data-disabled] {
  opacity: 0.5;
  cursor: not-allowed;
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
.ai-model-picker__status-dot[data-tone='green'] { background: #16a34a; }
.ai-model-picker__status-dot[data-tone='orange'] { background: #d97706; }
.ai-model-picker__status-dot[data-tone='red'] { background: #dc2626; }
.ai-model-picker__status-dot[data-tone='gray'] { background: #9ca3af; }
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
}
.ai-model-picker__badge {
  display: inline-block;
  padding: 1px 6px;
  font-size: 11px;
  background: var(--surface-subtle, #f3f4f6);
  color: var(--text-muted, #6b7280);
  border-radius: 999px;
  font-weight: 500;
}
.ai-model-picker__badge--default {
  background: color-mix(in srgb, var(--accent, #2563eb) 15%, transparent);
  color: var(--accent, #2563eb);
}
.ai-model-picker__badge--warn {
  background: #fef3c7;
  color: #b45309;
}
.ai-model-picker__badge--err {
  background: #fee2e2;
  color: #b91c1c;
}
.ai-model-picker__indicator {
  flex: 0 0 auto;
  color: var(--accent, #2563eb);
  margin-left: 8px;
}
</style>
