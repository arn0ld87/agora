export interface LlmRuntimePayload {
  provider: 'google' | 'openai' | 'custom_openai'
  api_key: string
  base_url?: string
}
