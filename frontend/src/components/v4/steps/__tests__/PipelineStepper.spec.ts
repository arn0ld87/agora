/**
 * PipelineStepper — Smoke-Tests (Slice H, Design-v4).
 *
 * Prueft:
 * 1. Mountet ohne Crash.
 * 2. Alle 5 Schritt-Labels werden gerendert.
 * 3. currentStep=1 markiert Schritt 1 als aktiv.
 * 4. currentStep=3 markiert Schritte 1-2 als done, Schritt 3 als aktiv, 4-5 als future.
 * 5. currentStep=5 markiert alle ausser 5 als done.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PipelineStepper from '../PipelineStepper.vue'

describe('PipelineStepper', () => {
  it('mountet ohne Crash', () => {
    const wrapper = mount(PipelineStepper, { props: { currentStep: 1 } })
    expect(wrapper.exists()).toBe(true)
  })

  it('rendert alle 5 Step-Labels', () => {
    const wrapper = mount(PipelineStepper, { props: { currentStep: 1 } })
    const labels = wrapper.findAll('.pipeline-stepper__label').map((el) => el.text())
    expect(labels).toEqual(['Upload', 'Personas', 'Simulation', 'Report', 'Interaktion'])
  })

  it('currentStep=1: erster Schritt ist aktiv, restliche future', () => {
    const wrapper = mount(PipelineStepper, { props: { currentStep: 1 } })
    const steps = wrapper.findAll('.pipeline-stepper__step')
    expect(steps[0].classes()).toContain('pipeline-stepper__step--active')
    expect(steps[1].classes()).toContain('pipeline-stepper__step--future')
    expect(steps[4].classes()).toContain('pipeline-stepper__step--future')
  })

  it('currentStep=3: Schritte 1+2 done, Schritt 3 aktiv, 4+5 future', () => {
    const wrapper = mount(PipelineStepper, { props: { currentStep: 3 } })
    const steps = wrapper.findAll('.pipeline-stepper__step')
    expect(steps[0].classes()).toContain('pipeline-stepper__step--done')
    expect(steps[1].classes()).toContain('pipeline-stepper__step--done')
    expect(steps[2].classes()).toContain('pipeline-stepper__step--active')
    expect(steps[3].classes()).toContain('pipeline-stepper__step--future')
    expect(steps[4].classes()).toContain('pipeline-stepper__step--future')
  })

  it('currentStep=5: Schritte 1-4 done, Schritt 5 aktiv', () => {
    const wrapper = mount(PipelineStepper, { props: { currentStep: 5 } })
    const steps = wrapper.findAll('.pipeline-stepper__step')
    expect(steps[0].classes()).toContain('pipeline-stepper__step--done')
    expect(steps[3].classes()).toContain('pipeline-stepper__step--done')
    expect(steps[4].classes()).toContain('pipeline-stepper__step--active')
  })

  it('aria-current="step" ist nur auf dem aktiven Schritt gesetzt', () => {
    const wrapper = mount(PipelineStepper, { props: { currentStep: 2 } })
    const steps = wrapper.findAll('.pipeline-stepper__step')
    expect(steps[1].attributes('aria-current')).toBe('step')
    expect(steps[0].attributes('aria-current')).toBeUndefined()
    expect(steps[2].attributes('aria-current')).toBeUndefined()
  })
})
