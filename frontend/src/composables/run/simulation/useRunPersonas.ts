/**
 * Persona-Zuordnung für die Feed-Oberfläche (Etappe 4, #1801).
 *
 * Lädt Profile und Konfiguration eines Laufs und beantwortet
 * `personaById(personaId)` mit Name, Rolle, Bio, Haltung und Streitfrage.
 *
 * Zuordnung der `persona_id` eines Beitrags (belegt am Backend):
 * - `persona_id` = `str(agent_id)` des Beitrags, und `agent_id` ist die
 *   POSITION des Profils in der Profildatei (OASIS liest `user_id` nicht):
 *   backend/scripts/run_parallel_simulation.py:482,
 *   backend/app/services/simulation_agent_identity.py:5-21.
 * - Das Profil an dieser Position trägt unter `user_id` die Nummer des Agenten
 *   in der Konfiguration; sie entspricht `agent_configs[].agent_id`. Die
 *   gespeicherte Konfiguration ist nicht auf OASIS-Positionen umgeschrieben
 *   (das geschieht erst im Runner, `align_config_to_profiles`). Fehlen Profile
 *   (abgelehnte Personas), weichen Position und `agent_id` darum ab.
 * - Deshalb: Profil per Position, Haltung über `profile.user_id` →
 *   `agent_configs[].agent_id`. Fehlt `user_id` oder der Konfigurationseintrag,
 *   ist `stance` `null` — es wird nichts geraten.
 * Gelesen wird die Reddit-Profilliste (`getSimulationProfiles`, Standard),
 * wie es auch der Runner tut.
 */
import { computed, ref, toValue, watch, type ComputedRef, type Ref } from 'vue'
import { z } from 'zod'
import { getSimulationConfig, getSimulationProfiles } from '@/api/simulation'

const ProfileSchema = z
  .object({
    user_id: z.union([z.number(), z.string()]).nullable().optional(),
    username: z.string().optional(),
    name: z.string().nullable().optional(),
    bio: z.string().nullable().optional(),
    profession: z.string().nullable().optional(),
  })
  .passthrough()

const ProfilesEnvelopeSchema = z.object({
  success: z.literal(true),
  data: z.object({ profiles: z.array(z.unknown()) }).passthrough(),
})

const AgentConfigSchema = z
  .object({
    agent_id: z.union([z.number(), z.string()]),
    stance: z.string().nullable().optional(),
  })
  .passthrough()

const ConfigEnvelopeSchema = z.object({
  success: z.literal(true),
  data: z
    .object({
      contested_question: z.string().nullable().optional(),
      agent_configs: z.array(z.unknown()).optional(),
    })
    .passthrough(),
})

export interface RunPersona {
  personaId: string
  name: string
  username: string | null
  /** `profession` des Profils, sonst null. */
  role: string | null
  bio: string | null
  /** `agent_configs[].stance`; null, wenn keine belastbare Zuordnung besteht. */
  stance: string | null
  /** `config.contested_question` des Laufs, sonst null. */
  contestedQuestion: string | null
}

export interface UseRunPersonasReturn {
  loading: Readonly<Ref<boolean>>
  /** Sichtbare Fehlermeldung (Profile und/oder Konfiguration), sonst `null`. */
  error: Readonly<Ref<string | null>>
  /** Streitfrage des Laufs, auch ohne Persona. */
  contestedQuestion: ComputedRef<string | null>
  /** Persona zur `persona_id` eines Beitrags oder null, wenn kein Profil dort liegt. */
  personaById: (personaId: string) => RunPersona | null
  /** Alle Personen des Laufs in Profilreihenfolge (`personaId` = Position); für Auswahllisten. */
  personas: ComputedRef<RunPersona[]>
  reload: () => Promise<void>
}

type Profile = z.infer<typeof ProfileSchema>
type AgentConfig = z.infer<typeof AgentConfigSchema>

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

function asNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isInteger(n) ? n : null
}

/** Profile und Konfiguration eines Laufs; `personaById` löst Beitragsautoren auf. */
export function useRunPersonas(simulationId: Ref<string> | string): UseRunPersonasReturn {
  const profiles = ref<Profile[]>([])
  const agentConfigs = ref<AgentConfig[]>([])
  const question = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  let token = 0

  async function reload(): Promise<void> {
    const id = toValue(simulationId)
    if (!id) return
    const mine = ++token
    loading.value = true
    error.value = null
    const [profileResult, configResult] = await Promise.allSettled([
      getSimulationProfiles(id),
      getSimulationConfig(id),
    ])
    if (mine !== token) return

    const problems: string[] = []

    if (profileResult.status === 'rejected') {
      problems.push(`Profile: ${message(profileResult.reason)}`)
      profiles.value = []
    } else {
      const env = ProfilesEnvelopeSchema.safeParse(profileResult.value)
      if (!env.success) {
        problems.push('Profile: Antwort entspricht nicht dem Vertrag')
        profiles.value = []
      } else {
        const parsed: Profile[] = []
        let invalid = 0
        for (const entry of env.data.data.profiles) {
          const p = ProfileSchema.safeParse(entry)
          if (p.success) parsed.push(p.data)
          else invalid += 1
        }
        // Die Position zählt: ein verworfener Eintrag verschöbe alle folgenden.
        if (invalid > 0) {
          problems.push(`Profile: ${invalid} Einträge entsprechen nicht dem Vertrag`)
          profiles.value = []
        } else {
          profiles.value = parsed
        }
      }
    }

    if (configResult.status === 'rejected') {
      problems.push(`Konfiguration: ${message(configResult.reason)}`)
      agentConfigs.value = []
      question.value = null
    } else {
      const env = ConfigEnvelopeSchema.safeParse(configResult.value)
      if (!env.success) {
        problems.push('Konfiguration: Antwort entspricht nicht dem Vertrag')
        agentConfigs.value = []
        question.value = null
      } else {
        question.value = env.data.data.contested_question ?? null
        agentConfigs.value = (env.data.data.agent_configs ?? []).flatMap((entry) => {
          const c = AgentConfigSchema.safeParse(entry)
          return c.success ? [c.data] : []
        })
      }
    }

    error.value = problems.length > 0 ? problems.join('; ') : null
    loading.value = false
  }

  function personaById(personaId: string): RunPersona | null {
    const position = asNumber(personaId)
    if (position === null || position < 0) return null
    const profile = profiles.value[position]
    if (!profile) return null

    const configId = asNumber(profile.user_id)
    const config =
      configId === null
        ? undefined
        : agentConfigs.value.find((c) => asNumber(c.agent_id) === configId)

    return {
      personaId,
      name: profile.name || profile.username || `Agent ${personaId}`,
      username: profile.username ?? null,
      role: profile.profession || null,
      bio: profile.bio || null,
      stance: config?.stance ?? null,
      contestedQuestion: question.value,
    }
  }

  watch(
    () => toValue(simulationId),
    () => {
      profiles.value = []
      agentConfigs.value = []
      question.value = null
      void reload()
    },
  )
  void reload()

  return {
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    contestedQuestion: computed(() => question.value),
    personaById,
    personas: computed(() =>
      profiles.value.flatMap((_, position) => {
        const p = personaById(String(position))
        return p ? [p] : []
      }),
    ),
    reload,
  }
}
