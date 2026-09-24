import { describe, expect, it } from 'vitest'

import taskStatusJsonSchema from '../../../../schemas/task-status-response.schema.json'

import { TaskStatusResponseSchema, parseTaskStatusResponse } from '../taskStatusContract'

/**
 * Issue #1466 — `GET /api/graph/task/<task_id>` und `GET /api/graph/tasks`
 * serialisierten bislang `Task.to_dict()` handgeschrieben, ohne Gegenstueck
 * in `schemas/` und ohne Zod-Drift-Check. Dieser Test bewacht die
 * Feld-Parität sowie das exakte Wire-Format von `Task.to_dict()`.
 */
describe('taskStatusContract mirrors backend task_status_contract', () => {
  it('TaskStatusResponseSchema declares exactly the fields of task-status-response.schema.json', () => {
    const backendFields = Object.keys(taskStatusJsonSchema.properties).sort()
    const zodFields = Object.keys(TaskStatusResponseSchema.shape).sort()
    expect(zodFields).toEqual(backendFields)
  })

  it('parses a pending task (Task.to_dict() default shape)', () => {
    const payload = {
      task_id: '11111111-1111-4111-8111-111111111111',
      task_type: 'graph_build',
      status: 'pending',
      created_at: '2026-09-24T10:00:00',
      updated_at: '2026-09-24T10:00:00',
      progress: 0,
      message: '',
      message_key: null,
      progress_detail: {},
      result: null,
      error: null,
      metadata: {},
    }
    expect(TaskStatusResponseSchema.safeParse(payload).success).toBe(true)
  })

  it('parses a completed task with message_key (#1458)', () => {
    const payload = {
      task_id: '11111111-1111-4111-8111-111111111111',
      task_type: 'graph_build',
      status: 'completed',
      created_at: '2026-09-24T10:00:00',
      updated_at: '2026-09-24T10:05:00',
      progress: 100,
      message: 'Task completed',
      message_key: 'task.completed',
      progress_detail: {},
      result: { ok: true },
      error: null,
      metadata: {},
    }
    const parsed = parseTaskStatusResponse(payload)
    expect(parsed).not.toBeNull()
    expect(parsed?.status).toBe('completed')
    expect(parsed?.message_key).toBe('task.completed')
  })

  it('rejects an unknown status value', () => {
    const payload = {
      task_id: 't1',
      task_type: 'graph_build',
      status: 'unknown_status',
      created_at: '2026-09-24T10:00:00',
      updated_at: '2026-09-24T10:00:00',
      progress: 0,
      message: '',
    }
    expect(TaskStatusResponseSchema.safeParse(payload).success).toBe(false)
  })

  it('rejects an unexpected field (strict)', () => {
    const payload = {
      task_id: 't1',
      task_type: 'graph_build',
      status: 'pending',
      created_at: '2026-09-24T10:00:00',
      updated_at: '2026-09-24T10:00:00',
      progress: 0,
      message: '',
      unexpected_field: true,
    }
    expect(TaskStatusResponseSchema.safeParse(payload).success).toBe(false)
  })
})
