/**
 * Temporarily store files and requirements to be uploaded
 * Used to immediately navigate after clicking Start Engine on home page, API call is made on Process page
 */
import { reactive } from 'vue'

interface PendingUploadState {
  files: File[]
  simulationRequirement: string
  llmProfileId: string | null
  isPending: boolean
}

const state = reactive<PendingUploadState>({
  files: [],
  simulationRequirement: '',
  llmProfileId: null,
  isPending: false
})

export function setPendingUpload(
  files: File[],
  requirement: string,
  llmProfileId: string | null = null,
): void {
  state.files = files
  state.simulationRequirement = requirement
  state.llmProfileId = llmProfileId
  state.isPending = true
}

export function getPendingUpload(): PendingUploadState {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    llmProfileId: state.llmProfileId,
    isPending: state.isPending,
  }
}

export function clearPendingUpload(): void {
  state.files = []
  state.simulationRequirement = ''
  state.llmProfileId = null
  state.isPending = false
}

export default state
