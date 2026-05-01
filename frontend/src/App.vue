<template>
  <router-view v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>

  <!-- Issue #132 — Globaler Log-Drawer; Toggle per Hotkey Ctrl+Shift+L. -->
  <button
    class="log-drawer-fab"
    :class="{ active: logDrawerOpen }"
    :title="$t('logs.drawer.toggle')"
    @click="logDrawerOpen = !logDrawerOpen"
  >▤ logs</button>
  <LogDrawer :open="logDrawerOpen" @close="logDrawerOpen = false" />
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import LogDrawer from './components/LogDrawer.vue'

const STORAGE_KEY = 'agora.ui.logDrawer.open'
function loadOpen() {
  try { return localStorage.getItem(STORAGE_KEY) === 'true' } catch { return false }
}
const logDrawerOpen = ref(loadOpen())
function persistOpen() {
  try { localStorage.setItem(STORAGE_KEY, String(logDrawerOpen.value)) } catch { /* ignore */ }
}
function handleHotkey(e) {
  if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'L' || e.key === 'l')) {
    e.preventDefault()
    logDrawerOpen.value = !logDrawerOpen.value
    persistOpen()
  }
}
onMounted(() => window.addEventListener('keydown', handleHotkey))
onUnmounted(() => window.removeEventListener('keydown', handleHotkey))
</script>

<style>
/* Reset only — design tokens live in src/assets/styles/tokens.css
   App-wide layout helpers in src/assets/styles/global.css */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
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
}

::-webkit-scrollbar-thumb:hover {
  background: var(--fg);
}

.log-drawer-fab {
  position: fixed;
  bottom: 12px;
  right: 12px;
  z-index: 95;
  background: var(--bg-elevated);
  color: var(--fg-muted);
  border: 1px solid var(--rule);
  border-radius: var(--r-pill);
  padding: 6px 14px;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 120ms ease, color 120ms ease, border-color 120ms ease;
}
.log-drawer-fab:hover { opacity: 1; color: var(--fg); border-color: var(--accent); }
.log-drawer-fab.active { color: var(--accent); border-color: var(--accent); opacity: 1; }
</style>
