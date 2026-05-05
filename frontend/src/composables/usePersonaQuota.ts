/**
 * usePersonaQuota — Composable for Persona-Quota-Plan state, persistence and
 * validation (Sub-Slice 35, Refs #203).
 *
 * Extracted from Step2EnvSetup.vue to reduce that component below 800 LOC.
 *
 * Owns:
 *   - useQuotaPlan ref (toggle)
 *   - quotaEntries ref (ordered list of { id, segment, count })
 *   - quotaTotal computed
 *   - quotaValidationError computed (Zod, i18n via injected t())
 *   - addQuotaSegment / removeQuotaSegment actions
 *   - LocalStorage persistence (key: agora.quotaPlan — unchanged, no migration)
 *
 * The `t` function is injected as a parameter so this composable can be
 * tested without a vue-i18n provider.
 */

import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  PersonaQuotaPlanSchema,
  buildQuotaPlanFromEntries,
} from '../contracts/personaQuotaContract'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const STORAGE_QUOTA_PLAN = 'agora.quotaPlan'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface QuotaEntry {
  id: string
  segment: string
  count: number
}

export interface UsePersonaQuotaOptions {
  /** vue-i18n t() injected so tests don't need a provider. */
  t: (key: string) => string
}

export interface UsePersonaQuotaReturn {
  /** Whether the quota plan feature is enabled. */
  useQuotaPlan: Ref<boolean>
  /** Ordered list of quota entries. */
  quotaEntries: Ref<QuotaEntry[]>
  /** Sum of all entry counts. */
  quotaTotal: ComputedRef<number>
  /**
   * Empty string when plan is valid (or disabled).
   * First Zod issue message when invalid.
   */
  quotaValidationError: ComputedRef<string>
  /** Append a new empty entry with a unique id. */
  addQuotaSegment: () => void
  /** Remove entry at given index. */
  removeQuotaSegment: (idx: number) => void
}

// ---------------------------------------------------------------------------
// Private helpers (module-scoped so they don't pollute the return value)
// ---------------------------------------------------------------------------

let _counter = 0

function _newEntryId(): string {
  _counter += 1
  return `q_${Date.now()}_${_counter}`
}

function _loadQuotaEntries(): QuotaEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_QUOTA_PLAN)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (
      !parsed ||
      typeof parsed !== 'object' ||
      !('targets' in parsed) ||
      typeof (parsed as Record<string, unknown>).targets !== 'object' ||
      (parsed as Record<string, unknown>).targets === null
    ) {
      return []
    }
    const targets = (parsed as { targets: Record<string, unknown> }).targets
    return Object.entries(targets).map(([segment, count]) => ({
      id: _newEntryId(),
      segment,
      count: Number(count) || 1,
    }))
  } catch {
    return []
  }
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function usePersonaQuota({ t }: UsePersonaQuotaOptions): UsePersonaQuotaReturn {
  // --- State ---

  const useQuotaPlan = ref<boolean>(false)
  const quotaEntries = ref<QuotaEntry[]>(_loadQuotaEntries())

  // --- Computed ---

  const quotaTotal = computed<number>(() =>
    quotaEntries.value.reduce((acc, e) => acc + (Number(e.count) || 0), 0),
  )

  const quotaValidationError = computed<string>(() => {
    if (!useQuotaPlan.value) return ''
    const plan = buildQuotaPlanFromEntries(quotaEntries.value)
    const result = PersonaQuotaPlanSchema.safeParse(plan)
    if (result.success) return ''
    const issue = result.error.issues[0]
    return issue?.message ?? t('step2.quota.invalid')
  })

  // --- LocalStorage persistence: save on every change ---

  watch(
    quotaEntries,
    (entries) => {
      const plan = buildQuotaPlanFromEntries(entries)
      localStorage.setItem(STORAGE_QUOTA_PLAN, JSON.stringify(plan))
    },
    { deep: true },
  )

  // --- Actions ---

  function addQuotaSegment(): void {
    quotaEntries.value = [
      ...quotaEntries.value,
      { id: _newEntryId(), segment: '', count: 5 },
    ]
  }

  function removeQuotaSegment(idx: number): void {
    const next = [...quotaEntries.value]
    next.splice(idx, 1)
    quotaEntries.value = next
  }

  return {
    useQuotaPlan,
    quotaEntries,
    quotaTotal,
    quotaValidationError,
    addQuotaSegment,
    removeQuotaSegment,
  }
}
