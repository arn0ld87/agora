/**
 * Stubs fuer die Daten-Composables der Seitenleiste (#1795).
 *
 * Specs, die die Seitenleiste nur als Huelle mounten, sollen weder die Ablage
 * laden noch /api/status abfragen. Einbindung per
 * `vi.mock('@/composables/useLibraryCounts', async () => (await import('./sidebarMocks')).libraryCountsMock)`.
 */
import { computed, ref } from 'vue'

export const libraryCountsMock = {
  useLibraryCounts: () => ({
    counts: computed(() => ({
      laeufe: 9,
      graphen: 3,
      personasaetze: 2,
      laeuft: 0,
      brauchtDich: 2,
      aktivitaet: 42,
    })),
    loadFailed: ref(false),
    compareSimulationId: ref<string | null>(null),
    reload: async () => {},
  }),
}

export const sidebarSystemMock = {
  useSidebarSystem: () => ({ tone: ref('ok') }),
}
