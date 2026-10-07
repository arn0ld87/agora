import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

const SUPPORTED = [
  { provider_id: 'openai', display_name: 'OpenAI' },
  { provider_id: 'google', display_name: 'Google Gemini' },
  { provider_id: 'minimax', display_name: 'MiniMax' },
  { provider_id: 'ollama_cloud', display_name: 'Ollama (Cloud)' },
  { provider_id: 'bedrock', display_name: 'Amazon Bedrock' },
]

const auth = vi.hoisted(() => ({
  activeWorkspaceId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  roles: { 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa': 'owner' },
}))
vi.mock('../../../store/auth', () => ({ useAuthStore: () => auth }))

const api = vi.hoisted(() => ({
  list: vi.fn(),
  save: vi.fn(),
  remove: vi.fn(),
}))
vi.mock('../../../api/workspaceProviderCredentials', () => ({
  listWorkspaceProviderCredentials: api.list,
  saveWorkspaceProviderCredential: api.save,
  deleteWorkspaceProviderCredential: api.remove,
}))

import WorkspaceProviderKeysView from '../WorkspaceProviderKeysView.vue'

beforeEach(() => {
  auth.roles['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'] = 'owner'
  api.list.mockReset().mockResolvedValue({ items: [], total: 0, supported_providers: SUPPORTED })
  api.save.mockReset()
  api.remove.mockReset()
})

describe('WorkspaceProviderKeysView', () => {
  it('eingebettet: kein eigenes h1, Anbieter bleiben sichtbar', async () => {
    const wrapper = mount(WorkspaceProviderKeysView, { props: { embedded: true } })
    await flushPromises()
    expect(wrapper.find('h1').exists()).toBe(false)
    expect(wrapper.text()).toContain('OpenAI')
    const standalone = mount(WorkspaceProviderKeysView)
    await flushPromises()
    expect(standalone.find('h1').exists()).toBe(true)
  })

  it('sends the entered key once and clears it without displaying it', async () => {
    api.save.mockResolvedValue({ provider_id: 'openai', configured: true, updated_at: null })
    const wrapper = mount(WorkspaceProviderKeysView)
    await flushPromises()

    await wrapper.find('#workspace-key-openai').setValue('private-api-key')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(api.save).toHaveBeenCalledWith('openai', 'private-api-key')
    expect((wrapper.find('#workspace-key-openai').element as HTMLInputElement).value).toBe('')
    expect(wrapper.text()).not.toContain('private-api-key')
    expect(wrapper.text()).toContain('auth.workspaceProviderKeys.configured')
  })

  it('renders every provider the backend offers', async () => {
    const wrapper = mount(WorkspaceProviderKeysView)
    await flushPromises()

    for (const provider of SUPPORTED) {
      expect(wrapper.find(`#workspace-key-${provider.provider_id}`).exists()).toBe(true)
      expect(wrapper.text()).toContain(provider.display_name)
    }
  })

  it('does not offer key editing to a viewer', async () => {
    auth.roles['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'] = 'viewer'
    const wrapper = mount(WorkspaceProviderKeysView)
    await flushPromises()

    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('auth.workspaceProviderKeys.readOnly')
    expect(api.save).not.toHaveBeenCalled()
  })
})
