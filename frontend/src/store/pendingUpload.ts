/**
 * Temporarily store files and requirements to be uploaded
 * Used to immediately navigate after clicking Start Engine on home page, API call is made on Process page
 *
 * Der Store gehört Schritt 1 und trägt genau das, was der Ontologie-Upload
 * braucht — allen voran die Dateien, die nicht serialisierbar sind. Er wird
 * nach dem Upload geleert (``useGraphBuildPipeline`` → ``clearPendingUpload``).
 *
 * Was Schritt 3 braucht, gehört deshalb NICHT hierher: Rundenzahl und
 * Run-Budget reisen über die Route-Query (``contracts/runParamsQuery``). Vor
 * Issue #1234 lag das Budget hier und erreichte den Simulationsstart nie, weil
 * Schritt 1 es zwischendurch weggeräumt hatte.
 */
import { reactive } from 'vue'

interface PendingUploadState {
  files: File[]
  simulationRequirement: string
  llmProfileId: string | null
  numAgents: number
  /** Nur für den Upload-Payload in Schritt 1. Der Simulationsstart liest ``maxRounds`` aus der Query. */
  numRounds: number
  isPending: boolean
}

const state = reactive<PendingUploadState>({
  files: [],
  simulationRequirement: '',
  llmProfileId: null,
  numAgents: 30,
  numRounds: 10,
  isPending: false
})

export function setPendingUpload(
  files: File[],
  requirement: string,
  llmProfileId: string | null = null,
  numAgents = 30,
  numRounds = 10,
): void {
  state.files = files
  state.simulationRequirement = requirement
  state.llmProfileId = llmProfileId
  state.numAgents = numAgents
  state.numRounds = numRounds
  state.isPending = true
}

export function getPendingUpload(): PendingUploadState {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    llmProfileId: state.llmProfileId,
    numAgents: state.numAgents,
    numRounds: state.numRounds,
    isPending: state.isPending,
  }
}

export function clearPendingUpload(): void {
  state.files = []
  state.simulationRequirement = ''
  state.llmProfileId = null
  state.numAgents = 30
  state.numRounds = 10
  state.isPending = false
}

export default state
