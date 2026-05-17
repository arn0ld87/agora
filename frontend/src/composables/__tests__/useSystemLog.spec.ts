import { describe, it, expect, beforeEach } from 'vitest'
import { useSystemLog } from '../useSystemLog'

describe('useSystemLog', () => {
  describe('addLog', () => {
    it('füllt systemLogs mit { time, msg }', () => {
      const { systemLogs, addLog } = useSystemLog()

      addLog('erster Eintrag')

      expect(systemLogs.value).toHaveLength(1)
      expect(systemLogs.value[0].msg).toBe('erster Eintrag')
      expect(typeof systemLogs.value[0].time).toBe('string')
    })

    it('time matched HH:MM:SS.mmm-Format', () => {
      const { systemLogs, addLog } = useSystemLog()

      addLog('timestamp-check')

      expect(systemLogs.value[0].time).toMatch(/^\d{2}:\d{2}:\d{2}\.\d{3}$/)
    })

    it('mehrere Einträge werden angehängt', () => {
      const { systemLogs, addLog } = useSystemLog()

      addLog('a')
      addLog('b')
      addLog('c')

      expect(systemLogs.value).toHaveLength(3)
      expect(systemLogs.value.map((e) => e.msg)).toEqual(['a', 'b', 'c'])
    })
  })

  describe('Cap-Enforcement', () => {
    it('bei cap=3 und 4 addLog-Calls bleibt Länge 3 (FIFO)', () => {
      const { systemLogs, addLog } = useSystemLog({ cap: 3 })

      addLog('eins')
      addLog('zwei')
      addLog('drei')
      addLog('vier')

      expect(systemLogs.value).toHaveLength(3)
      // Ältester Eintrag ('eins') wurde per FIFO entfernt
      expect(systemLogs.value[0].msg).toBe('zwei')
      expect(systemLogs.value[2].msg).toBe('vier')
    })

    it('ohne cap-Angabe gilt Default 200: 3 Calls → length 3, kein Drop', () => {
      const { systemLogs, addLog } = useSystemLog()

      addLog('x')
      addLog('y')
      addLog('z')

      expect(systemLogs.value).toHaveLength(3)
    })

    it('negativer Case: cap=1 verwirft alles außer dem neuesten', () => {
      const { systemLogs, addLog } = useSystemLog({ cap: 1 })

      addLog('alt')
      addLog('neu')

      expect(systemLogs.value).toHaveLength(1)
      expect(systemLogs.value[0].msg).toBe('neu')
    })
  })

  describe('clearLog', () => {
    it('setzt systemLogs auf []', () => {
      const { systemLogs, addLog, clearLog } = useSystemLog()

      addLog('wird gelöscht')
      addLog('wird auch gelöscht')
      clearLog()

      expect(systemLogs.value).toEqual([])
    })

    it('clearLog auf leerem Log ist idempotent', () => {
      const { systemLogs, clearLog } = useSystemLog()

      clearLog()

      expect(systemLogs.value).toEqual([])
    })
  })

  describe('Isolation: jede Instanz hat eigenen State', () => {
    it('zwei useSystemLog-Instanzen teilen keinen State', () => {
      const { systemLogs: logsA, addLog: addA } = useSystemLog()
      const { systemLogs: logsB } = useSystemLog()

      addA('nur in A')

      expect(logsA.value).toHaveLength(1)
      expect(logsB.value).toHaveLength(0)
    })
  })
})
