/**
 * statusMessage — Aufloesungskette serverseitiger Status-/Fortschrittsmeldungen
 * mit optionalem `message_key` (Issue #1174, Muster aus #1458/#1290).
 *
 * Getestete Contracts:
 *   1. `message_key` mit vorhandener Uebersetzung → uebersetzter Text.
 *   2. `message_key` ohne Katalog-Eintrag (te() sagt nein) → Fallback auf `message`.
 *   3. `message_key` ohne Katalog-Eintrag und ohne te() → Key-Gleichheits-Fallback.
 *   4. Kein `message_key` → `message`, sonst leerer String.
 *   5. Die realen `prepare.*`/`report.*`-Keys aus dem Backend-Vertrag loesen in
 *      de.json und en.json auf echte, verschiedene Texte auf.
 */

import { describe, it, expect, vi } from 'vitest'
import { resolveStatusMessage } from '../statusMessage'
import de from '../locales/de.json'
import en from '../locales/en.json'

// Minimaler t()-Stub mit echtem Katalog-Verhalten: Treffer → Text, Miss → Key.
function makeT(catalog: Record<string, string>) {
  return (key: string): string => catalog[key] ?? key
}

function makeTe(catalog: Record<string, string>) {
  return (key: string): boolean => key in catalog
}

const CATALOG = {
  'report.generated': 'Bericht erstellt.',
}

describe('resolveStatusMessage', () => {
  it('Case 1 — message_key mit Katalog-Eintrag gewinnt gegen message', () => {
    const text = resolveStatusMessage(
      { message: 'Report generated', message_key: 'report.generated' },
      makeT(CATALOG),
      makeTe(CATALOG),
    )
    expect(text).toBe('Bericht erstellt.')
  })

  it('Case 2 — unbekannter message_key: te() blockt den Lookup, Fallback auf message', () => {
    const t = vi.fn(makeT(CATALOG))
    const text = resolveStatusMessage(
      { message: 'Legacy status text', message_key: 'report.unbekannt' },
      t,
      makeTe(CATALOG),
    )
    expect(text).toBe('Legacy status text')
    // te() hat den Miss abgefangen — t() wird fuer den Key gar nicht erst gerufen.
    expect(t).not.toHaveBeenCalled()
  })

  it('Case 3 — unbekannter message_key ohne te(): Key-Gleichheit erkennt den Miss', () => {
    const text = resolveStatusMessage(
      { message: 'Legacy status text', message_key: 'report.unbekannt' },
      makeT(CATALOG),
    )
    expect(text).toBe('Legacy status text')
  })

  it('Case 4 — ohne message_key: message, sonst leerer String', () => {
    expect(resolveStatusMessage({ message: 'Nur Klartext' }, makeT(CATALOG))).toBe('Nur Klartext')
    expect(resolveStatusMessage({}, makeT(CATALOG))).toBe('')
    expect(resolveStatusMessage(null, makeT(CATALOG))).toBe('')
  })

  it('Case 5 — die Keys des Backend-Vertrags loesen in beiden Locales auf', () => {
    // Gespiegelt aus backend/app/api/simulation_prepare.py und
    // backend/app/services/report_status.py.
    const keys = [
      'prepare.already_completed',
      'prepare.task_started',
      'prepare.not_started',
      'report.generated',
      'report.failed',
      'report.awaiting_task',
    ]

    function lookup(catalog: unknown, key: string): unknown {
      return key
        .split('.')
        .reduce<unknown>(
          (acc, part) =>
            acc && typeof acc === 'object' ? (acc as Record<string, unknown>)[part] : undefined,
          catalog,
        )
    }

    for (const key of keys) {
      const deVal = lookup(de, key)
      const enVal = lookup(en, key)
      expect(typeof deVal, `de.json fehlt ${key}`).toBe('string')
      expect(typeof enVal, `en.json fehlt ${key}`).toBe('string')
      expect((deVal as string).length).toBeGreaterThan(0)
      expect((enVal as string).length).toBeGreaterThan(0)
    }

    // de und en sind sprachlich verschieden — waeren sie identisch, haette das
    // Uebersetzen keinen Sinn.
    expect(lookup(de, 'report.generated')).not.toBe(lookup(en, 'report.generated'))
  })
})
