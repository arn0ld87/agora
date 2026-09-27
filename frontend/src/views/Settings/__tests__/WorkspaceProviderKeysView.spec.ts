import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

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
  api.list.mockReset().mockResolvedValue({ items: [], total: 0 })
  api.save.mockReset()
  api.remove.mockReset()
})

describe('WorkspaceProviderKeysView', () => {
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

  it('does not offer key editing to a viewer', async () => {
    auth.roles['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'] = 'viewer'
    const wrapper = mount(WorkspaceProviderKeysView)
    await flushPromises()

    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('auth.workspaceProviderKeys.readOnly')
    expect(api.save).not.toHaveBeenCalled()
  })
})
