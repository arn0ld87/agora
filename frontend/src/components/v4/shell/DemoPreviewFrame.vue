<template>
  <template v-if="!showPreview">
    <slot />
  </template>

  <div v-else class="demo-preview">
    <div class="demo-preview__banner" role="status">
      <Icon name="settings" :size="16" :stroke="1.6" class="demo-preview__banner-icon" />
      <span class="demo-preview__banner-text">{{ t('demoPreview.banner.text') }}</span>
      <RouterLink :to="{ name: 'WorkspaceProviderKeys' }" class="demo-preview__banner-link">
        {{ t('demoPreview.banner.manageKeys') }}
      </RouterLink>
    </div>

    <!-- Statische Erklaerkarte statt der echten Ansicht (Besucher duerfen die
         zugrunde liegenden Daten nicht sehen, z.B. API-Keys, Audit-Logs). -->
    <div v-if="staticContent" class="demo-preview__static">
      <h1 class="demo-preview__static-title">{{ staticContent.title }}</h1>
      <ul class="demo-preview__static-bullets">
        <li v-for="(bullet, i) in staticContent.bullets" :key="i">{{ bullet }}</li>
      </ul>
      <div class="demo-preview__mock" aria-hidden="true">
        <Skeleton variant="text" :lines="1" width="40%" />
        <Skeleton variant="text" :lines="3" />
        <Skeleton variant="rect" height="64px" />
      </div>
    </div>

    <!-- Echte Ansicht, gesperrt und ausgegraut. -->
    <div v-else class="demo-preview__content" inert>
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, RouterLink } from 'vue-router'
import Icon from './Icon.vue'
import Skeleton from '../forms/Skeleton.vue'
import { useAuthStore } from '../../../store/auth'

const { t } = useI18n()
const route = useRoute()

function operatorAccessValue(): boolean {
  try {
    return useAuthStore().operatorAccess
  } catch {
    return true
  }
}

const operatorAccess = computed(operatorAccessValue)

/** Betreiber-Route, die der aktuelle Besucher nicht bearbeiten darf. */
const isOperatorOnly = computed(() => !!route.meta?.operatorOnly)
const showPreview = computed(() => isOperatorOnly.value && !operatorAccess.value)
const isStatic = computed(() => route.meta?.demoPreview === 'static')

interface StaticContent {
  title: string
  bullets: string[]
}

const STATIC_ROUTE_KEYS: Record<string, string> = {
  SettingsApiKeys: 'apiKeys',
  SettingsAuditLogs: 'auditLogs',
  SettingsProfile: 'profile',
}

const staticContent = computed<StaticContent | null>(() => {
  if (!showPreview.value || !isStatic.value) return null
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
.demo-preview {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
}

.demo-preview__banner {
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

.demo-preview__banner-icon {
  color: var(--accent);
  flex-shrink: 0;
}

.demo-preview__banner-text {
  flex: 1;
}

.demo-preview__banner-link {
  color: var(--accent);
  font-weight: 600;
  text-decoration: underline;
  white-space: nowrap;
}

.demo-preview__content {
  opacity: 0.6;
  filter: grayscale(0.4);
  pointer-events: none;
}

.demo-preview__static {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.demo-preview__static-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.demo-preview__static-bullets {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-left: 20px;
  color: var(--text-secondary);
  font-size: 14px;
}

.demo-preview__mock {
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
