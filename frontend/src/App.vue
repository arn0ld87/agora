<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import LogDrawer from './components/LogDrawer.vue'
import DemoPreviewStaticView from './components/v4/shell/DemoPreviewStaticView.vue'
import { useDemoPreview } from './composables/useDemoPreview'
import { useLogDrawer } from './composables/useLogDrawer'

// Muss zu den .fade-*-Regeln in assets/styles/global.css passen.
const TRANSITION_DURATION = { enter: 400, leave: 160 }

// Issue #132 / Redesign PR 2 — Zustand + Hotkey-Handler leben jetzt in
// useLogDrawer.ts (single source of truth). Die frueher hier gerenderte
// FAB ist raus; die Kopfzeilen-Icons in Topbar.vue/ShellRoot.vue toggeln
// denselben Composable-State.
const { visible: logDrawerOpen, close: closeLogDrawer, handleHotkey } = useLogDrawer()
onMounted(() => window.addEventListener('keydown', handleHotkey))
onUnmounted(() => window.removeEventListener('keydown', handleHotkey))

// Demo-Vorschau (#1697): DemoPreviewFrame darf NICHT mehr aussen um
// RouterView liegen — jede Settings-View rendert ihr eigenes AppShell, ein
// Wrapper hier sperrte also Sidebar/Topbar mit oder liess sie fuer statische
// Seiten ganz verschwinden. Betreiber-Sperre + Vorschau-Banner leben jetzt
// im Hauptbereich von AppShell.vue selbst. Nur fuer statische Vorschau-
// Routen (meta.demoPreview:'static') wird hier die echte Route-Komponente
// durch DemoPreviewStaticView ersetzt — sie mountet nie (kein Betreiber-Fetch).
const route = useRoute()
const demoPreview = useDemoPreview()
const showStaticPreview = computed(
  () => route.meta?.demoPreview === 'static' && demoPreview.value,
)
</script>

<template>
  <router-view v-slot="{ Component }">
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

  <!-- Issue #132 — Globaler Log-Drawer; Toggle per Hotkey Ctrl+Shift+L oder
       das Kopfzeilen-Icon "Protokoll" (Topbar.vue/ShellRoot.vue). Die frueher
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
