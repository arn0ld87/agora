/**
 * Tests für usePersonaQuota — Sub-Slice 35, Refs #203.
 *
 * Getestete Contracts:
 *   1. Add/Remove: addQuotaSegment fügt Eintrag mit eindeutiger id hinzu;
 *      removeQuotaSegment(idx) entfernt korrekt; quotaTotal aktualisiert sich.
 *   2. Total-Computed: drei Einträge 5/10/3 → 18; leere Liste → 0;
 *      nicht-numerische count wird als 0 behandelt.
 *   3. Zod-Valid: plausibler Plan → quotaValidationError === ''.
 *   4. Zod-Invalid: negativer count / leerer Segment-Name → Fehlermeldung.
 *   5. LocalStorage-Round-Trip: speichern → neues Composable → Einträge geladen.
 *   6. Toggle-Reset: useQuotaPlan = false → quotaValidationError === '' auch
 *      bei eigentlich invalidem Plan.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { usePersonaQuota, STORAGE_QUOTA_PLAN } from '../usePersonaQuota'

// ---------------------------------------------------------------------------
// Mock t() — identity function; tests check key suffixes, not translated text
// ---------------------------------------------------------------------------
const t = (key: string): string => key

// ---------------------------------------------------------------------------
// LocalStorage stub
// ---------------------------------------------------------------------------

function makeLocalStorageStub(): Storage {
  const store: Record<string, string> = {}
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
    get length() { return Object.keys(store).length },
    key: (i: number) => Object.keys(store)[i] ?? null,
  }
}

let localStorageStub: Storage

beforeEach(() => {
  localStorageStub = makeLocalStorageStub()
  vi.stubGlobal('localStorage', localStorageStub)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('usePersonaQuota', () => {
  // -------------------------------------------------------------------------
  // Case 1 — Add/Remove
  // -------------------------------------------------------------------------

  describe('Case 1 — addQuotaSegment / removeQuotaSegment / quotaTotal', () => {
    it('addQuotaSegment fügt Eintrag mit eindeutiger id hinzu', () => {
      const q = usePersonaQuota({ t })

      expect(q.quotaEntries.value).toHaveLength(0)

      q.addQuotaSegment()
      expect(q.quotaEntries.value).toHaveLength(1)

      q.addQuotaSegment()
      expect(q.quotaEntries.value).toHaveLength(2)

      const [a, b] = q.quotaEntries.value
      expect(a.id).toBeTruthy()
      expect(b.id).toBeTruthy()
      expect(a.id).not.toBe(b.id)
    })

    it('removeQuotaSegment(idx) entfernt den Eintrag am korrekten Index', () => {
      const q = usePersonaQuota({ t })
      q.addQuotaSegment()
      q.addQuotaSegment()
      q.addQuotaSegment()

      const idToKeep = q.quotaEntries.value[2].id
      q.removeQuotaSegment(0)
      q.removeQuotaSegment(0)

      expect(q.quotaEntries.value).toHaveLength(1)
      expect(q.quotaEntries.value[0].id).toBe(idToKeep)
    })

    it('quotaTotal ändert sich nach add und remove korrekt', () => {
      const q = usePersonaQuota({ t })
      expect(q.quotaTotal.value).toBe(0)

      q.addQuotaSegment()
      q.quotaEntries.value[0].count = 10

      q.addQuotaSegment()
      q.quotaEntries.value[1].count = 7

      expect(q.quotaTotal.value).toBe(17)

      q.removeQuotaSegment(0)
      expect(q.quotaTotal.value).toBe(7)
    })
  })

  // -------------------------------------------------------------------------
  // Case 2 — Total-Computed edge cases
  // -------------------------------------------------------------------------

  describe('Case 2 — quotaTotal edge cases', () => {
    it('drei Einträge 5/10/3 → quotaTotal === 18', () => {
      const q = usePersonaQuota({ t })
      q.quotaEntries.value = [
        { id: 'a', segment: 'Seg A', count: 5 },
        { id: 'b', segment: 'Seg B', count: 10 },
        { id: 'c', segment: 'Seg C', count: 3 },
      ]
      expect(q.quotaTotal.value).toBe(18)
    })

    it('leere Liste → quotaTotal === 0', () => {
      const q = usePersonaQuota({ t })
      expect(q.quotaEntries.value).toHaveLength(0)
      expect(q.quotaTotal.value).toBe(0)
    })

    it('nicht-numerische count wird als 0 behandelt', () => {
      const q = usePersonaQuota({ t })
      // TypeScript disallows string here, but runtime/JS can pass it,
      // so we cast to test the defensive Number() handling.
      q.quotaEntries.value = [
        { id: 'a', segment: 'Seg A', count: 'abc' as unknown as number },
        { id: 'b', segment: 'Seg B', count: 5 },
      ]
      expect(q.quotaTotal.value).toBe(5)
    })
  })

  // -------------------------------------------------------------------------
  // Case 3 — Zod-Valid
  // -------------------------------------------------------------------------

  describe('Case 3 — Zod-Valid: plausibler Plan liefert leeren Fehlerstring', () => {
    it('quotaValidationError === "" wenn Plan valide und Quota aktiviert', () => {
      const q = usePersonaQuota({ t })
      q.useQuotaPlan.value = true
      q.quotaEntries.value = [
        { id: 'a', segment: 'Millennial', count: 20 },
        { id: 'b', segment: 'Gen Z', count: 30 },
      ]
      expect(q.quotaValidationError.value).toBe('')
    })

    it('quotaValidationError === "" wenn useQuotaPlan=false (unabhängig von Einträgen)', () => {
      const q = usePersonaQuota({ t })
      q.useQuotaPlan.value = false
      // Empty entries with no segments — would fail Zod if plan were validated
      q.quotaEntries.value = []
      expect(q.quotaValidationError.value).toBe('')
    })
  })

  // -------------------------------------------------------------------------
  // Case 4 — Zod-Invalid
  // -------------------------------------------------------------------------

  describe('Case 4 — Zod-Invalid: ungültiger Plan liefert Fehlermeldung', () => {
    it('leere Einträge mit aktiviertem Plan → Fehler "targets muss mindestens..."', () => {
      const q = usePersonaQuota({ t })
      q.useQuotaPlan.value = true
      q.quotaEntries.value = []
      // Zod rejects: empty targets list → custom issue
      expect(q.quotaValidationError.value).not.toBe('')
    })

    it('Eintrag ohne Segment-Name (segment="") → Fehler', () => {
      const q = usePersonaQuota({ t })
      q.useQuotaPlan.value = true
      q.quotaEntries.value = [
        { id: 'a', segment: '', count: 10 },
      ]
      // buildQuotaPlanFromEntries skips entries with empty segment → empty targets
      expect(q.quotaValidationError.value).not.toBe('')
    })

    it('Eintrag mit count=0 (filtert zu total=0) → Fehler', () => {
      const q = usePersonaQuota({ t })
      q.useQuotaPlan.value = true
      q.quotaEntries.value = [
        { id: 'a', segment: 'Seg A', count: 0 },
      ]
      // Zod: count 0 fails min(1) constraint → fails safeParse
      expect(q.quotaValidationError.value).not.toBe('')
    })
  })

  // -------------------------------------------------------------------------
  // Case 5 — LocalStorage-Round-Trip
  // -------------------------------------------------------------------------

  describe('Case 5 — LocalStorage-Round-Trip', () => {
    it('gespeicherter Plan wird beim nächsten Composable-Aufruf geladen', async () => {
      // Simulate a previously saved plan in localStorage
      const plan = {
        targets: { Millennial: 15, 'Gen Z': 25 },
        total: 40,
      }
      localStorageStub.setItem(STORAGE_QUOTA_PLAN, JSON.stringify(plan))

      // New composable instance reads from localStorage on init
      const q = usePersonaQuota({ t })

      expect(q.quotaEntries.value).toHaveLength(2)
      expect(q.quotaEntries.value.find((e) => e.segment === 'Millennial')?.count).toBe(15)
      expect(q.quotaEntries.value.find((e) => e.segment === 'Gen Z')?.count).toBe(25)
    })

    it('Änderungen an quotaEntries werden in localStorage persistiert', async () => {
      const q = usePersonaQuota({ t })
      q.quotaEntries.value = [
        { id: 'x', segment: 'Boomer', count: 8 },
      ]

      // Vue watchers fire asynchronously
      await nextTick()
      await nextTick()

      const raw = localStorageStub.getItem(STORAGE_QUOTA_PLAN)
      expect(raw).not.toBeNull()
      const stored = JSON.parse(raw!)
      expect(stored.targets['Boomer']).toBe(8)
      expect(stored.total).toBe(8)
    })

    it('leere Einträge-Liste wird korrekt geladen wenn localStorage kein quotaPlan hat', () => {
      // localStorageStub is empty by default
      const q = usePersonaQuota({ t })
      expect(q.quotaEntries.value).toHaveLength(0)
    })
  })

  // -------------------------------------------------------------------------
  // Case 6 — Toggle-Reset
  // -------------------------------------------------------------------------

  describe('Case 6 — Toggle-Reset: useQuotaPlan=false → kein Validierungsfehler', () => {
    it('useQuotaPlan=false → quotaValidationError leer auch wenn Plan invalid wäre', () => {
      const q = usePersonaQuota({ t })
      // Plan wäre invalid (leer)
      q.quotaEntries.value = []
      q.useQuotaPlan.value = false
      expect(q.quotaValidationError.value).toBe('')
    })

    it('useQuotaPlan=true → bei invalidem Plan Fehler; nach Toggle auf false → leer', () => {
      const q = usePersonaQuota({ t })
      q.useQuotaPlan.value = true
      q.quotaEntries.value = [] // invalid when plan is active
      expect(q.quotaValidationError.value).not.toBe('')

      q.useQuotaPlan.value = false
      expect(q.quotaValidationError.value).toBe('')
    })
  })
})
