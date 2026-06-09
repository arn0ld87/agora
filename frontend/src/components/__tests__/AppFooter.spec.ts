/**
 * AppFooter — Tests.
 *
 * Test 1: Neo4j Browser link is visible in DEV mode.
 * Test 2: Neo4j Browser link is hidden in PROD mode.
 * Test 3: Link text is properly i18n-ized.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import AppFooter from '../AppFooter.vue'
import de from '../../i18n/locales/de.json'
import en from '../../i18n/locales/en.json'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  messages: {
    de,
    en,
  },
})

describe('AppFooter', () => {
  it('should render Neo4j Browser link in DEV mode', () => {
    // Simulate DEV mode
    import.meta.env.DEV = true

    const wrapper = mount(AppFooter, {
      global: {
        plugins: [i18n],
      },
    })

    const neo4jLink = wrapper.find('a[href="http://localhost:7474"]')
    expect(neo4jLink.exists()).toBe(true)
    expect(neo4jLink.text()).toContain('Neo4j Browser')
  })

  it('should NOT render Neo4j Browser link in PROD mode', () => {
    // Simulate PROD mode
    import.meta.env.DEV = false

    const wrapper = mount(AppFooter, {
      global: {
        plugins: [i18n],
      },
    })

    const neo4jLink = wrapper.find('a[href="http://localhost:7474"]')
    expect(neo4jLink.exists()).toBe(false)
  })

  it('should use i18n key for Neo4j Browser link text', () => {
    import.meta.env.DEV = true

    const wrapper = mount(AppFooter, {
      global: {
        plugins: [i18n],
      },
    })

    const neo4jLink = wrapper.find('a[href="http://localhost:7474"]')
    expect(neo4jLink.exists()).toBe(true)
    // Check that it uses the i18n key (will be rendered text)
    expect(neo4jLink.text().length > 0).toBe(true)
  })
})
