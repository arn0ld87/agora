import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import GraphEditErrors from '../GraphEditErrors.vue'
import { GraphEditTestId } from '@/contracts/testIds'
import type { GraphEditFailure, GraphEditErrorKind } from '@/composables/graph-library/useGraphEdit'
import { makeI18n } from './fixtures'

const sim = { simulation_id: 'sim_1', status: 'completed', project_id: 'p1', branch_name: null }

function mountErrors(failure: GraphEditFailure | null) {
  return mount(GraphEditErrors, {
    props: { failure },
    global: { plugins: [makeI18n()] },
  })
}

const KIND_TESTID: Record<GraphEditErrorKind, string> = {
  locked: GraphEditTestId.errorLocked,
  conflict: GraphEditTestId.errorConflict,
  migration_running: GraphEditTestId.errorMigrationRunning,
  embedding_failed: GraphEditTestId.errorEmbeddingFailed,
  invalid_input: GraphEditTestId.errorInvalidInput,
  other: GraphEditTestId.errorOther,
}

describe('GraphEditErrors', () => {
  it('unterscheidet 409-Sperre, 409-Konflikt, Migration, 503 und Eingabefehler', () => {
    const kinds: GraphEditErrorKind[] = [
      'locked',
      'conflict',
      'migration_running',
      'embedding_failed',
      'invalid_input',
      'other',
    ]
    const texts = kinds.map((kind) => {
      const wrapper = mountErrors({ kind, message: `Servertext ${kind}`, usedBy: [] })
      expect(wrapper.get(`[data-testid="${KIND_TESTID[kind]}"]`).attributes('role')).toBe('alert')
      expect(wrapper.text()).toContain(`Servertext ${kind}`)
      return wrapper.get(`[data-testid="${KIND_TESTID[kind]}"]`).text()
    })
    // Jede Art traegt einen eigenen Text: 409 und 503 duerfen nicht gleich aussehen.
    expect(new Set(texts).size).toBe(kinds.length)
    expect(texts[0]).toContain('gesperrt')
    expect(texts[1]).toContain('kollidiert')
    expect(texts[3]).toContain('Einbettung')
  })

  it('nennt bei der Sperre die nutzenden Laeufe', () => {
    const wrapper = mountErrors({ kind: 'locked', message: 'gesperrt', usedBy: [sim] })
    expect(wrapper.text()).toContain('sim_1')
  })

  it('zeigt ohne Fehler nichts', () => {
    const wrapper = mountErrors(null)
    expect(wrapper.find(`[data-testid="${GraphEditTestId.error}"]`).exists()).toBe(false)
    expect(wrapper.text()).toBe('')
  })

  it('laesst den Hinweis wegklicken', async () => {
    const wrapper = mountErrors({ kind: 'other', message: 'kaputt', usedBy: [] })
    await wrapper.get(`[data-testid="${GraphEditTestId.error}"] button`).trigger('click')
    expect(wrapper.emitted('dismiss')).toHaveLength(1)
  })
})