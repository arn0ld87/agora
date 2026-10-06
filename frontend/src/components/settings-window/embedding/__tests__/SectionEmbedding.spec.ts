import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

import SectionEmbedding from '../../sections/SectionEmbedding.vue'

const ViewStub = defineComponent({
  name: 'EmbeddingConfigurationsView',
  props: { embedded: { type: Boolean, default: false } },
  template: '<div data-testid="embedding-view" />',
})

describe('SectionEmbedding', () => {
  it('zeigt oben den #1417-Hinweis mit Verweis und bettet die Ansicht ohne Kopf ein', () => {
    const wrapper = mount(SectionEmbedding, {
      global: { stubs: { EmbeddingConfigurationsView: ViewStub } },
    })
    const notice = wrapper.get('[data-testid="embedding-1417-notice"]')
    expect(notice.text()).toContain('views.settingsWindow.embedding.notice')
    const link = notice.get('a')
    expect(link.text()).toBe('#1417')
    expect(link.attributes('href')).toContain('/issues/1417')
    // Hinweis steht vor der eingebetteten Ansicht (DOM-Reihenfolge = Fokusreihenfolge).
    const html = wrapper.html()
    expect(html.indexOf('embedding-1417-notice')).toBeLessThan(html.indexOf('embedding-view'))
    expect(wrapper.findComponent(ViewStub).props('embedded')).toBe(true)
    expect(wrapper.find('h1').exists()).toBe(false)
  })
})
