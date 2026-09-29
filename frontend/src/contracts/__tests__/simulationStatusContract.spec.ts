/**
 * Der Zod-Spiegel muss die echte Antwort von `GET /api/simulation/<id>`
 * strikt parsen und die Felder aus #1713 kennen.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  RunnerStatusSchema,
  SimulationStatusResponseSchema,
} from '../simulationStatusContract'

const backendPayload = {
  simulation_id: 'sim_446625a756cc',
  project_id: 'proj_a1b2c3d4e5f6',
  graph_id: 'graph_9',
  enable_twitter: true,
  enable_reddit: true,
  status: 'completed',
  entities_count: 12,
  profiles_count: 12,
  entity_types: ['Person', 'Organisation'],
  config_generated: true,
  config_reasoning: 'Begruendung',
  current_round: 10,
  twitter_status: 'completed',
  reddit_status: 'completed',
  created_at: '2026-09-28T10:00:00',
  updated_at: '2026-09-28T10:30:00',
  branch_depth: 0,
  branch_name: null,
  error: null,
  persona_floor: null,
  root_simulation_id: null,
  source_simulation_id: null,
  run_instructions: null,
  runner_status: 'completed',
  interview_env_alive: true,
}

const schemaPath = resolve(
  __dirname,
  '../../../../schemas/simulation-status-response.schema.json',
)

describe('simulationStatusContract', () => {
  it('parst die vollstaendige Backend-Antwort strikt', () => {
    const parsed = SimulationStatusResponseSchema.parse(backendPayload)

    expect(parsed.status).toBe('completed')
    expect(parsed.runner_status).toBe('completed')
    expect(parsed.interview_env_alive).toBe(true)
  })

  it('weist ein unbekanntes Feld ab', () => {
    const result = SimulationStatusResponseSchema.safeParse({
      ...backendPayload,
      unerwartet: 1,
    })
    expect(result.success).toBe(false)
  })

  it('verlangt interview_env_alive', () => {
    const { interview_env_alive: _omit, ...rest } = backendPayload
    expect(SimulationStatusResponseSchema.safeParse(rest).success).toBe(false)
  })

  it('spiegelt Felder, Pflichtfelder und runner_status-Werte des JSON-Schemas', () => {
    const schema = JSON.parse(readFileSync(schemaPath, 'utf-8')) as {
      properties: Record<string, { anyOf?: Array<{ enum?: string[] }> }>
      required: string[]
    }

    const zodKeys = Object.keys(SimulationStatusResponseSchema.shape).sort()
    expect(zodKeys).toEqual(Object.keys(schema.properties).sort())

    const zodRequired = Object.entries(SimulationStatusResponseSchema.shape)
      .filter(([, field]) => !field.isOptional())
      .map(([key]) => key)
      .sort()
    expect(zodRequired).toEqual([...schema.required].sort())

    const runnerEnum = schema.properties.runner_status.anyOf?.find((v) => v.enum)?.enum ?? []
    expect([...RunnerStatusSchema.options].sort()).toEqual([...runnerEnum].sort())
  })
})
