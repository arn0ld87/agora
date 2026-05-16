<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import DashboardScreen from './screens/DashboardScreen.vue'
import RunsScreen from './screens/RunsScreen.vue'

const SCREEN_KEYS = ['dashboard', 'runs'] as const
type ScreenKey = (typeof SCREEN_KEYS)[number]

function isScreenKey(value: string): value is ScreenKey {
  return (SCREEN_KEYS as readonly string[]).includes(value)
}

const active = ref<ScreenKey>('dashboard')

function onNav(key: string): void {
  if (isScreenKey(key)) active.value = key
}

const prevTheme = ref<string | null>(null)

onMounted(() => {
  prevTheme.value = document.documentElement.getAttribute('data-theme')
  document.documentElement.setAttribute('data-theme', 'agora-2026')
})

onUnmounted(() => {
  if (prevTheme.value != null) {
    document.documentElement.setAttribute('data-theme', prevTheme.value)
  } else {
    document.documentElement.removeAttribute('data-theme')
  }
})
</script>

<template>
  <div class="a26-root agora-2026-canvas">
    <DashboardScreen v-if="active === 'dashboard'" @nav="onNav" />
    <RunsScreen v-else-if="active === 'runs'" @nav="onNav" />
  </div>
</template>

<style scoped>
.agora-2026-canvas {
  position: fixed;
  inset: 0;
  z-index: 1;
  overflow: hidden;
}
</style>
