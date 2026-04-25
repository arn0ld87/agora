import { ref } from 'vue'

/**
 * Composable for the timestamped log strip rendered next to every workspace
 * view (Main / Simulation / SimulationRun / Report / Interaction).
 *
 * Replaces five identical addLog/systemLogs implementations with one source
 * of truth. The cap is configurable per call-site so we keep the existing
 * 100/200-line behaviour without behavioural surprises.
 */
export function useSystemLog({ cap = 200 } = {}) {
  const systemLogs = ref([])

  function addLog(msg) {
    const now = new Date()
    const time = now.toTimeString().slice(0, 8) + '.' + String(now.getMilliseconds()).padStart(3, '0')
    systemLogs.value.push({ time, msg })
    if (systemLogs.value.length > cap) systemLogs.value.shift()
  }

  function clearLog() {
    systemLogs.value = []
  }

  return { systemLogs, addLog, clearLog }
}
