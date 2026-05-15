export interface LlmRuntimePayload {
  provider: 'google' | 'openai' | 'custom_openai'
  /** Wenn nicht gesetzt: Backend löst Key via Settings-DB auf (Smoke-Fix Slice 04). */
  api_key?: string
  base_url?: string
}
