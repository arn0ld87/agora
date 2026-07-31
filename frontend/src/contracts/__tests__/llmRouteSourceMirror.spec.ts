/**
 * Issue #901 — Frontend-Spiegel von `StageLLMRoute.ai_model_ref_source`.
 *
 * `LlmRouteSchema` ist `.strict()`. Das ist Absicht (siehe Kopfkommentar in
 * `llmRoute.ts`): das Frontend liest Routing-Defaults aus dem Backend zurück
 * und soll bemerken, wenn der Vertrag auseinanderläuft. Genau deshalb bricht
 * ein neues Backend-Feld den Lesepfad hart, solange der Spiegel fehlt — der
 * Fehler zeigt sich dann nicht im Contract-Test, sondern erst beim Nutzer.
 *
 * Diese Datei pinnt beide Richtungen: das neue Feld muss akzeptiert werden,
 * und Bestandsrouten ohne das Feld müssen weiterhin parsen.
 */

import { describe, it, expect } from 'vitest'

import { LlmRouteSchema } from '../llmRoute'
import { AiModelSourceSchema } from '../aiModelRef'

const BASE_ROUTE = {
  stage: 'report_generation',
  provider_id: 'conn-1',
  model: 'qwen2.5:32b',
  provider_options: {},
} as const

describe('#901 · LlmRouteSchema spiegelt die AiModelRef-Herkunft', () => {
  it.each(AiModelSourceSchema.options)('akzeptiert ai_model_ref_source=%s', (source) => {
    const parsed = LlmRouteSchema.safeParse({
      ...BASE_ROUTE,
      ai_model_ref_source: source,
      // provider_fallback verlangt backendseitig einen Grund; der Spiegel
      // transportiert ihn mit, validiert die Kopplung aber nicht nach —
      // SSoT dafür bleibt der Pydantic-Validator.
      fallback_reason: source === 'fallback' ? 'Primaermodell nicht erreichbar' : null,
    })

    expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true)
    if (parsed.success) {
      expect(parsed.data.ai_model_ref_source).toBe(source)
    }
  })

  it('parst Bestandsrouten ohne das Feld weiterhin', () => {
    const parsed = LlmRouteSchema.safeParse(BASE_ROUTE)

    expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true)
    if (parsed.success) {
      expect(parsed.data.ai_model_ref_source ?? null).toBeNull()
    }
  })

  it('akzeptiert explizites null (Backend serialisiert das Feld immer mit)', () => {
    const parsed = LlmRouteSchema.safeParse({
      ...BASE_ROUTE,
      ai_model_ref_source: null,
      fallback_reason: null,
    })

    expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true)
  })

  it('lehnt einen unbekannten Herkunftswert ab', () => {
    const parsed = LlmRouteSchema.safeParse({
      ...BASE_ROUTE,
      ai_model_ref_source: 'erfunden',
    })

    expect(parsed.success).toBe(false)
  })

  it('bleibt strict — unbekannte Felder fallen weiterhin auf', () => {
    const parsed = LlmRouteSchema.safeParse({
      ...BASE_ROUTE,
      voellig_neues_backend_feld: 'x',
    })

    expect(
      parsed.success,
      'strict() ist der Drift-Melder dieses Vertrags und darf nicht aufgeweicht werden',
    ).toBe(false)
  })
})
