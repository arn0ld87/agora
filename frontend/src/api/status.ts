import service from './index'
import type { SystemStatusResponse } from '../contracts/systemStatusContract'

export interface SystemStatusEnvelope {
  success: boolean
  data?: SystemStatusResponse
  // /api/status nutzt json_success(**extra), wodurch das Envelope flach ist:
  // { success: true, backend: {...}, neo4j: {...}, ... }
  // Wir akzeptieren beide Formen und entpacken im Composable.
  backend?: unknown
  neo4j?: unknown
  ollama?: unknown
  disk?: unknown
  gpu?: unknown
  timestamp?: string
  [key: string]: unknown
}

export const getSystemStatus = (): Promise<SystemStatusEnvelope> =>
  service.get('/api/status')
