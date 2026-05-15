/**
 * locale-coverage — i18n-Schlüssel-Vollständigkeitstest (Smoke-Fix Slice 06).
 *
 * Prueft:
 * 1. Schlüssel-Parität: de.json und en.json haben exakt dieselben Keys.
 * 2. Pflicht-Keys aus Smoke-Report #9 existieren in beiden Locales:
 *    dashboard.active.phase.ontology_generate
 * 3. Pflicht-Keys aus Smoke-Report #10 (graph.edgeLabels.*):
 *    REPRESENTS, COMMENTS_ON, PLANS_WITH, OWNERSHIP_STAKE, LEADS, SELF_RELATIONS_(1)
 */
import { describe, it, expect } from 'vitest'
import de from '../locales/de.json'
import en from '../locales/en.json'

// ---------------------------------------------------------------------------
// Hilfsfunktion: flacht ein verschachteltes Objekt zu "a.b.c"-Keys ab
// ---------------------------------------------------------------------------
function flatKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === 'object' && v !== null
      ? flatKeys(v as Record<string, unknown>, prefix + k + '.')
      : [prefix + k],
  )
}

const deKeys = flatKeys(de as unknown as Record<string, unknown>).sort()
const enKeys = flatKeys(en as unknown as Record<string, unknown>).sort()

// ---------------------------------------------------------------------------
describe('locale-coverage', () => {
  // 1. Parität
  it('de.json und en.json haben denselben Key-Baum (keine einseitigen Keys)', () => {
    const onlyDe = deKeys.filter((k) => !enKeys.includes(k))
    const onlyEn = enKeys.filter((k) => !deKeys.includes(k))
    expect(onlyDe, `Keys nur in de.json: ${onlyDe.join(', ')}`).toHaveLength(0)
    expect(onlyEn, `Keys nur in en.json: ${onlyEn.join(', ')}`).toHaveLength(0)
  })

  it('de.json und en.json haben dieselbe Anzahl Keys', () => {
    expect(deKeys.length).toBe(enKeys.length)
  })

  // 2. Smoke #9: ontology_generate Phase-Key
  it('dashboard.active.phase.ontology_generate existiert in de.json (smoke #9)', () => {
    expect(deKeys).toContain('dashboard.active.phase.ontology_generate')
  })

  it('dashboard.active.phase.ontology_generate existiert in en.json (smoke #9)', () => {
    expect(enKeys).toContain('dashboard.active.phase.ontology_generate')
  })

  it('de: ontology_generate ist nicht leer und kein EN-String', () => {
    const val = (de as Record<string, unknown> & {
      dashboard: { active: { phase: { ontology_generate: string } } }
    }).dashboard.active.phase.ontology_generate
    expect(typeof val).toBe('string')
    expect(val.length).toBeGreaterThan(0)
    // Kein reiner EN-Wert (kurze Heuristik: darf nicht mit "Generating" beginnen)
    expect(val).not.toMatch(/^Generating/i)
  })

  // 3. Smoke #10: graph.edgeLabels.*
  const missingEdgeLabels = [
    'REPRESENTS',
    'COMMENTS_ON',
    'PLANS_WITH',
    'OWNERSHIP_STAKE',
    'LEADS',
    'SELF_RELATIONS_(1)',
  ] as const

  for (const label of missingEdgeLabels) {
    it(`graph.edgeLabels.${label} existiert in de.json (smoke #10)`, () => {
      expect(deKeys).toContain(`graph.edgeLabels.${label}`)
    })

    it(`graph.edgeLabels.${label} existiert in en.json (smoke #10)`, () => {
      expect(enKeys).toContain(`graph.edgeLabels.${label}`)
    })
  }

  // 4. Sidebar-Keys (smoke #8)
  it('sidebar.nav.* Keys existieren in beiden Locales', () => {
    const navIds = ['dashboard', 'runs', 'projects', 'datasets', 'templates', 'monitoring']
    for (const id of navIds) {
      expect(deKeys).toContain(`sidebar.nav.${id}`)
      expect(enKeys).toContain(`sidebar.nav.${id}`)
    }
  })

  it('sidebar.settings.* Keys existieren in beiden Locales', () => {
    const settingsIds = ['label', 'general', 'integrations', 'usersTeams', 'apiKeys', 'llmProviders', 'llmRouting', 'auditLogs']
    for (const id of settingsIds) {
      expect(deKeys).toContain(`sidebar.settings.${id}`)
      expect(enKeys).toContain(`sidebar.settings.${id}`)
    }
  })

  it('topbar.search und topbar.notifications existieren in beiden Locales', () => {
    expect(deKeys).toContain('topbar.search')
    expect(deKeys).toContain('topbar.notifications')
    expect(enKeys).toContain('topbar.search')
    expect(enKeys).toContain('topbar.notifications')
  })
})
