import { describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'

const hoisted = await vi.hoisted(async () => {
  const { ref: r } = await import('vue')
  return { posts: r<unknown[]>([]), error: r<string | null>(null), reload: vi.fn(), options: [] as unknown[] }
})

vi.mock('@/composables/run/simulation/useRunFeed', () => ({
  useRunFeed: (_id: unknown, options: unknown) => {
    hoisted.options.push(options)
    return { posts: hoisted.posts, error: hoisted.error, reload: hoisted.reload }
  },
}))

import { useEvidenceFeedCheck } from '../useEvidenceFeedCheck'

function setup(wantedInitial: boolean) {
  const wanted = ref(wantedInitial)
  const scope = effectScope()
  const check = scope.run(() => useEvidenceFeedCheck(() => 'sim_1', () => wanted.value))!
  return { wanted, check, scope }
}

describe('useEvidenceFeedCheck', () => {
  it('lädt nichts, solange kein Feed-Beleg gewählt ist, und startet keinen Strom', async () => {
    hoisted.reload.mockReset().mockResolvedValue(undefined)
    hoisted.options.length = 0
    const { check } = setup(false)
    await flushPromises()
    expect(hoisted.reload).not.toHaveBeenCalled()
    expect(hoisted.options[0]).toEqual({ immediate: false })
    expect(check.state.value).toBe('idle')
  })

  it('lädt einmal bei Bedarf: loading, dann ready', async () => {
    let done!: () => void
    hoisted.error.value = null
    hoisted.reload.mockReset().mockReturnValue(new Promise<void>((r) => (done = r)))
    const { wanted, check } = setup(false)
    wanted.value = true
    await flushPromises()
    expect(check.state.value).toBe('loading')
    done()
    await flushPromises()
    expect(check.state.value).toBe('ready')
    wanted.value = false
    wanted.value = true
    await flushPromises()
    expect(hoisted.reload).toHaveBeenCalledTimes(1)
  })

  it('Ladefehler wird als error gemeldet', async () => {
    hoisted.reload.mockReset().mockResolvedValue(undefined)
    hoisted.error.value = 'twitter: Netzwerkfehler'
    const { check } = setup(true)
    await flushPromises()
    expect(check.state.value).toBe('error')
    hoisted.error.value = null
  })
})
