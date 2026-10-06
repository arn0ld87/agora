<template>
  <!-- Die Huelle sitzt zentral in App.vue und bekommt dort demo-frame=false:
       die Karte hier ist bereits der komplette Ersatz fuer die gesperrte
       Ansicht (Banner + Erklaerung) — AppShells DemoPreviewFrame-Wrapper
       wuerde sie zusaetzlich grau/inert machen. -->
  <div class="demo-preview-static">
      <div class="demo-preview-static__banner" role="status">
        <Icon name="settings" :size="16" :stroke="1.6" class="demo-preview-static__banner-icon" />
        <span class="demo-preview-static__banner-text">{{ t('demoPreview.banner.text') }}</span>
        <RouterLink :to="{ name: 'SettingsWindow', params: { section: 'providers' } }" class="demo-preview-static__banner-link">
          {{ t('demoPreview.banner.manageKeys') }}
        </RouterLink>
      </div>

      <!-- Statische Erklaerkarte statt der echten Ansicht (Besucher duerfen die
           zugrunde liegenden Daten nicht sehen, z.B. API-Keys, Audit-Logs).
           Die echte Route-Komponente wird von App.vue fuer diese Routen gar
           nicht erst gemountet — kein zusaetzlicher Betreiber-Fetch. -->
      <div v-if="staticContent" class="demo-preview-static__card">
        <h1 class="demo-preview-static__title">{{ staticContent.title }}</h1>
        <ul class="demo-preview-static__bullets">
          <li v-for="(bullet, i) in staticContent.bullets" :key="i">{{ bullet }}</li>
        </ul>
        <div class="demo-preview-static__mock" aria-hidden="true">
          <Skeleton variant="text" :lines="1" width="40%" />
          <Skeleton variant="text" :lines="3" />
          <Skeleton variant="rect" height="64px" />
        </div>
      </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, RouterLink } from 'vue-router'
import Icon from './Icon.vue'
import Skeleton from '../forms/Skeleton.vue'

const { t } = useI18n()
const route = useRoute()

interface StaticContent {
  title: string
  bullets: string[]
}

/** Route-Name → i18n-Schluessel unter demoPreview.static.* (DemoPreviewFrame#1697). */
const STATIC_ROUTE_KEYS: Record<string, string> = {
  SettingsApiKeys: 'apiKeys',
  SettingsAuditLogs: 'auditLogs',
  SettingsProfile: 'profile',
}

const staticContent = computed<StaticContent | null>(() => {
  const key = STATIC_ROUTE_KEYS[String(route.name ?? '')]
  if (!key) return null
  // Jede Bullet ist ein eigener i18n-Schluessel (bullet1..bulletN) — vue-i18n
  // liefert Listen erst ueber tm(), die einfache Nummerierung reicht hier.
  const count = Number(t(`demoPreview.static.${key}.bulletCount`))
  const bullets = Array.from({ length: count }, (_, i) => t(`demoPreview.static.${key}.bullet${i + 1}`))
  return { title: t(`demoPreview.static.${key}.title`), bullets }
})
</script>

<style scoped>
.demo-preview-static {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
}

.demo-preview-static__banner {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: var(--accent-tint-bg);
  border: 1px solid var(--accent);
  border-radius: var(--r-3, 6px);
  color: var(--text-primary);
  font-size: 13px;
}

.demo-preview-static__banner-icon {
  color: var(--accent);
  flex-shrink: 0;
}

.demo-preview-static__banner-text {
  flex: 1;
}

.demo-preview-static__banner-link {
  color: var(--accent);
  font-weight: 600;
  text-decoration: underline;
  white-space: nowrap;
}

.demo-preview-static__card {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.demo-preview-static__title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.demo-preview-static__bullets {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-left: 20px;
  color: var(--text-secondary);
  font-size: 14px;
}

.demo-preview-static__mock {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  background: var(--surface-elevated);
  border: 1px solid var(--hairline);
  border-radius: var(--r-3, 6px);
  opacity: 0.6;
  filter: grayscale(0.4);
}
</style>
