/**
 * Tests für usePersonaFilter — Sub-Slice 40, Refs #203.
 *
 * Getestete Contracts:
 *   1.  Leerer personaSearch → filteredPersonas === profiles (alle Profile).
 *   2.  Suche case-insensitive auf username-Feld findet Treffer.
 *   3.  Suche matcht auf name / bio / persona / profession / country / mbti.
 *   4.  Suche matcht auf interested_topics-Array (Element wird gefunden).
 *   5.  interested_topics als String (defensiv): kein TypeError, String wird durchsucht.
 *   6.  null/undefined-Profile in der Liste werfen keinen Fehler.
 *   7.  visiblePersonas Default: schneidet auf 24, wenn profiles.length > 24, personaSearch leer, showAllPersonas=false.
 *   8.  visiblePersonas zeigt alle, wenn showAllPersonas=true.
 *   9.  visiblePersonas zeigt alle Treffer ohne Slice, wenn personaSearch gesetzt (auch > 24 Treffer).
 *   10. Reactivity: profiles.value ändert sich → filteredPersonas reagiert.
 */

import { describe, it, expect } from 'vitest'
import { ref, nextTick } from 'vue'
import { usePersonaFilter } from '../usePersonaFilter'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildProfiles(count: number, overrides: Record<string, unknown> = {}) {
  return Array.from({ length: count }, (_, i) => ({
    username: `user${i}`,
    name: `Name ${i}`,
    bio: `Bio ${i}`,
    persona: `Persona ${i}`,
    profession: `Prof ${i}`,
    country: 'DE',
    mbti: 'INTJ',
    interested_topics: ['Sport', 'Tech'],
    ...overrides,
  }))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('usePersonaFilter', () => {

  // -------------------------------------------------------------------------
  // Case 1 — Leerer personaSearch → alle Profile zurück
  // -------------------------------------------------------------------------

  describe('Case 1 — leerer personaSearch gibt alle Profile zurück', () => {
    it('filteredPersonas entspricht profiles bei leerem Search', () => {
      const profiles = ref(buildProfiles(3))
      const { filteredPersonas } = usePersonaFilter({ profiles })

      expect(filteredPersonas.value).toEqual(profiles.value)
    })

    it('filteredPersonas ist leer bei leerer profiles-Liste', () => {
      const profiles = ref<unknown[]>([])
      const { filteredPersonas } = usePersonaFilter({ profiles })

      expect(filteredPersonas.value).toHaveLength(0)
    })
  })

  // -------------------------------------------------------------------------
  // Case 2 — Suche case-insensitive auf username
  // -------------------------------------------------------------------------

  describe('Case 2 — Suche case-insensitive auf username', () => {
    it('findet Profil wenn Suchterm in username (lowercase)', () => {
      const profiles = ref([
        { username: 'AliceWonder', name: 'Alice', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [] },
        { username: 'bob123', name: 'Bob', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [] },
      ])
      const { personaSearch, filteredPersonas } = usePersonaFilter({ profiles })

      personaSearch.value = 'alice'

      expect(filteredPersonas.value).toHaveLength(1)
      expect(filteredPersonas.value[0]).toMatchObject({ username: 'AliceWonder' })
    })

    it('findet Profil wenn Suchterm in username (uppercase)', () => {
      const profiles = ref([
        { username: 'alicewonder', name: '', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [] },
      ])
      const { personaSearch, filteredPersonas } = usePersonaFilter({ profiles })

      personaSearch.value = 'ALICE'

      expect(filteredPersonas.value).toHaveLength(1)
    })

    it('gibt kein Ergebnis zurück wenn Suchterm nicht matched', () => {
      const profiles = ref([
        { username: 'bob123', name: 'Bob', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [] },
      ])
      const { personaSearch, filteredPersonas } = usePersonaFilter({ profiles })

      personaSearch.value = 'alice'

      expect(filteredPersonas.value).toHaveLength(0)
    })
  })

  // -------------------------------------------------------------------------
  // Case 3 — Suche matcht auf alle Textfelder
  // -------------------------------------------------------------------------

  describe('Case 3 — Suche matcht auf verschiedene Felder', () => {
    it.each([
      ['name', { name: 'Zielgruppe Alpha' }, 'zielgruppe'],
      ['bio', { bio: 'Technologie-Enthusiast aus Berlin' }, 'technologie'],
      ['persona', { persona: 'Der reflektierte Skeptiker' }, 'skeptiker'],
      ['profession', { profession: 'Softwareentwickler' }, 'software'],
      ['country', { country: 'Österreich' }, 'österreich'],
      ['mbti', { mbti: 'ENFP' }, 'enfp'],
    ])('findet Profil via %s-Feld', (_field, profileData, searchTerm) => {
      const profiles = ref([
        { username: 'user1', name: '', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [], ...profileData },
        { username: 'noMatch', name: '', bio: '', persona: '', profession: '', country: 'US', mbti: 'ISTJ', interested_topics: [] },
      ])
      const { personaSearch, filteredPersonas } = usePersonaFilter({ profiles })

      personaSearch.value = searchTerm

      expect(filteredPersonas.value).toHaveLength(1)
      expect(filteredPersonas.value[0]).toMatchObject({ username: 'user1' })
    })
  })

  // -------------------------------------------------------------------------
  // Case 4 — Suche matcht auf interested_topics-Array
  // -------------------------------------------------------------------------

  describe('Case 4 — Suche matcht auf interested_topics-Array', () => {
    it('findet Profil wenn Suchterm in einem Topic-Element vorkommt', () => {
      const profiles = ref([
        { username: 'user1', name: '', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: ['Klimawandel', 'Technologie', 'Sport'] },
        { username: 'user2', name: '', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: ['Musik', 'Kunst'] },
      ])
      const { personaSearch, filteredPersonas } = usePersonaFilter({ profiles })

      personaSearch.value = 'klimawandel'

      expect(filteredPersonas.value).toHaveLength(1)
      expect(filteredPersonas.value[0]).toMatchObject({ username: 'user1' })
    })

    it('findet Profil wenn Suchterm als Teilstring in einem Topic vorkommt', () => {
      const profiles = ref([
        { username: 'user1', name: '', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: ['Technologiepolitik'] },
      ])
      const { personaSearch, filteredPersonas } = usePersonaFilter({ profiles })

      personaSearch.value = 'technologie'

      expect(filteredPersonas.value).toHaveLength(1)
    })

    it('gibt kein Ergebnis wenn Suchterm in keinem Topic vorkommt', () => {
      const profiles = ref([
        { username: 'user1', name: '', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: ['Musik', 'Kunst'] },
      ])
      const { personaSearch, filteredPersonas } = usePersonaFilter({ profiles })

      personaSearch.value = 'klimawandel'

      expect(filteredPersonas.value).toHaveLength(0)
    })
  })

  // -------------------------------------------------------------------------
  // Case 5 — interested_topics als String (defensiv)
  // -------------------------------------------------------------------------

  describe('Case 5 — interested_topics als String', () => {
    it('wirft keinen TypeError wenn interested_topics ein String ist', () => {
      const profiles = ref([
        { username: 'user1', name: '', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: 'Klimawandel,Technologie' },
      ])
      const { personaSearch, filteredPersonas } = usePersonaFilter({ profiles })

      personaSearch.value = 'klimawandel'

      expect(() => filteredPersonas.value).not.toThrow()
    })

    it('durchsucht interessted_topics-String-Inhalt', () => {
      const profiles = ref([
        { username: 'user1', name: '', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: 'Klimawandel Technologie' },
        { username: 'user2', name: '', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: 'Musik Kunst' },
      ])
      const { personaSearch, filteredPersonas } = usePersonaFilter({ profiles })

      personaSearch.value = 'klimawandel'

      expect(filteredPersonas.value).toHaveLength(1)
      expect(filteredPersonas.value[0]).toMatchObject({ username: 'user1' })
    })
  })

  // -------------------------------------------------------------------------
  // Case 6 — null/undefined-Profile
  // -------------------------------------------------------------------------

  describe('Case 6 — null/undefined-Profile in der Liste', () => {
    it('wirft keinen Fehler wenn Profile null/undefined enthalten', () => {
      const profiles = ref<unknown[]>([
        null,
        undefined,
        { username: 'user1', name: 'Alice', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [] },
      ])
      const { personaSearch, filteredPersonas } = usePersonaFilter({ profiles })

      personaSearch.value = 'alice'

      expect(() => filteredPersonas.value).not.toThrow()
    })

    it('findet valides Profil auch wenn Liste null-Einträge enthält', () => {
      const profiles = ref<unknown[]>([
        null,
        { username: 'alice', name: 'Alice', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [] },
        undefined,
      ])
      const { personaSearch, filteredPersonas } = usePersonaFilter({ profiles })

      personaSearch.value = 'alice'

      expect(filteredPersonas.value).toHaveLength(1)
      expect((filteredPersonas.value[0] as Record<string, unknown>).username).toBe('alice')
    })
  })

  // -------------------------------------------------------------------------
  // Case 7 — visiblePersonas Default: Slice auf 24
  // -------------------------------------------------------------------------

  describe('Case 7 — visiblePersonas Default: Slice auf 24', () => {
    it('zeigt maximal 24 Profile wenn showAllPersonas=false und personaSearch leer', () => {
      const profiles = ref(buildProfiles(30))
      const { visiblePersonas } = usePersonaFilter({ profiles })

      expect(visiblePersonas.value).toHaveLength(24)
    })

    it('zeigt alle Profile wenn profiles.length <= 24', () => {
      const profiles = ref(buildProfiles(10))
      const { visiblePersonas } = usePersonaFilter({ profiles })

      expect(visiblePersonas.value).toHaveLength(10)
    })

    it('zeigt erste 24 Profile (nicht zufällig)', () => {
      const profiles = ref(buildProfiles(30))
      const { visiblePersonas } = usePersonaFilter({ profiles })

      expect(visiblePersonas.value[0]).toMatchObject({ username: 'user0' })
      expect(visiblePersonas.value[23]).toMatchObject({ username: 'user23' })
    })
  })

  // -------------------------------------------------------------------------
  // Case 8 — visiblePersonas zeigt alle wenn showAllPersonas=true
  // -------------------------------------------------------------------------

  describe('Case 8 — visiblePersonas zeigt alle bei showAllPersonas=true', () => {
    it('zeigt alle Profile wenn showAllPersonas=true, auch > 24', () => {
      const profiles = ref(buildProfiles(30))
      const { showAllPersonas, visiblePersonas } = usePersonaFilter({ profiles })

      showAllPersonas.value = true

      expect(visiblePersonas.value).toHaveLength(30)
    })

    it('toggling showAllPersonas zurück auf false beschränkt wieder auf 24', () => {
      const profiles = ref(buildProfiles(30))
      const { showAllPersonas, visiblePersonas } = usePersonaFilter({ profiles })

      showAllPersonas.value = true
      expect(visiblePersonas.value).toHaveLength(30)

      showAllPersonas.value = false
      expect(visiblePersonas.value).toHaveLength(24)
    })
  })

  // -------------------------------------------------------------------------
  // Case 9 — visiblePersonas zeigt alle Treffer ohne Slice bei personaSearch
  // -------------------------------------------------------------------------

  describe('Case 9 — visiblePersonas ohne Slice bei aktivem personaSearch', () => {
    it('zeigt alle Treffer wenn personaSearch gesetzt ist, auch > 24', () => {
      const profiles = ref(buildProfiles(30, { country: 'CH' }))
      const { personaSearch, visiblePersonas } = usePersonaFilter({ profiles })

      personaSearch.value = 'ch' // matcht country='CH' in allen 30 Profilen

      expect(visiblePersonas.value).toHaveLength(30)
    })

    it('zeigt 0 Treffer wenn personaSearch gesetzt aber nichts matcht', () => {
      const profiles = ref(buildProfiles(30))
      const { personaSearch, visiblePersonas } = usePersonaFilter({ profiles })

      personaSearch.value = 'xxxxxxxx-kein-treffer'

      expect(visiblePersonas.value).toHaveLength(0)
    })

    it('whitespace-only personaSearch gilt als leer (greift auf Slice-Logik zurück)', () => {
      const profiles = ref(buildProfiles(30))
      const { personaSearch, visiblePersonas } = usePersonaFilter({ profiles })

      personaSearch.value = '   '

      // Whitespace-only → trim() ergibt '', wird als leer behandelt → Slice auf 24
      expect(visiblePersonas.value).toHaveLength(24)
    })
  })

  // -------------------------------------------------------------------------
  // Case 10 — Reactivity: profiles-Änderung propagiert in filteredPersonas
  // -------------------------------------------------------------------------

  describe('Case 10 — Reactivity', () => {
    it('filteredPersonas reagiert auf Änderung von profiles.value', async () => {
      const profiles = ref<unknown[]>([
        { username: 'user1', name: 'Alice', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [] },
      ])
      const { filteredPersonas } = usePersonaFilter({ profiles })

      expect(filteredPersonas.value).toHaveLength(1)

      profiles.value = [
        { username: 'user1', name: 'Alice', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [] },
        { username: 'user2', name: 'Bob', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [] },
        { username: 'user3', name: 'Carol', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [] },
      ]

      await nextTick()

      expect(filteredPersonas.value).toHaveLength(3)
    })

    it('filteredPersonas reagiert auf Änderung von personaSearch', async () => {
      const profiles = ref([
        { username: 'alice', name: 'Alice', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [] },
        { username: 'bob', name: 'Bob', bio: '', persona: '', profession: '', country: 'DE', mbti: '', interested_topics: [] },
      ])
      const { personaSearch, filteredPersonas } = usePersonaFilter({ profiles })

      expect(filteredPersonas.value).toHaveLength(2)

      personaSearch.value = 'alice'
      await nextTick()

      expect(filteredPersonas.value).toHaveLength(1)
      expect((filteredPersonas.value[0] as Record<string, unknown>).username).toBe('alice')
    })
  })

})
