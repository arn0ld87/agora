/**
 * DropdownMenu + DropdownMenuItem — Tests
 * Slice UI-G · 2026-05-15
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, defineComponent } from 'vue'
import DropdownMenu from '../DropdownMenu.vue'
import DropdownMenuItem from '../DropdownMenuItem.vue'

function buildHost(slots: { trigger: string; menu: string }) {
  return defineComponent({
    components: { DropdownMenu },
    template: `
      <DropdownMenu>
        <template #trigger="{ toggle, isOpen }">
          ${slots.trigger}
        </template>
        ${slots.menu}
      </DropdownMenu>
    `,
  })
}

describe('DropdownMenu', () => {
  it('Test 1: Panel ist initial geschlossen', () => {
    const wrapper = mount(DropdownMenu, {
      slots: {
        trigger: '<button>Open</button>',
        default: '<div data-testid="content">x</div>',
      },
    })

    expect(wrapper.find('.dm-panel').exists()).toBe(false)
    expect(wrapper.find('[data-testid="content"]').exists()).toBe(false)
  })

  it('Test 2: Trigger-Slot bekommt toggle + isOpen als Slot-Props', async () => {
    const Host = buildHost({
      trigger: '<button data-testid="trigger" @click="toggle">{{ isOpen ? "OPEN" : "ZU" }}</button>',
      menu: '<div data-testid="panel-content">Inhalt</div>',
    })

    const wrapper = mount(Host)
    expect(wrapper.find('[data-testid="trigger"]').text()).toBe('ZU')

    await wrapper.find('[data-testid="trigger"]').trigger('click')
    await nextTick()

    expect(wrapper.find('[data-testid="trigger"]').text()).toBe('OPEN')
    expect(wrapper.find('[data-testid="panel-content"]').exists()).toBe(true)
  })

  it('Test 3: align=start setzt entsprechende Panel-Klasse', async () => {
    const wrapper = mount(DropdownMenu, {
      props: { align: 'start' },
      slots: {
        trigger: '<button>Open</button>',
        default: '<div>x</div>',
      },
    })

    // Öffnen über exposed-API
    wrapper.vm.open()
    await nextTick()

    expect(wrapper.find('.dm-panel--align-start').exists()).toBe(true)
    expect(wrapper.find('.dm-panel--align-end').exists()).toBe(false)
  })

  it('Test 4: ESC-Taste schließt das Panel', async () => {
    const wrapper = mount(DropdownMenu, {
      attachTo: document.body,
      slots: {
        trigger: '<button>Open</button>',
        default: '<div>x</div>',
      },
    })

    wrapper.vm.open()
    await nextTick()
    expect(wrapper.find('.dm-panel').exists()).toBe(true)

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()

    expect(wrapper.find('.dm-panel').exists()).toBe(false)
    wrapper.unmount()
  })

  it('Test 5: Click außerhalb schließt das Panel', async () => {
    const wrapper = mount(DropdownMenu, {
      attachTo: document.body,
      slots: {
        trigger: '<button>Open</button>',
        default: '<div>x</div>',
      },
    })

    wrapper.vm.open()
    await nextTick()
    expect(wrapper.find('.dm-panel').exists()).toBe(true)

    // Click ein anderes Element außerhalb des Dropdown
    const outside = document.createElement('div')
    document.body.appendChild(outside)
    outside.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()

    expect(wrapper.find('.dm-panel').exists()).toBe(false)
    outside.remove()
    wrapper.unmount()
  })
})

describe('DropdownMenuItem', () => {
  it('Test 6: Default-Mount rendert role=menuitem', () => {
    const wrapper = mount(DropdownMenuItem, {
      slots: { default: 'Bearbeiten' },
    })

    const btn = wrapper.find('.dmi-root')
    expect(btn.attributes('role')).toBe('menuitem')
    expect(btn.classes()).toContain('dmi-root--default')
    expect(btn.text()).toBe('Bearbeiten')
  })

  it('Test 7: variant=danger trägt danger-Klasse', () => {
    const wrapper = mount(DropdownMenuItem, {
      props: { variant: 'danger' },
      slots: { default: 'Löschen' },
    })

    expect(wrapper.find('.dmi-root--danger').exists()).toBe(true)
  })

  it('Test 8: Click emittiert select-Event', async () => {
    const wrapper = mount(DropdownMenuItem, {
      slots: { default: 'X' },
    })

    await wrapper.find('.dmi-root').trigger('click')
    expect(wrapper.emitted('select')).toHaveLength(1)
  })

  it('Test 9: disabled blockiert select-Emit', async () => {
    const wrapper = mount(DropdownMenuItem, {
      props: { disabled: true },
      slots: { default: 'X' },
    })

    const btn = wrapper.find('.dmi-root')
    expect(btn.attributes('disabled')).toBeDefined()

    await btn.trigger('click')
    // Browser/JSDOM blockt click bei disabled-button → emit darf nicht feuern
    expect(wrapper.emitted('select')).toBeUndefined()
  })
})
