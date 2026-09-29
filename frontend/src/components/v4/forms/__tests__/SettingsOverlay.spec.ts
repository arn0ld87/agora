/**
 * SettingsOverlay — Fix #1713 (Befund 7, Doppelnavigation).
 *
 * Die eigene Sektionsliste (Nav + eigenes <h1> + "Zurück") ist entfallen —
 * die Sidebar-Gruppe „Einstellungen” ist die einzige Navigationsebene fuer
 * `/settings/*` (siehe Sidebar.spec.ts). SettingsOverlay ist jetzt nur noch
 * ein Layout-Wrapper: mountet ohne Crash und rendert den Slot-Inhalt.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { SettingsOverlayTestId } from '@/contracts/testIds'
import SettingsOverlay from '../SettingsOverlay.vue'

describe('SettingsOverlay', () => {
  it('mountet ohne Crash und rendert den Slot-Inhalt', () => {
    const wrapper = mount(SettingsOverlay, {
      slots: { default: '<p class="slot-probe">Inhalt</p>' },
    })
    expect(wrapper.find('.slot-probe').exists()).toBe(true)
  })

  it('traegt keine eigene Navigation mehr (Doppelnavigation aufgeloest)', () => {
    const wrapper = mount(SettingsOverlay, {
      slots: { default: '<p class="slot-probe">Inhalt</p>' },
    })
    expect(wrapper.find('nav').exists()).toBe(false)
    expect(wrapper.find('h1').exists()).toBe(false)
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('traegt den Root-Marker fuer Layout-Tests', () => {
    const wrapper = mount(SettingsOverlay, {
      slots: { default: '<p class="slot-probe">Inhalt</p>' },
    })
    expect(wrapper.attributes('data-testid')).toBe(SettingsOverlayTestId.root)
  })
})
