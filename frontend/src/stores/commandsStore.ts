/**
 * commandsStore — Pinia Store fuer Cmd+K Command-Palette
 *
 * Liefert statische Nav-Commands (alle Top-Level-Routes) und
 * injiziert dynamische Recent-Commands aus dem useCommandPalette-Composable.
 *
 * Dynamische Sim-Commands (offene Runs) koennen spaeter via inject(openRunsRef) erweiterbar sein.
 * Hier: statische Commands + recent-Ordering.
 */
import { defineStore } from 'pinia'
import { computed } from 'vue'
import type { Router } from 'vue-router'
import { useCommandPalette } from '@/composables/useCommandPalette'

export interface Command {
  id: string
  label: string
  icon?: string
  group: 'nav' | 'sim' | 'report' | 'recent'
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

export const useCommandsStore = defineStore('commands', () => {
  const { recent } = useCommandPalette()

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

  // all ist ein computed, der _baseCommands und recent-Ordering kombiniert.
  // Da router erst beim Komponent-Setup bekannt ist, speichern wir
  // den Ref auf die gebuildete Liste in einem reaktiven Ref.
  const _static = computed<Command[]>(() => [])

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
   * Filtert Commands nach Query-String (case-insensitiv, Label-Suche).
   */
  function filter(cmds: Command[], query: string): Command[] {
    const q = query.trim().toLowerCase()
    if (!q) return cmds
    return cmds.filter((c) => c.label.toLowerCase().includes(q) || c.id.toLowerCase().includes(q))
  }

  return {
    _static,
    recent,
    buildStaticCommands,
    getOrdered,
    filter,
  }
})
