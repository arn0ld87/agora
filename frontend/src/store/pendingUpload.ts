/**
 * Temporarily store files and requirements to be uploaded
 * Used to immediately navigate after clicking Start Engine on home page, API call is made on Process page
 */
import { reactive } from 'vue'

interface PendingUploadState {
  files: File[]
  simulationRequirement: string
  llmProfileId: string | null
  numAgents: number
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
