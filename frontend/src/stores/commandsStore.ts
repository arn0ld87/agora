/**
 * commandsStore — Pinia Store fuer Cmd+K Command-Palette
 *
 * Liefert statische Nav-Commands (alle Top-Level-Routes) und
 * dynamische Commands aus laufenden/offenen Simulationen sowie
 * recent abgeschlossenen Reports (aus useRunsPolling).
 *
 * Lifecycle:
 *   bindDynamicCommands(router) — einmalig in AppShell.vue onMounted;
 *   beobachtet runs via watch und haelt dynamicCommands reaktiv.
 */
import { defineStore } from 'pinia'
import { ref, watch, computed } from 'vue'
import type { Router } from 'vue-router'
import { useCommandPalette } from '@/composables/useCommandPalette'
import { useRunsPolling } from '@/composables/useRunsPolling'
import type { RunDetail } from '@/contracts/runsContract'
import { t } from '@/i18n/translate'

export interface Command {
  id: string
  label: string
  icon?: string
  group: 'nav' | 'sim' | 'report' | 'recent'
  keywords?: string[]
  action: () => void
}

// Statische Nav-Commands, unabhaengig von einer Router-Instanz definierbar.
// action wird beim Aufruf von buildStaticCommands() mit router.push verdrahtet.
interface StaticCommandDef {
  id: string
  labelDe: string
  labelEn: string
  routeName: string
  group: Command['group']
}

const STATIC_DEFS: StaticCommandDef[] = [
  { id: 'nav:dashboard',              labelDe: 'Dashboard',      labelEn: 'Dashboard',      routeName: 'Dashboard',             group: 'nav' },
  { id: 'nav:runs',                   labelDe: 'Runs',            labelEn: 'Runs',            routeName: 'Runs',                  group: 'nav' },
  { id: 'nav:history',                labelDe: 'Historie',        labelEn: 'History',         routeName: 'HistoryV4',             group: 'nav' },
  { id: 'nav:settings-general',       labelDe: 'Einstellungen — Allgemein',    labelEn: 'Settings — General',       routeName: 'SettingsGeneral',       group: 'nav' },
  { id: 'nav:settings-integrations',  labelDe: 'Einstellungen — Integrationen', labelEn: 'Settings — Integrations',  routeName: 'SettingsIntegrations',  group: 'nav' },
  { id: 'nav:settings-llm-routing',   labelDe: 'Einstellungen — LLM-Routing', labelEn: 'Settings — LLM Routing',   routeName: 'SettingsLlmRouting',    group: 'nav' },
  { id: 'nav:settings-llm-providers', labelDe: 'Einstellungen — LLM-Provider', labelEn: 'Settings — LLM Providers', routeName: 'SettingsLlmProviders',  group: 'nav' },
  { id: 'nav:settings-api-keys',      labelDe: 'Einstellungen — API-Schlüssel', labelEn: 'Settings — API Keys',     routeName: 'SettingsApiKeys',       group: 'nav' },
  { id: 'nav:settings-audit-logs',    labelDe: 'Einstellungen — Audit-Logs',  labelEn: 'Settings — Audit Logs',    routeName: 'SettingsAuditLogs',     group: 'nav' },
  { id: 'nav:settings-users-teams',   labelDe: 'Einstellungen — Nutzer & Teams', labelEn: 'Settings — Users & Teams', routeName: 'SettingsUsersTeams',  group: 'nav' },
]

/** Leitet einen lesbaren Label aus einem RunDetail ab. */
function runLabel(run: RunDetail): string {
  const docName = run.summary?.document_name
  if (docName) return docName
  // entity_id kann UUID sein — kuerzen auf erste 8 Zeichen
  return run.entity_id.slice(0, 8)
}

/** Gibt den report_id aus linked_ids oder artifacts zurück, falls vorhanden. */
function extractReportId(run: RunDetail): string | null {
  const linked = run.linked_ids as Record<string, unknown>
  if (typeof linked['report_id'] === 'string') return linked['report_id']
  const arts = run.artifacts as Record<string, unknown>
  if (typeof arts['report_id'] === 'string') return arts['report_id']
  return null
}

/** Ob ein Run als "aktiv/offen" gilt (sim-Command). */
const ACTIVE_STATUSES = new Set(['pending', 'processing', 'paused'])
/** Ob ein Run in Recent-Reports erscheinen soll (nur completed mit report). */
const COMPLETED_STATUS = 'completed'
/** Max. Anzahl Recent-Report-Commands. */
const MAX_RECENT_REPORTS = 5

export const useCommandsStore = defineStore('commands', () => {
  const { recent } = useCommandPalette()

  // Dynamische Commands (reaktiv, wird durch bindDynamicCommands befuellt).
  const dynamicCommands = ref<Command[]>([])
  let stopWatch: (() => void) | null = null
  let stopPolling: (() => void) | null = null

  /**
   * Baut statische Commands und verdrahtet router.push.
   * Wird einmalig in CommandPalette.vue beim Setup aufgerufen.
   */
  function buildStaticCommands(router: Router, locale: 'de' | 'en' = 'de'): Command[] {
    return STATIC_DEFS.map((def) => ({
      id: def.id,
      label: locale === 'en' ? def.labelEn : def.labelDe,
      group: def.group,
      action: () => {
        router.push({ name: def.routeName }).catch(() => {
          // Navigation-Fehler bei bereits aktiver Route ignorieren
        })
      },
    }))
  }

  /**
   * Verdrahtet dynamische Commands aus laufenden/offenen Simulationen
   * und recent abgeschlossenen Reports.
   *
   * Aufgerufen einmalig in AppShell.vue::onMounted.
   * Beobachtet den runs-Array via watch — Commands werden reaktiv aktualisiert.
   */
  function bindDynamicCommands(router: Router): void {
    // Verhindere doppelte Watches
    if (stopWatch) return

    const { runs, start, stop } = useRunsPolling(10_000)

    // Polling starten (no-op wenn bereits laufend).
    // Promise.resolve() macht den Aufruf robust gegen gemockte start()-Varianten
    // die keinen Promise zurückgeben (z.B. in vitest-Umgebungen).
    Promise.resolve(start()).catch(() => {
      // Polling-Start-Fehler (z.B. ohne API) ignorieren
    })
    stopPolling = stop

    stopWatch = watch(
      runs,
      (currentRuns) => {
        const cmds: Command[] = []

        for (const run of currentRuns) {
          if (ACTIVE_STATUSES.has(run.status)) {
            const label = runLabel(run)
            const statusKey =
              run.status === 'processing'
                ? 'cmd.dynamic.statusRunning'
                : run.status === 'paused'
                  ? 'cmd.dynamic.statusPaused'
                  : 'cmd.dynamic.statusPending'
            const statusLabel = t(statusKey)
            cmds.push({
              id: `sim:${run.run_id}`,
              label: t('cmd.dynamic.runLabel', { name: `${label} (${statusLabel})` }),
              group: 'sim',
              keywords: [run.run_id, run.entity_id, label, 'simulation', 'lauf', 'live', run.status],
              action: () => {
                router.push({
                  name: 'StepSimulation',
                  params: { simulationId: run.entity_id },
                }).catch(() => {})
              },
            })
          }
        }

        // Recent Reports: abgeschlossene Runs mit report_id, max 5
        let reportCount = 0
        for (const run of currentRuns) {
          if (reportCount >= MAX_RECENT_REPORTS) break
          if (run.status !== COMPLETED_STATUS) continue
          const reportId = extractReportId(run)
          if (!reportId) continue
          const label = runLabel(run)
          cmds.push({
            id: `report:${reportId}`,
            label: t('cmd.dynamic.reportLabel', { name: label }),
            group: 'report',
            keywords: [reportId, run.run_id, label, 'report', 'bericht', 'ergebnis'],
            action: () => {
              router.push({
                name: 'StepReport',
                params: { reportId },
              }).catch(() => {})
            },
          })
          reportCount++
        }

        dynamicCommands.value = cmds
      },
      { deep: true },
    )
  }

  /**
   * Bereinigt den Watch (z.B. beim Testen oder bei Komponenten-Teardown).
   */
  function unbindDynamicCommands(): void {
    stopWatch?.()
    stopWatch = null
    stopPolling?.()
    stopPolling = null
    dynamicCommands.value = []
  }

  /**
   * Alle Commands: dynamisch (Sims + Reports) zuerst, dann statisch.
   * Wird in CommandPalette als kombinierter Pool verwendet.
   */
  const allDynamic = computed<Command[]>(() => dynamicCommands.value)

  /**
   * Gibt alle Commands zurueck: Recent zuerst (nach recent-Stack sortiert),
   * dann restliche statische Commands.
   */
  function getOrdered(staticCmds: Command[]): Command[] {
    if (recent.value.length === 0) return staticCmds
    const recentSet = new Set(recent.value)
    const recentCmds: Command[] = []
    for (const id of recent.value) {
      const cmd = staticCmds.find((c) => c.id === id)
      if (cmd) recentCmds.push({ ...cmd, group: 'recent' as const })
    }
    const rest = staticCmds.filter((c) => !recentSet.has(c.id))
    return [...recentCmds, ...rest]
  }

  /**
   * Filtert Commands nach Query-String (case-insensitiv, Label + ID + Keywords).
   */
  function filter(cmds: Command[], query: string): Command[] {
    const q = query.trim().toLowerCase()
    if (!q) return cmds
    return cmds.filter((c) => {
      if (c.label.toLowerCase().includes(q)) return true
      if (c.id.toLowerCase().includes(q)) return true
      if (c.keywords?.some((k) => k.toLowerCase().includes(q))) return true
      return false
    })
  }

  return {
    recent,
    dynamicCommands: allDynamic,
    buildStaticCommands,
    bindDynamicCommands,
    unbindDynamicCommands,
    getOrdered,
    filter,
  }
})
