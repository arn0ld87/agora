/**
 * DropdownMenu — reka-ui-spezifische Verhaltens-Tests
 *
 * Diese Specs verifizieren ARIA-Härte, die die alte Eigenbau-Variante NICHT
 * hatte: aria-haspopup, ARIA-Rollen + Orientation, aria-disabled, exposed-API.
 *
 * Die alte DropdownMenu.spec.ts bleibt als API-Kompatibilitäts-Smoke
 * bestehen (Public Slots + exposed-API darf nicht brechen).
 *
 * Slice FE-Redesign-1 · 2026-05-15
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, defineComponent } from 'vue'
import DropdownMenu from '../DropdownMenu.vue'
import DropdownMenuItem from '../DropdownMenuItem.vue'

function mountHost() {
  const Host = defineComponent({
    components: { DropdownMenu, DropdownMenuItem },
    template: `
      <DropdownMenu>
        <template #trigger="{ isOpen }">
          <!-- as-child: reka-ui übernimmt Click-Handling; kein @click="toggle" nötig.
               aria-haspopup="menu" + aria-expanded werden von reka-ui auf diesen Button gemergt. -->
          <button data-testid="trigger" :aria-expanded="isOpen">
            Aktionen
          </button>
        </template>
        <template #default="{ close }">
          <DropdownMenuItem data-testid="item-edit" @select="close">Bearbeiten</DropdownMenuItem>
          <DropdownMenuItem data-testid="item-copy" @select="close">Kopieren</DropdownMenuItem>
          <DropdownMenuItem data-testid="item-delete" variant="danger" @select="close">Löschen</DropdownMenuItem>
        </template>
      </DropdownMenu>
    `,
  })
  return mount(Host, { attachTo: document.body })
}

describe('DropdownMenu — reka-ui ARIA-Härte', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('Trigger trägt aria-haspopup="menu"', async () => {
    const wrapper = mountHost()
    // DropdownMenuTrigger (reka-ui) setzt aria-haspopup="menu" auf sein eigenes
    // Element. Es rendert ein <button> als Wrapper um den trigger-Slot.
    // Wir suchen das Element mit aria-haspopup="menu" im DOM — das ist der
    // DropdownMenuTrigger-Button, nicht der Consumer-Button im Slot.
    const triggerEl = document.querySelector('[aria-haspopup="menu"]')
    expect(triggerEl).not.toBeNull()
    expect(triggerEl?.getAttribute('aria-haspopup')).toBe('menu')
    wrapper.unmount()
  })

  it('Panel-Container trägt role="menu" und aria-orientation="vertical"', async () => {
    const wrapper = mountHost()
    await wrapper.find('[data-testid="trigger"]').trigger('click')
    await nextTick()

    // reka-ui MenuContentImpl setzt role="menu" + aria-orientation="vertical"
    const menu = document.querySelector('[role="menu"]')
    expect(menu).not.toBeNull()
    expect(menu?.getAttribute('aria-orientation')).toBe('vertical')
    wrapper.unmount()
  })

  it('Items tragen role="menuitem" und sind im DOM vorhanden', async () => {
    const wrapper = mountHost()
    await wrapper.find('[data-testid="trigger"]').trigger('click')
    await nextTick()

    // MenuItemImpl setzt role="menuitem" auf jedes Item
    const items = document.querySelectorAll('[role="menuitem"]')
    expect(items.length).toBe(3)
    wrapper.unmount()
  })

  it('Disabled-Item trägt aria-disabled="true"', async () => {
    const Host = defineComponent({
      components: { DropdownMenu, DropdownMenuItem },
      template: `
        <DropdownMenu>
          <template #trigger>
            <button data-testid="trigger">Aktionen</button>
          </template>
          <DropdownMenuItem data-testid="item-disabled" :disabled="true">Gesperrt</DropdownMenuItem>
        </DropdownMenu>
      `,
    })
    const wrapper = mount(Host, { attachTo: document.body })
    await wrapper.find('[data-testid="trigger"]').trigger('click')
    await nextTick()

    // MenuItemImpl setzt aria-disabled="true" (nicht HTML disabled-Attribut) bei disabled=true
    const item = document.querySelector('[data-testid="item-disabled"]')
    expect(item?.getAttribute('aria-disabled')).toBe('true')
    wrapper.unmount()
  })

  it('as-child: Trigger-Slot-Button trägt aria-haspopup, kein nested button', async () => {
    // Mit as-child rendert reka-ui kein eigenes <button> mehr —
    // aria-haspopup="menu" wird direkt auf den Consumer-Button gemergt.
    const wrapper = mountHost()
    const triggerBtn = document.querySelector('[data-testid="trigger"]') as HTMLElement | null
    expect(triggerBtn).not.toBeNull()
    // aria-haspopup="menu" muss auf dem Consumer-Button selbst stehen
    expect(triggerBtn?.getAttribute('aria-haspopup')).toBe('menu')
    // Kein nested button: Consumer-Button darf kein weiteres <button> enthalten
    const nestedButtons = triggerBtn?.querySelectorAll('button')
    expect(nestedButtons?.length ?? 0).toBe(0)
    wrapper.unmount()
  })

  it('Exposed API bleibt: open/close/toggle/isOpen', async () => {
    const wrapper = mount(DropdownMenu, {
      attachTo: document.body,
      slots: {
        trigger: '<button>x</button>',
        default: '<div data-testid="content">y</div>',
      },
    })

    expect(wrapper.vm.isOpen).toBe(false)
    wrapper.vm.open()
    await nextTick()
    expect(wrapper.vm.isOpen).toBe(true)
    wrapper.vm.close()
    await nextTick()
    expect(wrapper.vm.isOpen).toBe(false)
    wrapper.vm.toggle()
    await nextTick()
    expect(wrapper.vm.isOpen).toBe(true)
    wrapper.unmount()
  })
})
