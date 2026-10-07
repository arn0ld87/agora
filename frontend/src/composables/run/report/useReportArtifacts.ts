/**
 * Kennzahlen-Artefakte eines Berichts (Etappe 5, #1804): Belegdichte
 * (`evidence-density`) und Positionierungsquote (`stance-analysis`).
 *
 * Jeder Endpunkt hat drei sichtbare Zustände, nie einen stillen Leerzustand:
 *   ok        200 mit `data`
 *   unsaved   404: die Fassung ist älter als das Artefakt, es wurde nicht gespeichert
 *   omitted   200 mit `artifact_omitted`: die Datei verletzt den Vertrag
 * dazu `idle` (keine Fassung / Bericht läuft), `loading` und `failed` (Transport
 * oder Vertragsbruch der Antwort). Antworten laufen über `api/report.ts` durch Zod.
 */
import { computed, ref, watch, type Ref } from 'vue'
import { ApiError } from '@/api/envelope'
import {
  getReportEvidenceDensity,
  getReportStanceAnalysis,
  type EvidenceDensityEnvelope,
  type StanceAnalysisEnvelope,
} from '@/api/report'
import type { EvidenceDensity } from '@/contracts/evidenceDensityContract'
import type { ReportArtifactOmission } from '@/contracts/reportArtifactContract'
import type { StanceAnalysis } from '@/contracts/stanceAnalysisContract'

export type ArtifactState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ok'; data: T }
  | { status: 'unsaved' }
  | { status: 'omitted'; omission: ReportArtifactOmission }
  | { status: 'failed'; reason: string }

export interface ReportArtifactsApi {
  getDensity: (reportId: string) => Promise<EvidenceDensityEnvelope>
  getStance: (reportId: string) => Promise<StanceAnalysisEnvelope>
}

export interface UseReportArtifactsOptions {
  /** Gewählte Fassung; `null` heißt: nichts zu laden. */
  reportId: () => string | null
  /** Nur fertige Fassungen haben Artefakte. */
  enabled: () => boolean
  api?: Partial<ReportArtifactsApi>
}

function describe(err: unknown): string {
  return err instanceof Error && err.message ? err.message : String(err)
}

/** Zustand aus einer Antwort; der Fehler-Envelope `success: false` mit `not_found` ist ein 404. */
export function toArtifactState<T>(
  res: { success: boolean; data?: T; artifact_omitted?: ReportArtifactOmission; code?: string; error?: string },
): ArtifactState<T> {
  if (res.success !== true) {
    if (res.code === 'not_found') return { status: 'unsaved' }
    return { status: 'failed', reason: res.error || res.code || 'unbekannter Fehler' }
  }
  if (res.artifact_omitted) return { status: 'omitted', omission: res.artifact_omitted }
  if (res.data !== undefined) return { status: 'ok', data: res.data }
  return { status: 'failed', reason: 'leere Antwort' }
}

function fromError<T>(err: unknown): ArtifactState<T> {
  if (err instanceof ApiError && err.status === 404) return { status: 'unsaved' }
  return { status: 'failed', reason: describe(err) }
}

export function useReportArtifacts(options: UseReportArtifactsOptions): {
  density: Ref<ArtifactState<EvidenceDensity>>
  stance: Ref<ArtifactState<StanceAnalysis>>
  reload: () => Promise<void>
} {
  const api: ReportArtifactsApi = {
    getDensity: getReportEvidenceDensity,
    getStance: getReportStanceAnalysis,
    ...options.api,
  }
  const density = ref<ArtifactState<EvidenceDensity>>({ status: 'idle' }) as Ref<ArtifactState<EvidenceDensity>>
  const stance = ref<ArtifactState<StanceAnalysis>>({ status: 'idle' }) as Ref<ArtifactState<StanceAnalysis>>
  let seq = 0

  async function reload(): Promise<void> {
    const mine = ++seq
    const id = options.reportId()
    if (!id || !options.enabled()) {
      density.value = { status: 'idle' }
      stance.value = { status: 'idle' }
      return
    }
    density.value = { status: 'loading' }
    stance.value = { status: 'loading' }
    const [d, s] = await Promise.all([
      api.getDensity(id).then(
        (res) => toArtifactState<EvidenceDensity>(res),
        (err) => fromError<EvidenceDensity>(err),
      ),
      api.getStance(id).then(
        (res) => toArtifactState<StanceAnalysis>(res),
        (err) => fromError<StanceAnalysis>(err),
      ),
    ])
    if (mine !== seq) return
    density.value = d
    stance.value = s
  }

  const key = computed(() => `${options.reportId() ?? ''}|${options.enabled() ? 1 : 0}`)
  watch(key, () => void reload(), { immediate: true })

  return { density, stance, reload }
}
