import { describe, expect, it } from 'vitest'

import prepareStatusJsonSchema from '../../../../schemas/prepare-status-response.schema.json'

import { PrepareStatusResponseSchema } from '../prepareStatusContract'

/**
 * Issue #1174 (Codex-Finding 1) — die Prepare-Status-Antworten waren bis
 * dahin handgeschriebene Dicts ohne Gegenstueck in ``schemas/*.json`` und
 * ohne Zod-Drift-Check. Dieser Test schliesst die Luecke: jeder Feldname aus
 * dem generierten JSON-Schema muss im Zod-Spiegel vorkommen, und die drei
 * literalen Kurzschluesse muessen strikt parsen.
 */
describe('prepareStatusContract mirrors backend prepare_status_contract', () => {
  it('PrepareStatusResponseSchema declares exactly the fields of prepare-status-response.schema.json', () => {
    const backendFields = Object.keys(prepareStatusJsonSchema.properties).sort()
    const zodFields = Object.keys(PrepareStatusResponseSchema.shape).sort()
    expect(zodFields).toEqual(backendFields)
  })

  it('parses the Prepared-Shortcut payload (_already_prepared_response)', () => {
    const payload = {
      simulation_id: 'sim_0123456789ab',
      status: 'ready',
      message: 'Preparation already completed, no need to regenerate',
      message_key: 'prepare.already_completed',
      already_prepared: true,
      prepare_info: { status: 'ready' },
    }
    expect(PrepareStatusResponseSchema.safeParse(payload).success).toBe(true)
  })

  it('parses the Task-gestartet payload (_build_prepare_response) inkl. persona_target', () => {
    const payload = {
      simulation_id: 'sim_0123456789ab',
      task_id: 'task-1',
      run_id: 'run-1',
      status: 'preparing',
      message: 'Preparation task started; query progress via /api/simulation/prepare/status',
      message_key: 'prepare.task_started',
      already_prepared: false,
      expected_entities_count: 7,
      entity_types: ['Person'],
      persona_target: {
        entity_count: 7,
        persona_target_count: 50,
        floor_applied: true,
        floor: 50,
      },
    }
    expect(PrepareStatusResponseSchema.safeParse(payload).success).toBe(true)
  })

  it('parses the not_started payload from /prepare/status', () => {
    const payload = {
      simulation_id: 'sim_0123456789ab',
      status: 'not_started',
      progress: 0,
      message: 'Preparation not started yet, please call /api/simulation/prepare',
      message_key: 'prepare.not_started',
      already_prepared: false,
    }
    expect(PrepareStatusResponseSchema.safeParse(payload).success).toBe(true)
  })

  it('rejects an unknown field (strict)', () => {
    const payload = {
      simulation_id: 'sim_0123456789ab',
      status: 'ready',
      message: 'x',
      message_key: 'prepare.already_completed',
      already_prepared: true,
      unexpected_field: true,
    }
    expect(PrepareStatusResponseSchema.safeParse(payload).success).toBe(false)
  })

  it('rejects a message_key outside the three known values', () => {
    const payload = {
      simulation_id: 'sim_0123456789ab',
      status: 'ready',
      message: 'x',
      message_key: 'prepare.unbekannt',
      already_prepared: true,
    }
    expect(PrepareStatusResponseSchema.safeParse(payload).success).toBe(false)
  })
})
