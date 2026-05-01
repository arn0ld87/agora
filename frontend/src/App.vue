<script setup>
import AuroraBackground from './components/ui/AuroraBackground.vue'
import { useTheme } from './composables/useTheme.js'

// Mount the theme watcher early so the persisted theme is applied before
// the first child component reads any token-driven style.
useTheme()
</script>

<template>
  <AuroraBackground />
  <router-view v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>

<style>
/* Reset only — design tokens live in src/assets/styles/tokens.css
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
