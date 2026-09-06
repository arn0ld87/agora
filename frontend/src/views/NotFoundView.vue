<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const path = String(route.fullPath || '')

function goHome(): void {
  void router.replace({ name: 'Dashboard' })
}
</script>

<template>
  <main class="not-found">
    <div class="not-found__inner">
      <p class="not-found__kicker">{{ t('router.notFound.kicker') }}</p>
      <h1 class="not-found__title">{{ t('router.notFound.title') }}</h1>
      <p class="not-found__path">{{ path }}</p>
      <button type="button" class="not-found__cta" @click="goHome">
        {{ t('router.notFound.cta') }}
      </button>
    </div>
  </main>
</template>

<style scoped>
.not-found {
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: 2rem;
}
.not-found__inner {
  text-align: center;
  max-width: 32rem;
}
.not-found__kicker {
  font-size: 0.75rem;
  letter-spacing: 0.2em;
  opacity: 0.6;
  margin: 0 0 0.5rem;
}
.not-found__title {
  font-size: clamp(1.5rem, 4vw, 2.25rem);
  margin: 0 0 1rem;
}
.not-found__path {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.9rem;
  opacity: 0.7;
  word-break: break-all;
  margin: 0 0 1.5rem;
}
.not-found__cta {
  padding: 0.6rem 1.2rem;
  border: 1px solid currentColor;
  background: transparent;
  cursor: pointer;
  border-radius: var(--r-3);
  font: inherit;
}
.not-found__cta:hover {
  background: currentColor;
  color: var(--bg, white);
}
</style>
