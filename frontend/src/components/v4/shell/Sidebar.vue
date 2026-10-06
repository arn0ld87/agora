<template>
  <aside class="sidebar" :class="{ 'sidebar--collapsed': collapsed }">
    <!-- Brand header -->
    <div class="sidebar__brand">
      <AgoraBrand mode="ring" alt="Agora" />
      <span v-if="!collapsed" class="sidebar__wordmark">Agora</span>
    </div>

    <!-- Nav body: Bibliothek, Im Blick, Werkzeuge, dann (mit Abstand statt Trennlinie) System und Einstellungen -->
    <nav class="sidebar__body" :aria-label="t('sidebar.title')">
      <div
        v-for="group in navGroups"
        :key="group.id"
        class="sidebar__group"
        role="group"
        :aria-label="group.title"
      >
        <div v-if="!collapsed" class="sidebar__group-title" aria-hidden="true">{{ group.title }}</div>
        <SidebarItem
          v-for="item in group.items"
          :key="item.id"
          :glyph="item.glyph"
          :label="item.label"
          :to="item.to"
          :count="item.count"
          :current="item.current"
          :collapsed="collapsed"
          @click="handleNavClick"
        />
      </div>

      <p v-if="loadFailed && !collapsed" class="sidebar__notice" role="status">
        {{ t('sidebar.countsError') }}
      </p>

      <div class="sidebar__bottom">
        <SidebarItem
          :label="t('sidebar.system.label')"
          :to="{ name: 'SettingsGeneral' }"
          :tone="systemTone"
          :tooltip="t(`sidebar.system.state.${systemTone}`)"
          :current="false"
          :collapsed="collapsed"
          @click="handleNavClick"
        />

        <!-- Settings group (IA-Matrix: nur wire-Sub-Items). Fuer Besucher ohne
             Betreiber-Zugang bleibt die Gruppe nur auf der Demo-Instanz sichtbar
             (demoPreview) — jede Unterseite ist dort per DemoPreviewFrame
             einsehbar, nur die eigenen Provider-Keys sind editierbar. Ein
             regulaerer JWT-Nutzer ohne Demo-Modus sieht die Gruppe gar nicht,
             da er ohnehin ueberall herausredirected wuerde (#1697).
             Eingeklappt gibt es keine Unterpunkte: ein Symbol fuehrt zur ersten
             Einstellungsseite, alle weiteren erreicht man ausgeklappt. -->
        <template v-if="showSettingsGroup">
          <SidebarItem
            v-if="collapsed"
            icon="settings"
            :label="t('sidebar.settings.label')"
            :to="navSettings[0].to"
            :current="onSettingsRoute"
            collapsed
            @click="handleNavClick"
          />
          <SidebarGroup
            v-else
            group-key="settings"
            :label="t('sidebar.settings.label')"
            icon="settings"
            :active-route-names="settingsRouteNames"
          >
            <template v-for="sub in navSettings" :key="sub.id">
              <RouterLink
                :to="sub.to"
                class="sidebar-sub-item"
                active-class="sidebar-sub-item--active"
                exact-active-class="sidebar-sub-item--active"
                @click="handleNavClick"
              >
                {{ sub.label }}
                <span v-if="!operatorAccess && sub.id !== 'provider-keys'" class="sidebar-sub-item__badge">
                  {{ t('sidebar.settings.previewBadge') }}
                </span>
              </RouterLink>
            </template>
          </SidebarGroup>
        </template>
      </div>
    </nav>

    <!-- Footer collapse toggle -->
    <button
      type="button"
      class="sidebar__footer"
      :aria-label="collapsed ? t('sidebar.footer.expand') : t('sidebar.footer.collapse')"
      @click="emit('collapse-toggle')"
    >
      <Icon :name="collapsed ? 'chevron' : 'arrowL'" :size="14" :stroke="1.6" />
      <span v-if="!collapsed" class="sidebar__footer-label">{{ t('sidebar.footer.collapse') }}</span>
    </button>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useOperatorAccess } from '../../../composables/useOperatorAccess'
import { useDemoPreview } from '../../../composables/useDemoPreview'
import { useLibraryCounts } from '../../../composables/useLibraryCounts'
import { useSidebarSystem } from '../../../composables/useSidebarSystem'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import SidebarItem from './SidebarItem.vue'
import SidebarGroup from './SidebarGroup.vue'
import Icon from './Icon.vue'
import AgoraBrand from '../../brand/AgoraBrand.vue'
import { useShellStore } from '@/stores/shell'
import { MOBILE_MEDIA_QUERY } from '@/constants/breakpoints'

const { t } = useI18n()
const route = useRoute()
// Einstellungen sind Betreiber-Zustand: für Supabase-Nutzer ausgeblendet (#1617).
const operatorAccess = useOperatorAccess()
// Demo-Vorschau (#1697): nur auf der Demo-Instanz sehen Besucher ohne
// Betreiber-Zugang die Gruppe ueberhaupt (als nicht-editierbare Vorschau).
const demoPreview = useDemoPreview()
const showSettingsGroup = computed(() => operatorAccess.value || demoPreview.value)
const shellStore = useShellStore()
const { counts, loadFailed, compareSimulationId } = useLibraryCounts()
const { tone: systemTone } = useSidebarSystem()

function handleNavClick(): void {
  // MOBILE_MEDIA_QUERY (SSoT, Slice 7.3.2) matcht "< MOBILE_BREAKPOINT_PX" —
  // konsistent mit AppShell.vue's Resize-Handler (window.innerWidth >= 768).
  if (window.matchMedia(MOBILE_MEDIA_QUERY).matches) {
    shellStore.closeMobileNav()
  }
}

interface NavItem {
  id: string
  glyph: string
  label: string
  to: RouteLocationRaw
  /** Zaehler; `null` = unbekannt (keine Zahl), `undefined` = der Eintrag hat keinen Zaehler. */
  count?: number | null
  /** Aktiv-Zustand explizit: der Router kennt die Ablage-Filter (Query) nicht. */
  current: boolean
}

interface NavGroup {
  id: string
  title: string
  items: NavItem[]
}

interface NavSettingsItem {
  id: string
  label: string
  to: RouteLocationRaw
}

const props = withDefaults(
  defineProps<{
    collapsed?: boolean
  }>(),
  {
    collapsed: false,
  },
)

const emit = defineEmits<{
  'collapse-toggle': []
}>()

/** Alle Route-Namen, bei denen die Settings-Gruppe als aktiv gilt und auto-oeffnet.
 *  IA-Matrix Slice 7.3: SettingsAuditLogs und SettingsLlmRouting sind nicht in der Sidebar,
 *  muessen hier aber gelistet bleiben, damit ein Aufruf der Hidden-Route (z.B. via
 *  CommandPalette oder Deep-Link) die Gruppe trotzdem auto-oeffnet. */
const settingsRouteNames = [
  'Settings',
  'SettingsGeneral',
  'SettingsIntegrations',
  'SettingsProfile',
  'SettingsApiKeys',
  'SettingsAuditLogs',
  'SettingsLlmRouting',
  'SettingsLlmProviders',
  'SettingsEmbedding',
  // Deep-Link aus dem Demo-Vorschau-Banner: Gruppe muss auch hier auto-oeffnen.
  'WorkspaceProviderKeys',
]

const onSettingsRoute = computed(() =>
  route.matched.some((r) => r.name !== undefined && settingsRouteNames.includes(String(r.name))),
)

const RUN_WORKSPACE_ROUTES = ['RunWorkspace', 'RunOverview', 'RunGraph']

/** Gewaehlte Ansicht der Laeufe-Bibliothek (`?view=`); `null` = alle. */
const runsView = computed<string | null>(() => {
  const raw = route.query.view
  return route.name === 'LibraryRuns' && typeof raw === 'string' ? raw : null
})

/** Art des Objekts auf der alten Ablage-Objektansicht (`/ablage/:kind/:objectId`, Bericht und Personasatz bis Etappe 5/7). */
const shelfObjectKind = computed<string | null>(() =>
  route.name === 'ShelfObject' && typeof route.params.kind === 'string' ? route.params.kind : null,
)

const onRunsSection = computed(
  () =>
    (route.name === 'LibraryRuns' && runsView.value !== 'running' && runsView.value !== 'attention') ||
    route.name === 'NewRun' ||
    route.matched.some((r) => r.name !== undefined && RUN_WORKSPACE_ROUTES.includes(String(r.name))) ||
    shelfObjectKind.value === 'lauf' ||
    shelfObjectKind.value === 'bericht',
)

const onActivitySection = computed(() => route.path === '/activity' || route.path.startsWith('/activity/'))

/**
 * Seitenleiste laut Bauplan 3.1. Jeder Eintrag fuehrt auf eine Adresse der
 * Etappe 2:
 *  - Laeufe → Bibliothek → Laeufe; ein geoeffneter Lauf (`/simulations/…`)
 *    markiert „Laeufe“. Graphen → Graphen-Bibliothek, `/graphs/:projectId`
 *    markiert „Graphen“.
 *  - Personasaetze → bis Etappe 7 die Laeufe-Bibliothek; nie selbst als aktiv
 *    markiert (ausser auf der alten Personasatz-Objektansicht).
 *  - Laeuft gerade / Braucht dich → Laeufe mit `?view=running` bzw.
 *    `?view=attention`.
 *  - Vergleich → Vergleichsansicht, mit dem juengsten Lauf mit Simulation
 *    vorgewaehlt, sobald einer bekannt ist.
 *  - Aktivitaet → Jobs; `/activity/*` markiert „Aktivitaet“.
 */
const navGroups = computed<NavGroup[]>(() => [
  {
    id: 'library',
    title: t('sidebar.groups.library'),
    items: [
      { id: 'runs', glyph: '▶', label: t('sidebar.nav.runs'), to: { name: 'LibraryRuns' }, count: counts.value.laeufe, current: onRunsSection.value },
      { id: 'graphs', glyph: '◇', label: t('sidebar.nav.graphs'), to: { name: 'LibraryGraphs' }, count: counts.value.graphen, current: route.name === 'LibraryGraphs' || route.name === 'GraphLibraryDetail' || shelfObjectKind.value === 'graph' },
      { id: 'personas', glyph: '◎', label: t('sidebar.nav.personas'), to: { name: 'LibraryRuns' }, count: counts.value.personasaetze, current: shelfObjectKind.value === 'personasatz' },
    ],
  },
  {
    id: 'focus',
    title: t('sidebar.groups.focus'),
    items: [
      { id: 'running', glyph: '◌', label: t('sidebar.nav.running'), to: { name: 'LibraryRuns', query: { view: 'running' } }, count: counts.value.laeuft, current: runsView.value === 'running' },
      { id: 'attention', glyph: '!', label: t('sidebar.nav.attention'), to: { name: 'LibraryRuns', query: { view: 'attention' } }, count: counts.value.brauchtDich, current: runsView.value === 'attention' },
    ],
  },
  {
    id: 'tools',
    title: t('sidebar.groups.tools'),
    items: [
      {
        id: 'compare',
        glyph: '⇄',
        label: t('sidebar.nav.compare'),
        to: compareSimulationId.value
          ? { name: 'Compare', params: { simulationId: compareSimulationId.value } }
          : { name: 'Compare' },
        current: route.name === 'Compare',
      },
      { id: 'activity', glyph: '≡', label: t('sidebar.nav.activity'), to: { name: 'ActivityJobs' }, count: counts.value.aktivitaet, current: onActivitySection.value },
    ],
  },
])

/** IA-Matrix: nur wire-Settings-Sub-Items.
 *  Besucher ohne Betreiber-Zugang sehen zusaetzlich vorne "Provider-Keys" —
 *  die einzige Unterseite, die sie tatsaechlich bearbeiten duerfen.
 *
 *  Fix #1713 (Befund 7): LLM-Routing und Audit-Logs hatten in der Sidebar
 *  keinen Eintrag, obwohl SettingsOverlay sie zeigte (Doppelnavigation).
 *  Beide Routen sind jetzt Teil dieser einen Navigationsebene. */
const navSettingsOperator: NavSettingsItem[] = [
  { id: 'general',       label: t('sidebar.settings.general'),       to: { name: 'SettingsGeneral' } },
  { id: 'integrations',  label: t('sidebar.settings.integrations'),  to: { name: 'SettingsIntegrations' } },
  { id: 'profile',       label: t('sidebar.settings.profile'),       to: { name: 'SettingsProfile' } },
  { id: 'api-keys',      label: t('sidebar.settings.apiKeys'),       to: { name: 'SettingsApiKeys' } },
  { id: 'llm-providers', label: t('sidebar.settings.llmProviders'),  to: { name: 'SettingsLlmProviders' } },
  { id: 'embedding',     label: t('sidebar.settings.embedding'),     to: { name: 'SettingsEmbedding' } },
  { id: 'llm-routing',   label: t('sidebar.settings.llmRouting'),    to: { name: 'SettingsLlmRouting' } },
  { id: 'audit-logs',    label: t('sidebar.settings.auditLogs'),     to: { name: 'SettingsAuditLogs' } },
]

const navSettings = computed<NavSettingsItem[]>(() =>
  operatorAccess.value
    ? navSettingsOperator
    : [
        { id: 'provider-keys', label: t('sidebar.settings.providerKeys'), to: { name: 'WorkspaceProviderKeys' } },
        ...navSettingsOperator,
      ],
)
</script>

<style scoped>
.sidebar {
  width: 220px;
  background: var(--s1);
  display: flex;
  flex-direction: column;
  height: 100%;
  flex-shrink: 0;
  transition: width var(--v4-state-motion-duration-base) var(--v4-state-motion-ease);
  overflow: hidden;
}

@media (prefers-reduced-motion: reduce) {
  .sidebar {
    transition: none;
  }
}

.sidebar--collapsed {
  width: 56px;
}

.sidebar__brand {
  height: 64px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
  flex-shrink: 0;
}

.sidebar__wordmark {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--fg);
  font-family: var(--ag-font-sans);
  white-space: nowrap;
}

.sidebar__body {
  padding: 0 10px 8px;
  display: flex;
  flex-direction: column;
  flex: 1;
  /* Hoehe der Seitenleiste mit geoeffneter Einstellungen-Gruppe (8 Unterpunkte)
     passt bewusst in 720 px Viewport-Hoehe: scrollt die Leiste, springt der
     Fokus beim Tabben in die Mitte und die Tab-Reihenfolge-Pruefung
     (e2e tabOrder) meldet einen Sprung nach oben. Die Abstaende hier und in
     SidebarItem/SidebarGroup sind darauf abgestimmt. */
  min-height: 0;
  overflow-y: auto;
}

.sidebar__group {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-bottom: 10px;
}

.sidebar__group-title {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--fg3);
  padding: 0 10px 2px;
}

.sidebar__notice {
  margin: 0 0 12px;
  padding: 0 10px;
  font-size: 12px;
  color: var(--fg3);
}

/* Abstand statt Trennlinie: System und Einstellungen rutschen nach unten. */
.sidebar__bottom {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-top: 8px;
}

.sidebar__footer {
  width: 100%;
  padding: 8px 18px;
  border: 0;
  border-radius: 0;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--fg2);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  flex-shrink: 0;
  user-select: none;
  transition: color 100ms ease;
}

.sidebar__footer:hover {
  color: var(--fg);
}

/* Die Unterpunkte der Einstellungen-Gruppe hatten keinen Fokusring —
   mit der Tastatur war nicht sichtbar, wo man steht. */
.sidebar-sub-item:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

/* Demo-Vorschau (Besucher ohne Betreiber-Zugang): kennzeichnet die
   Betreiber-Unterseiten in der Einstellungen-Gruppe. */
.sidebar-sub-item__badge {
  margin-left: auto;
  padding: 1px 6px;
  border-radius: var(--ag-r-pill);
  background: var(--acc-soft);
  color: var(--acc-text);
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.sidebar__footer:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: -2px;
}

.sidebar__footer-label {
  white-space: nowrap;
}
</style>
