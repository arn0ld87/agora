/**
 * Parser für source_id_anchor-Strings (Sub-Slice 12 Backend-Vertrag).
 *
 * Bekannte Formate:
 *   - "agent-log-{logId}#entry-{entryId}"
 *   - "agent-log-{logId}"          (ohne entry-Suffix)
 *   - "web:{url}"                   (optional mit #:~:text=...)
 *   - "kg:entity:{uuid}"
 */
export type ParsedAnchor =
  | { kind: 'agent-log'; logId: string; entryId: string | null }
  | { kind: 'web'; url: string }
  | { kind: 'kg'; payload: string }
  | { kind: 'unknown'; raw: string }

export function parseSourceAnchor(anchor: string | null | undefined): ParsedAnchor | null {
  if (!anchor || typeof anchor !== 'string') return null

  const agentLogWithEntry = anchor.match(/^agent-log-([^#]+)#entry-(.+)$/)
  if (agentLogWithEntry) {
    return { kind: 'agent-log', logId: agentLogWithEntry[1], entryId: agentLogWithEntry[2] }
  }

  const agentLogOnly = anchor.match(/^agent-log-(.+)$/)
  if (agentLogOnly && !agentLogOnly[1].includes('#')) {
    return { kind: 'agent-log', logId: agentLogOnly[1], entryId: null }
  }

  const webMatch = anchor.match(/^web:(https?:\/\/.+)$/)
  if (webMatch) {
    return { kind: 'web', url: webMatch[1] }
  }

  const kgMatch = anchor.match(/^kg:(.+)$/)
  if (kgMatch) {
    return { kind: 'kg', payload: kgMatch[1] }
  }

  return { kind: 'unknown', raw: anchor }
}

/**
 * Deterministische Entry-ID aus dem AgentLogEntry-Objekt — wird als DOM-id im
 * Agent-Log-Pane gesetzt, damit ein klickbarer Anchor `agent-log-X#entry-Y`
 * vom Backend auf den richtigen Entry zeigen kann.
 *
 * Heuristik: timestamp + action + tool_name + section_index. Fällt auf
 * "unknown" zurück, wenn nichts gesetzt ist (sollte praktisch nie passieren).
 */
export function entryAnchorId(entry: Record<string, unknown> | null | undefined): string {
  if (!entry || typeof entry !== 'object') return 'unknown'
  const ts = String(entry.timestamp ?? entry.ts ?? '').replace(/[^a-zA-Z0-9-]/g, '')
  const action = String(entry.action ?? '').replace(/[^a-zA-Z0-9_]/g, '')
  const tool = String(entry.tool_name ?? '').replace(/[^a-zA-Z0-9_]/g, '')
  const sec = String(entry.section_index ?? '')
  const parts = [ts, action, tool, sec].filter(Boolean)
  return parts.length ? parts.join('-') : 'unknown'
}
