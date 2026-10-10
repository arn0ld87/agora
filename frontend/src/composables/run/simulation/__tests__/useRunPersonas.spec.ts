import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick } from 'vue'

const api = vi.hoisted(() => ({
  profiles: vi.fn(),
  config: vi.fn(),
}))

vi.mock('@/api/simulation', () => ({
  getSimulationProfiles: api.profiles,
  getSimulationConfig: api.config,
}))

import { useRunPersonas } from '../useRunPersonas'

async function flush(): Promise<void> {
  for (let i = 0; i < 5; i++) await Promise.resolve()
  await nextTick()
}

function setup() {
  const scope = effectScope()
  return scope.run(() => useRunPersonas('sim-1'))!
}

const profiles = {
  success: true,
  data: {
    profiles: [
      { user_id: 0, username: 'anna', name: 'Anna Beck', bio: 'Bio A', profession: 'Landwirtin', extra: 1 },
      // Position 1 trägt Konfigurations-Nummer 2: Profil 1 wurde abgelehnt.
      { user_id: 2, username: 'carl', name: 'Carl', bio: 'Bio C' },
      { username: 'dora', name: 'Dora' },
    ],
  },
}
const config = {
  success: true,
  data: {
    contested_question: 'Soll die Pflicht kommen?',
    agent_configs: [
      { agent_id: 0, stance: 'supportive', activity_level: 0.7 },
      { agent_id: 1, stance: 'opposing' },
      { agent_id: 2, stance: 'neutral' },
    ],
  },
}

beforeEach(() => {
  api.profiles.mockReset()
  api.config.mockReset()
})

describe('useRunPersonas', () => {
  it('ordnet persona_id (Position) dem Profil und die Haltung über user_id zu', async () => {
    api.profiles.mockResolvedValue(profiles)
    api.config.mockResolvedValue(config)
    const personas = setup()
    await flush()

    expect(personas.error.value).toBeNull()
    expect(personas.contestedQuestion.value).toBe('Soll die Pflicht kommen?')
    expect(personas.personaById('0')).toMatchObject({
      name: 'Anna Beck',
      role: 'Landwirtin',
      bio: 'Bio A',
      stance: 'supportive',
      contestedQuestion: 'Soll die Pflicht kommen?',
    })
    // Position 1 ist Konfigurations-Agent 2, nicht 1.
    expect(personas.personaById('1')).toMatchObject({ name: 'Carl', stance: 'neutral', role: null })
  })

  it('liefert stance null ohne belastbare Zuordnung (kein user_id) und rät nichts', async () => {
    api.profiles.mockResolvedValue(profiles)
    api.config.mockResolvedValue(config)
    const personas = setup()
    await flush()
    expect(personas.personaById('2')).toMatchObject({ name: 'Dora', stance: null })
  })

  it('liefert null für unbekannte oder nicht numerische persona_id', async () => {
    api.profiles.mockResolvedValue(profiles)
    api.config.mockResolvedValue(config)
    const personas = setup()
    await flush()
    expect(personas.personaById('9')).toBeNull()
    expect(personas.personaById('alice')).toBeNull()
    expect(personas.personaById('')).toBeNull()
  })

  it('zeigt einen Konfigurationsfehler, behält die Profile', async () => {
    api.profiles.mockResolvedValue(profiles)
    api.config.mockRejectedValue(new Error('nicht vorbereitet'))
    const personas = setup()
    await flush()
    expect(personas.error.value).toContain('nicht vorbereitet')
    expect(personas.personaById('0')).toMatchObject({ name: 'Anna Beck', stance: null, contestedQuestion: null })
  })

  it('meldet vertragswidrige Antworten sichtbar statt still leer', async () => {
    api.profiles.mockResolvedValue({ success: true, data: { profiles: 'kaputt' } })
    api.config.mockResolvedValue({ success: false, error: 'x' })
    const personas = setup()
    await flush()
    expect(personas.error.value).toContain('Profile')
    expect(personas.error.value).toContain('Konfiguration')
    expect(personas.personaById('0')).toBeNull()
  })

  it('lädt Profile nicht teilweise, wenn ein Eintrag den Vertrag verletzt (Position zählt)', async () => {
    api.profiles.mockResolvedValue({
      success: true,
      data: { profiles: [{ name: 5 }, { name: 'Carl' }] },
    })
    api.config.mockResolvedValue(config)
    const personas = setup()
    await flush()
    expect(personas.error.value).toContain('1 Einträge')
    expect(personas.personaById('1')).toBeNull()
  })

  // UAT-007: Streitfrage als ContestedQuestion-Contract-Objekt (kanonisch seit #1778)
  // darf auf der Interview-Seite keinen Pseudo-Vertragsfehler produzieren.
  it('parst contested_question als Contract-Objekt (Statement, origin=user) ohne Fehler', async () => {
    api.profiles.mockResolvedValue(profiles)
    api.config.mockResolvedValue({
      success: true,
      data: {
        contested_question: {
          statement: 'Soll die Pflicht kommen?',
          origin: 'user',
        },
        agent_configs: [
          { agent_id: 0, stance: 'supportive', activity_level: 0.7 },
          { agent_id: 1, stance: 'opposing' },
          { agent_id: 2, stance: 'neutral' },
        ],
      },
    })
    const personas = setup()
    await flush()
    expect(personas.error.value).toBeNull()
    expect(personas.contestedQuestion.value).toBe('Soll die Pflicht kommen?')
    expect(personas.personaById('0')).toMatchObject({
      name: 'Anna Beck',
      stance: 'supportive',
      contestedQuestion: 'Soll die Pflicht kommen?',
    })
  })

  it('parst contested_question als Contract-Objekt mit origin=none als null', async () => {
    api.profiles.mockResolvedValue(profiles)
    api.config.mockResolvedValue({
      success: true,
      data: {
        contested_question: {
          statement: null,
          origin: 'none',
          absence_reason: 'Keine strittige Frage',
        },
        agent_configs: [],
      },
    })
    const personas = setup()
    await flush()
    expect(personas.error.value).toBeNull()
    expect(personas.contestedQuestion.value).toBeNull()
  })

  it('lehnt einen dritten contested_question-Typ als Vertragsverstoß ab', async () => {
    api.profiles.mockResolvedValue(profiles)
    api.config.mockResolvedValue({
      success: true,
      data: {
        contested_question: { origin: 'user', other: 1 },
        agent_configs: [],
      },
    })
    const personas = setup()
    await flush()
    expect(personas.error.value).toContain('Konfiguration')
    expect(personas.contestedQuestion.value).toBeNull()
  })
})
