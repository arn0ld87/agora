<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import type { FunctionalComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { RouteLocationNormalized } from 'vue-router'
import LogDrawer from './components/LogDrawer.vue'
import { SETTINGS_FALLBACK_PATH } from './components/settings-window/sections'
import { useSettingsWindowStore } from './stores/settingsWindow'
import AppShell from './components/v4/shell/AppShell.vue'
import DemoPreviewStaticView from './components/v4/shell/DemoPreviewStaticView.vue'
import { useDemoPreview } from './composables/useDemoPreview'
import { useLogDrawer } from './composables/useLogDrawer'

// Muss zu den .fade-*-Regeln in assets/styles/global.css passen.
const TRANSITION_DURATION = { enter: 400, leave: 160 }

// Issue #132 / Redesign PR 2 — Zustand + Hotkey-Handler leben jetzt in
// useLogDrawer.ts (single source of truth). Die frueher hier gerenderte
// FAB ist raus; die Kopfzeilen-Icons in Topbar.vue toggeln
// denselben Composable-State.
const { visible: logDrawerOpen, close: closeLogDrawer, handleHotkey } = useLogDrawer()
onMounted(() => window.addEventListener('keydown', handleHotkey))
onUnmounted(() => window.removeEventListener('keydown', handleHotkey))

// Demo-Vorschau (#1697): DemoPreviewFrame darf NICHT mehr aussen um
// RouterView liegen — ein Wrapper dort sperrte Sidebar/Topbar mit oder liess
// sie fuer statische Seiten ganz verschwinden. Betreiber-Sperre + Vorschau-Banner leben jetzt
// im Hauptbereich von AppShell.vue selbst. Nur fuer statische Vorschau-
// Routen (meta.demoPreview:'static') wird hier die echte Route-Komponente
// durch DemoPreviewStaticView ersetzt — sie mountet nie (kein Betreiber-Fetch).
const route = useRoute()
const router = useRouter()
const demoPreview = useDemoPreview()

// Einstellungsfenster (#1799, Etappe 3): `/settings/:section` liegt als Dialog
// ueber der zuletzt gezeigten Ansicht. Dazu rendert der Haupt-router-view eine
// Hintergrundroute (`:route`) statt der aktuellen: die gemerkte vorherige
// Adresse, bei Direktaufruf die Bibliothek der Laeufe. Das Fenster selbst
// rendert ein zweiter router-view (Komponente der aktuellen Route).
const settingsWindowStore = useSettingsWindowStore()
const isSettingsWindow = computed(() => route.meta?.settingsWindow === true)
const shownRoute = computed<RouteLocationNormalized>(() => {
  if (!isSettingsWindow.value) return route as RouteLocationNormalized
  const behind = router.resolve(settingsWindowStore.returnTo ?? SETTINGS_FALLBACK_PATH)
  // Nie ein Fenster unter dem Fenster.
  const target = behind.meta?.settingsWindow === true ? router.resolve(SETTINGS_FALLBACK_PATH) : behind
  // resolve() liefert dieselbe Form wie die aktuelle Route, nur `name` ist `null` statt `undefined`-fähig.
  return target as RouteLocationNormalized
})

const showStaticPreview = computed(
  () => shownRoute.value.meta?.demoPreview === 'static' && demoPreview.value,
)

// Zentrale Huelle (#1795): jede Route bekommt sie, ausser meta.layout === 'bare'.
// Passthrough reicht den Inhalt unveraendert durch (kein zusaetzliches DOM).
const withShell = computed(() => shownRoute.value.meta?.layout !== 'bare')
const Passthrough: FunctionalComponent = (_props, { slots }) => slots.default?.()
// Die statische Vorschau bringt Banner + Inhalt selbst mit — ein zweiter
// DemoPreviewFrame in der Huelle machte sie grau/inert (#1697).
const shellProps = computed(() => (withShell.value ? { demoFrame: !showStaticPreview.value } : {}))
</script>

<template>
  <!-- #1795 Ticket 4: die Huelle sitzt genau hier, einmal um alle Ansichten.
       Sie bleibt beim Wechsel zwischen Ansichten stehen (Seitenleiste und
       Kopf werden nicht neu aufgebaut); nur der Inhalt blendet ueber.
       Ansichten ohne Huelle (Anmeldung, Nicht-gefunden ...) tragen
       meta.layout === 'bare' — das ist der einzige Opt-out. -->
  <component :is="withShell ? AppShell : Passthrough" v-bind="shellProps">
    <router-view v-slot="{ Component }" :route="shownRoute">
      <!-- :duration ist Pflicht, nicht Kosmetik. Ohne explizite Dauer wartet Vue
           bei mode="out-in" auf ein transitionend-Event. In einem Hintergrund-Tab
           laesst Chrome CSS-Transitions gar nicht erst laufen, das Event bleibt
           aus und die leave-Phase endet nie: die URL wechselt, der alte View
           bleibt stehen. Mit :duration nutzt Vue einen Timer statt des Events. -->
      <transition name="fade" mode="out-in" :duration="TRANSITION_DURATION">
        <DemoPreviewStaticView v-if="showStaticPreview" />
        <component :is="Component" v-else />
      </transition>
    </router-view>
  </component>

  <!-- Einstellungsfenster: Komponente der aktuellen Route, ueber der Huelle. -->
  <router-view v-if="isSettingsWindow" />

  <!-- Issue #132 — Globaler Log-Drawer; Toggle per Hotkey Ctrl+Shift+L oder
       das Kopfzeilen-Icon "Protokoll" (Topbar.vue). Die frueher
       hier gerenderte FAB (Redesign-Audit §14 "Chrome-Rauschen") ist raus. -->
  <LogDrawer :open="logDrawerOpen" @close="closeLogDrawer" />
</template>

<style>
/* Reset only — design tokens live in src/assets/styles/tokens-v3.css
   App-wide layout helpers in src/assets/styles/global.css */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  position: relative;
  z-index: 2;
}

::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--bg-elevated);
}

::-webkit-scrollbar-thumb {
  background: var(--rule-strong);
  border-radius: var(--r-pill);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--fg-muted);
}
</style>
