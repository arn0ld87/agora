/**
 * DropdownMenu + DropdownMenuItem — API-Kompatibilitäts-Tests
 * Slice UI-G · 2026-05-15 (angepasst für Slice FE-Redesign-1 reka-ui)
 *
 * Selektor-Anpassungen nach reka-ui-Migration:
 * - Panel rendert via DropdownMenuPortal in document.body, daher
 *   `document.querySelector('.dm-panel')` statt `wrapper.find('.dm-panel')`.
 * - DropdownMenuItem benötigt DropdownMenuRoot-Kontext (reka-ui-Pflicht),
 *   Tests 6-9 mounten daher via Host-Wrapper mit DropdownMenu.
 * - Test 9 prüft aria-disabled statt HTML-disabled (reka-ui-Konvention:
 *   aria-disabled für Focus-Trap-Kompatibilität, nicht HTML disabled).
 */

import { describe, it, expect, beforeEach } from 'vitest'
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
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('Test 1: Panel ist initial geschlossen', () => {
    const wrapper = mount(DropdownMenu, {
      attachTo: document.body,
      slots: {
        trigger: '<button>Open</button>',
        default: '<div data-testid="content">x</div>',
      },
    })

    // Portal rendert in document.body — document.querySelector statt wrapper.find
    expect(document.querySelector('.dm-panel')).toBeNull()
    expect(document.querySelector('[data-testid="content"]')).toBeNull()
    wrapper.unmount()
  })

  it('Test 2: Trigger-Slot bekommt toggle + isOpen als Slot-Props', async () => {
    // Mit as-child übernimmt reka-ui das Click-Handling auf dem Trigger-Button.
    // Der Consumer-Button darf daher kein eigenes @click="toggle" haben —
    // sonst wird isOpen doppelt getoggelt. isOpen als Slot-Prop reflektiert
    // reka-ui's internen Open-State via v-model:open.
    const Host = buildHost({
      trigger: '<button data-testid="trigger">{{ isOpen ? "OPEN" : "ZU" }}</button>',
      menu: '<div data-testid="panel-content">Inhalt</div>',
    })

    const wrapper = mount(Host, { attachTo: document.body })
    expect(wrapper.find('[data-testid="trigger"]').text()).toBe('ZU')

    await wrapper.find('[data-testid="trigger"]').trigger('click')
    await nextTick()

    expect(wrapper.find('[data-testid="trigger"]').text()).toBe('OPEN')
    // Panel rendert in Portal → document.querySelector
    expect(document.querySelector('[data-testid="panel-content"]')).not.toBeNull()
    wrapper.unmount()
  })

  it('Test 3: align=start setzt entsprechende Panel-Klasse', async () => {
    const wrapper = mount(DropdownMenu, {
      attachTo: document.body,
      props: { align: 'start' },
      slots: {
        trigger: '<button>Open</button>',
        default: '<div>x</div>',
      },
    })

    // Öffnen über exposed-API
    wrapper.vm.open()
    await nextTick()

    // Panel rendert in Portal → document.querySelector
    expect(document.querySelector('.dm-panel--align-start')).not.toBeNull()
    expect(document.querySelector('.dm-panel--align-end')).toBeNull()
    wrapper.unmount()
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
    // Panel rendert in Portal → document.querySelector
    expect(document.querySelector('.dm-panel')).not.toBeNull()

    // reka-ui handelt ESC intern — dispatchEvent auf document
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await nextTick()

    expect(wrapper.vm.isOpen).toBe(false)
    wrapper.unmount()
  })

  it('Test 5: Panel kann via close() programmatisch geschlossen werden', async () => {
    // Outside-Click wird von reka-ui DismissableLayer intern gehandhabt
    // (pointerdown outside → dismiss). In jsdom ist dieses Verhalten nicht
    // testbar, da watchEffect-isClient-Check reka-ui-seitig greift.
    // Die Intention "Panel kann geschlossen werden" ist durch exposed close()
    // und ESC (Test 4) abgedeckt — reka-ui's own tests decken DismissableLayer ab.
    const wrapper = mount(DropdownMenu, {
      attachTo: document.body,
      slots: {
        trigger: '<button>Open</button>',
        default: '<div>x</div>',
      },
    })

    wrapper.vm.open()
    await nextTick()
    expect(document.querySelector('.dm-panel')).not.toBeNull()

    wrapper.vm.close()
    await nextTick()
    expect(wrapper.vm.isOpen).toBe(false)
    wrapper.unmount()
  })
})

describe('DropdownMenuItem', () => {
  // DropdownMenuItem benötigt nach reka-ui-Migration einen DropdownMenuRoot-Kontext.
  // Tests mounten daher immer via DropdownMenu-Host.

  function mountItemInMenu(itemTemplate: string) {
    const Host = defineComponent({
      components: { DropdownMenu, DropdownMenuItem },
      template: `
        <DropdownMenu ref="menu">
          <template #trigger>
            <!-- as-child: reka-ui übernimmt Click-Handling -->
            <button data-testid="trigger">Aktionen</button>
          </template>
          ${itemTemplate}
        </DropdownMenu>
      `,
    })
    const wrapper = mount(Host, { attachTo: document.body })
    return wrapper
  }

  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('Test 6: Default-Mount rendert role=menuitem', async () => {
    const wrapper = mountItemInMenu(
      '<DropdownMenuItem data-testid="item">Bearbeiten</DropdownMenuItem>',
    )
    // Öffnen um Items zu sehen (Panel im Portal)
    await wrapper.find('[data-testid="trigger"]').trigger('click')
    await nextTick()

    // reka-ui MenuItemImpl setzt role="menuitem"
    const item = document.querySelector('[data-testid="item"]')
    expect(item?.getAttribute('role')).toBe('menuitem')
    // CSS-Klassen bleiben erhalten
    expect(item?.classList.contains('dmi-root')).toBe(true)
    expect(item?.classList.contains('dmi-root--default')).toBe(true)
    expect(item?.textContent?.trim()).toBe('Bearbeiten')
    wrapper.unmount()
  })

  it('Test 7: variant=danger trägt danger-Klasse', async () => {
    const wrapper = mountItemInMenu(
      '<DropdownMenuItem data-testid="item" variant="danger">Löschen</DropdownMenuItem>',
    )
    await wrapper.find('[data-testid="trigger"]').trigger('click')
    await nextTick()

    const item = document.querySelector('[data-testid="item"]')
    expect(item?.classList.contains('dmi-root--danger')).toBe(true)
    wrapper.unmount()
  })

  it('Test 8: Click emittiert select-Event', async () => {
    let selectFired = false
    const Host = defineComponent({
      components: { DropdownMenu, DropdownMenuItem },
      setup() {
        function onSelect() { selectFired = true }
        return { onSelect }
      },
      template: `
        <DropdownMenu>
          <template #trigger>
            <button data-testid="trigger">Open</button>
          </template>
          <DropdownMenuItem data-testid="item" @select="onSelect">X</DropdownMenuItem>
        </DropdownMenu>
      `,
    })
    const wrapper = mount(Host, { attachTo: document.body })
    await wrapper.find('[data-testid="trigger"]').trigger('click')
    await nextTick()

    const item = document.querySelector('[data-testid="item"]') as HTMLElement
    item?.click()
    await nextTick()

    expect(selectFired).toBe(true)
    wrapper.unmount()
  })

  it('Test 9: disabled verhindert select-Emit und trägt aria-disabled', async () => {
    let selectFired = false
    const Host = defineComponent({
      components: { DropdownMenu, DropdownMenuItem },
      setup() {
        function onSelect() { selectFired = true }
        return { onSelect }
      },
      template: `
        <DropdownMenu>
          <template #trigger>
            <button data-testid="trigger">Open</button>
          </template>
          <DropdownMenuItem data-testid="item" :disabled="true" @select="onSelect">X</DropdownMenuItem>
        </DropdownMenu>
      `,
    })
    const wrapper = mount(Host, { attachTo: document.body })
    await wrapper.find('[data-testid="trigger"]').trigger('click')
    await nextTick()

    const item = document.querySelector('[data-testid="item"]') as HTMLElement
    // reka-ui setzt aria-disabled="true" (nicht HTML disabled) für Focus-Trap-Kompatibilität
    expect(item?.getAttribute('aria-disabled')).toBe('true')

    item?.click()
    await nextTick()
    // reka-ui blockiert handleSelect bei disabled=true → kein Emit
    expect(selectFired).toBe(false)
    wrapper.unmount()
  })
})
