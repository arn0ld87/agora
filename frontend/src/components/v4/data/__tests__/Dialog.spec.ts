/**
 * Dialog — Tests
 * Slice UI-E · 2026-05-15
 */

import { describe, it, expect, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import Dialog from '../Dialog.vue'

afterEach(() => {
  document.body.style.overflow = ''
})

describe('Dialog', () => {
  it('Test 1: modelValue=false rendert kein Panel', () => {
    const wrapper = mount(Dialog, {
      props: { modelValue: false, title: 'X' },
      slots: { default: 'Body' },
    })

    expect(wrapper.find('.dlg-overlay').exists()).toBe(false)
  })

  it('Test 2: modelValue=true rendert Panel mit Titel + Beschreibung + role=dialog', async () => {
    const wrapper = mount(Dialog, {
      props: { modelValue: true, title: 'Run löschen', description: 'Kann nicht rückgängig gemacht werden.' },
      slots: { default: 'Wirklich löschen?' },
      attachTo: document.body,
    })

    await nextTick()

    expect(wrapper.find('.dlg-overlay').exists()).toBe(true)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.find('[aria-modal="true"]').exists()).toBe(true)
    expect(wrapper.find('#dlg-title').text()).toBe('Run löschen')
    expect(wrapper.find('#dlg-desc').text()).toBe('Kann nicht rückgängig gemacht werden.')

    wrapper.unmount()
  })

  it('Test 3: footer-Slot wird gerendert', async () => {
    const wrapper = mount(Dialog, {
      props: { modelValue: true, title: 'X' },
      slots: {
        default: 'B',
        footer: '<button data-testid="confirm">OK</button>',
      },
      attachTo: document.body,
    })

    await nextTick()
    expect(wrapper.find('.dlg-footer').exists()).toBe(true)
    expect(wrapper.find('[data-testid="confirm"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('Test 4: Backdrop-Click emittiert update:modelValue=false (dismissible default)', async () => {
    const wrapper = mount(Dialog, {
      props: { modelValue: true, title: 'X' },
      slots: { default: 'B' },
      attachTo: document.body,
    })

    await nextTick()
    await wrapper.find('.dlg-overlay').trigger('click')

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('Test 5: dismissible=false blockiert Backdrop-Close', async () => {
    const wrapper = mount(Dialog, {
      props: { modelValue: true, dismissible: false, title: 'X' },
      slots: { default: 'B' },
      attachTo: document.body,
    })

    await nextTick()
    await wrapper.find('.dlg-overlay').trigger('click')

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    wrapper.unmount()
  })

  it('Test 6: ESC schließt das Dialog (dismissible=true)', async () => {
    const wrapper = mount(Dialog, {
      props: { modelValue: true, title: 'X' },
      slots: { default: '<button data-testid="btn">B</button>' },
      attachTo: document.body,
    })

    await nextTick()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
    wrapper.unmount()
  })

  it('Test 7: dismissible=false blockiert ESC-Close', async () => {
    const wrapper = mount(Dialog, {
      props: { modelValue: true, dismissible: false, title: 'X' },
      slots: { default: 'B' },
      attachTo: document.body,
    })

    await nextTick()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    wrapper.unmount()
  })

  it('Test 8: open emittet beim Wechsel false→true', async () => {
    const wrapper = mount(Dialog, {
      props: { modelValue: false, title: 'X' },
      slots: { default: 'B' },
      attachTo: document.body,
    })

    await wrapper.setProps({ modelValue: true })
    await nextTick()

    expect(wrapper.emitted('open')).toHaveLength(1)
    wrapper.unmount()
  })

  it('Test 9: Scroll-Lock setzt body.style.overflow=hidden beim Öffnen', async () => {
    const wrapper = mount(Dialog, {
      props: { modelValue: true, title: 'X' },
      slots: { default: 'B' },
      attachTo: document.body,
    })

    await nextTick()
    expect(document.body.style.overflow).toBe('hidden')

    await wrapper.setProps({ modelValue: false })
    await nextTick()
    expect(document.body.style.overflow).toBe('')

    wrapper.unmount()
  })

  it('Test 10: size=lg setzt entsprechende Klasse', async () => {
    const wrapper = mount(Dialog, {
      props: { modelValue: true, size: 'lg', title: 'X' },
      slots: { default: 'B' },
      attachTo: document.body,
    })

    await nextTick()
    expect(wrapper.find('.dlg-panel--lg').exists()).toBe(true)
    wrapper.unmount()
  })
})
