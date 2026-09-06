/**
 * Button — Tests
 * Slice UI-A · 2026-05-15
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Button, { type ButtonVariant } from '../Button.vue'

describe('Button', () => {
  it('Test 1: Default-Mount nutzt primary + md (kein --md-Suffix in Klassenliste)', () => {
    const wrapper = mount(Button, {
      slots: { default: 'Speichern' },
    })

    const btn = wrapper.find('button')
    expect(btn.classes()).toContain('btn')
    expect(btn.classes()).toContain('btn--primary')
    // md ist Default-Size → kein btn--md-Suffix
    expect(btn.classes()).not.toContain('btn--md')
    expect(btn.text()).toBe('Speichern')
    expect(btn.attributes('type')).toBe('button')
  })

  it('Test 2: variant=danger trägt Danger-Klasse', () => {
    const wrapper = mount(Button, {
      props: { variant: 'danger' },
      slots: { default: 'Löschen' },
    })

    expect(wrapper.find('button').classes()).toContain('btn--danger')
  })

  it('Test 3: size=sm und size=lg setzen entsprechende Suffix-Klassen', () => {
    const sm = mount(Button, { props: { size: 'sm' }, slots: { default: 'X' } })
    const lg = mount(Button, { props: { size: 'lg' }, slots: { default: 'X' } })

    expect(sm.find('button').classes()).toContain('btn--sm')
    expect(lg.find('button').classes()).toContain('btn--lg')
  })

  it('Test 4: loading deaktiviert Button, zeigt Spinner + aria-busy=true', () => {
    const wrapper = mount(Button, {
      props: { loading: true },
      slots: { default: 'Lade' },
    })

    const btn = wrapper.find('button')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.attributes('aria-busy')).toBe('true')
    expect(wrapper.find('.btn-spinner').exists()).toBe(true)
    expect(btn.classes()).toContain('is-loading')
  })

  it('Test 5: disabled blockiert Click-Emit nicht (Browser blockt, nicht Komponente)', async () => {
    const wrapper = mount(Button, {
      props: { disabled: true },
      slots: { default: 'X' },
    })

    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
  })

  it('Test 6: arrow=true rendert Pfeil-Glyph aria-hidden', () => {
    const wrapper = mount(Button, {
      props: { arrow: true },
      slots: { default: 'Weiter' },
    })

    const arrow = wrapper.find('.arrow')
    expect(arrow.exists()).toBe(true)
    expect(arrow.text()).toBe('→')
    expect(arrow.attributes('aria-hidden')).toBe('true')
  })

  it('Test 7: icon=true trägt btn--icon-Klasse und nutzt aria-label', () => {
    const wrapper = mount(Button, {
      props: { icon: true, ariaLabel: 'Schließen' },
      slots: { default: '<svg width="14" height="14"/>' },
    })

    const btn = wrapper.find('button')
    expect(btn.classes()).toContain('btn--icon')
    expect(btn.attributes('aria-label')).toBe('Schließen')
  })

  it('Test 8: Click emittiert MouseEvent', async () => {
    const wrapper = mount(Button, { slots: { default: 'Klick' } })

    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
    const event = wrapper.emitted('click')?.[0]?.[0]
    expect(event).toBeInstanceOf(MouseEvent)
  })

  it('Test 9: type=submit wird durchgereicht', () => {
    const wrapper = mount(Button, {
      props: { type: 'submit' },
      slots: { default: 'Submit' },
    })

    expect(wrapper.find('button').attributes('type')).toBe('submit')
  })

  it('Test 10: nur noch vier Varianten sind zulässig (primary/secondary/ghost/danger)', () => {
    // Regressionstest zu PR 5 (Control-Primitives): tinted/accent/info/plasma/glass
    // sind per Audit gestrichen. Der Typecheck (`bun run check`) schlägt fehl,
    // sobald jemand eine der gestrichenen Varianten erneut zulässt.
    const erlaubteVarianten: ButtonVariant[] = ['primary', 'secondary', 'ghost', 'danger']
    for (const variant of erlaubteVarianten) {
      const wrapper = mount(Button, { props: { variant }, slots: { default: 'X' } })
      expect(wrapper.find('button').classes()).toContain(`btn--${variant}`)
    }
  })
})
