<template>
  <template v-if="!showPreview">
    <slot />
  </template>

  <div v-else class="demo-preview">
    <div class="demo-preview__banner" role="status">
      <Icon name="settings" :size="16" :stroke="1.6" class="demo-preview__banner-icon" />
      <span class="demo-preview__banner-text">{{ t('demoPreview.banner.text') }}</span>
      <RouterLink :to="{ name: 'SettingsWindow', params: { section: 'providers' } }" class="demo-preview__banner-link">
        {{ t('demoPreview.banner.manageKeys') }}
      </RouterLink>
    </div>

    <!-- Echte Ansicht, gesperrt und ausgegraut. Statische Erklaerkarten
         (meta.demoPreview:'static') mounten hier gar nicht erst — App.vue
         rendert dafuer DemoPreviewStaticView.vue statt der Route-Komponente. -->
    <div class="demo-preview__content" inert>
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, RouterLink } from 'vue-router'
import Icon from './Icon.vue'
import { useOperatorAccess } from '../../../composables/useOperatorAccess'

const { t } = useI18n()
const route = useRoute()
const operatorAccess = useOperatorAccess()

/** Betreiber-Route, die der aktuelle Besucher nicht bearbeiten darf. */
const isOperatorOnly = computed(() => !!route.meta?.operatorOnly)
const showPreview = computed(() => isOperatorOnly.value && !operatorAccess.value)
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
</style>
