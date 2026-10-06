import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

import SectionPipeline from '../../sections/SectionPipeline.vue'
import { PIPELINE_SETTINGS_SECTIONS } from '../pipelineSections'
import { INTEGRATION_SETTINGS_SECTIONS } from '@/views/Settings/settingsSections'

const PanelStub = defineComponent({
  name: 'SettingsSectionPanel',
  props: { allowedSections: { type: Array, required: true } },
  template: '<div data-testid="panel-stub" />',
})

describe('SectionPipeline', () => {
  it('zeigt die Integrationen ohne budget', () => {
    expect(INTEGRATION_SETTINGS_SECTIONS).toContain('budget')
    expect(PIPELINE_SETTINGS_SECTIONS).not.toContain('budget')
    expect(PIPELINE_SETTINGS_SECTIONS).not.toContain('security')
    for (const id of ['ontology', 'hybrid_search', 'agent_tools', 'webtools', 'oasis']) {
      expect(PIPELINE_SETTINGS_SECTIONS).toContain(id)
    }
  })

  it('reicht die gefilterte Liste an das Panel und setzt kein eigenes h1', () => {
    const wrapper = mount(SectionPipeline, {
      global: { stubs: { SettingsSectionPanel: PanelStub } },
    })
    const panel = wrapper.findComponent(PanelStub)
    expect(panel.props('allowedSections')).toEqual(PIPELINE_SETTINGS_SECTIONS)
    expect(wrapper.find('h1').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('settingsWindow.placeholderTitle')
  })
})
