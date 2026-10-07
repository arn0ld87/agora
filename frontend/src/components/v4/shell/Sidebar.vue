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
          :to="{ name: 'SettingsWindow', params: { section: 'system' } }"
          :tone="systemTone"
          :tooltip="t(`sidebar.system.state.${systemTone}`)"
          :current="false"
          :collapsed="collapsed"
          @click="handleNavClick"
        />

        <!-- Eine Zeile „Einstellungen“ (Etappe 3, #1799): oeffnet das
             Einstellungsfenster auf „Allgemein“; die Abschnitte stehen in dessen
             Liste. Fuer Besucher ohne Betreiber-Zugang bleibt die Zeile nur auf
             der Demo-Instanz sichtbar (demoPreview); ein regulaerer JWT-Nutzer
             ohne Demo-Modus sieht sie nicht (#1697). -->
        <SidebarItem
          v-if="showSettingsGroup"
          icon="settings"
          :label="t('sidebar.settings.label')"
          :to="{ name: 'SettingsGeneral' }"
          :current="onSettingsRoute"
          :collapsed="collapsed"
          @click="handleNavClick"
        />
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
import { useRoute } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import SidebarItem from './SidebarItem.vue'
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

/** Route-Namen, bei denen die Zeile „Einstellungen“ als aktiv gilt. Die Fenster-
 *  Adressen (meta.settingsWindow) kommen zusaetzlich ueber `onSettingsRoute`;
 *  die alten Einstellungsadressen sind seit Etappe 3 Weiterleitungen und
 *  tauchen in `route.matched` nicht mehr auf. */
const settingsRouteNames = ['Settings', 'SettingsGeneral', 'SettingsWindow', 'SettingsEmbedding']

const onSettingsRoute = computed(
  () =>
    route.meta?.settingsWindow === true ||
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

const onPersonaSetsSection = computed(() => route.name === 'LibraryPersonaSets' || route.name === 'PersonaSet')

const onActivitySection =computed(() => route.path === '/activity' || route.path.startsWith('/activity/'))

/**
 * Seitenleiste laut Bauplan 3.1. Jeder Eintrag fuehrt auf eine Adresse der
 * Etappe 2:
 *  - Laeufe → Bibliothek → Laeufe; ein geoeffneter Lauf (`/simulations/…`)
 *    markiert „Laeufe“. Graphen → Graphen-Bibliothek, `/graphs/:projectId`
 *    markiert „Graphen“.
 *  - Personasaetze → Personasatz-Bibliothek (Etappe 7); `/persona-sets/:setId`
 *    und die alte Personasatz-Objektansicht markieren sie ebenfalls.
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
      { id: 'personas', glyph: '◎', label: t('sidebar.nav.personas'), to: { name: 'LibraryPersonaSets' }, count: counts.value.personasaetze, current: onPersonaSetsSection.value || shelfObjectKind.value === 'personasatz' },
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
  padding: 0 10px 12px;
  display: flex;
  flex-direction: column;
  flex: 1;
  /* Die Seitenleiste passt bewusst in 720 px Viewport-Hoehe ohne internes
     Scrollen: scrollt sie, springt der Fokus beim Tabben in die Mitte und die
     Tab-Reihenfolge-Pruefung (e2e tabOrder) meldet einen Sprung nach oben.
     Mit nur einer Zeile „Einstellungen“ (statt der Gruppe mit 8 Unterpunkten)
     reichen die urspruenglichen Masse: 34-px-Zeilen, 2-px-Luecken (≈ 565 px). */
  min-height: 0;
  overflow-y: auto;
}

.sidebar__group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 16px;
}

.sidebar__group-title {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--fg3);
  padding: 0 10px 4px;
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
  gap: 2px;
  padding-top: 16px;
}

.sidebar__footer {
  width: 100%;
  padding: 10px 18px;
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

.sidebar__footer:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: -2px;
}

.sidebar__footer-label {
  white-space: nowrap;
}
</style>
