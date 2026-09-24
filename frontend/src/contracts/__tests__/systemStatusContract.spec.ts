import { describe, expect, it } from 'vitest'

import systemStatusNeo4jJsonSchema from '../../../../schemas/system-status-neo4j.schema.json'
import systemStatusDiskJsonSchema from '../../../../schemas/system-status-disk.schema.json'

import { SystemStatusDiskSchema, SystemStatusNeo4jSchema } from '../systemStatusContract'

/**
 * Issue #1466 — Neo4j- und Disk-Teilbaum von `/api/status` hatten bislang
 * kein Backend-Pydantic-Gegenstueck (nur Ollama/E2E waren seit #955/#1458
 * abgedeckt). Dieser Test schliesst die Luecke: jeder Feldname aus dem
 * generierten JSON-Schema muss im Zod-Spiegel vorkommen, und alle
 * beobachteten Wire-Format-Zweige muessen parsen.
 */
describe('systemStatusContract mirrors backend system_status_contract (Neo4j/Disk)', () => {
  it('SystemStatusNeo4jSchema declares exactly the fields of system-status-neo4j.schema.json', () => {
    const backendFields = Object.keys(systemStatusNeo4jJsonSchema.properties).sort()
    const zodFields = Object.keys(SystemStatusNeo4jSchema.shape).sort()
    expect(zodFields).toEqual(backendFields)
  })

  it('SystemStatusDiskSchema.uploads declares exactly the fields of $defs.SystemStatusDiskUploads', () => {
    const backendFields = Object.keys(
      systemStatusDiskJsonSchema.$defs.SystemStatusDiskUploads.properties
    ).sort()
    const uploadsShape = (SystemStatusDiskSchema.shape.uploads as { shape: Record<string, unknown> })
      .shape
    const zodFields = Object.keys(uploadsShape).sort()
    expect(zodFields).toEqual(backendFields)
  })

  it('parses the "no storage" Neo4j branch (is_connected/last_success_ts absent)', () => {
    const payload = {
      reachable: false,
      error: { code: 'unreachable' },
      uri: 'bolt://localhost:7687',
    }
    expect(SystemStatusNeo4jSchema.safeParse(payload).success).toBe(true)
  })

  it('parses the reachable Neo4j branch with all fields present', () => {
    const payload = {
      reachable: true,
      error: null,
      uri: 'bolt://localhost:7687',
      is_connected: true,
      last_success_ts: '2026-09-20T10:00:00+00:00',
    }
    expect(SystemStatusNeo4jSchema.safeParse(payload).success).toBe(true)
  })

  it('parses the unreachable Neo4j branch with structured error', () => {
    const payload = {
      reachable: false,
      error: { code: 'unexpected' },
      uri: 'bolt://localhost:7687',
      is_connected: false,
      last_success_ts: null,
    }
    expect(SystemStatusNeo4jSchema.safeParse(payload).success).toBe(true)
  })

  it('parses the disk success branch without an error field', () => {
    const payload = {
      uploads: {
        path: '/srv/agora/uploads',
        total_bytes: 1000,
        free_bytes: 500,
        used_pct: 50,
      },
    }
    expect(SystemStatusDiskSchema.safeParse(payload).success).toBe(true)
  })

  it('parses the disk failure branch with null metrics and structured error', () => {
    const payload = {
      uploads: {
        path: '/srv/agora/uploads',
        total_bytes: null,
        free_bytes: null,
        used_pct: null,
        error: { code: 'auth' },
      },
    }
    expect(SystemStatusDiskSchema.safeParse(payload).success).toBe(true)
  })
})
