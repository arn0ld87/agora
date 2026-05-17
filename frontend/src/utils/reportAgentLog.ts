export interface AgentLogEntry {
  ts: string
  stage: string
  action: string
  title: string
  subtitle: string
  body: string
  elapsed: number | undefined
  [key: string]: unknown
}

const SENSITIVE_KEY_PATTERN = /token|key|secret|auth|password|credential|ticket|cookie|header/i
const REDACTED = '[redacted]'

function redactParamValue(key: string, value: unknown): string {
  if (SENSITIVE_KEY_PATTERN.test(key)) return REDACTED
  const str = typeof value === 'string' ? value : JSON.stringify(value)
  return str.length > 80 ? str.slice(0, 80) + '…' : str
}

function parseAgentObject(raw: unknown): Record<string, unknown> | null {
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw) as Record<string, unknown>
    } catch {
      return { action: 'raw', message: raw }
    }
  }
  if (raw && typeof raw === 'object') return raw as Record<string, unknown>
  return null
}

export function parseAgentEntry(raw: unknown): AgentLogEntry | null {
  const obj = parseAgentObject(raw)
  if (!obj) return null
  const ts = obj.timestamp ? String(obj.timestamp).slice(11, 19) : ''
  const stage = (obj.stage as string) || ''
  const action = (obj.action as string) || ''
  const d = (obj.details as Record<string, unknown>) || {}
  let title = action.replace(/_/g, ' ')
  let subtitle = ''
  let body = ''

  if (action === 'tool_call') {
    title = `TOOL → ${(obj.tool_name as string) || (d.tool_name as string) || '?'}`
    const params = (d.parameters as Record<string, unknown>) || {}
    subtitle = Object.entries(params).map(([k, v]) => `${k}=${redactParamValue(k, v)}`).join('  ')
  } else if (action === 'tool_result') {
    title = `← ${(obj.tool_name as string) || (d.tool_name as string) || '?'}`
    subtitle = `${(d.result_length as number) || 0} chars`
  } else if (action === 'llm_response') {
    title = 'LLM'
    subtitle = `iter ${d.iteration ?? ''} · tool_calls=${d.has_tool_calls} · final=${d.has_final_answer}`
    body = (d.response as string) || ''
  } else if (action === 'section_start') {
    title = `▶ Section ${obj.section_index ?? ''}: ${(obj.section_title as string) || (d.message as string) || ''}`
  } else if (action === 'section_complete') {
    title = `✓ Section ${obj.section_index ?? ''}`
    subtitle = (d.message as string) || ''
  } else if (action === 'planning_complete') {
    title = 'PLAN'
    const outline = ((d.outline as Record<string, unknown>)?.sections as unknown[]) || []
    subtitle = `${outline.length} sections`
    body = (d.summary as string) || ''
  } else if (action === 'error') {
    title = '⚠ ERROR'
    subtitle = (d.message as string) || (d.error as string) || ''
  }
  return {
    ts,
    stage,
    action,
    title,
    subtitle,
    body,
    elapsed: obj.elapsed_seconds as number | undefined,
  }
}
