<script setup lang="ts">
/**
 * Embedding — aktive Konfiguration und Migration (Inhalt von
 * `/settings/embedding`), ohne eigenen Seitenkopf. Oben steht der Hinweis zu
 * #1417: Die Oberfläche behauptet nicht, die angezeigte Konfiguration sei die
 * wirksame.
 */
import { useI18n } from 'vue-i18n'
import EmbeddingConfigurationsView from '@/views/Settings/EmbeddingConfigurationsView.vue'

const { t } = useI18n()
</script>

<template>
  <div class="section-embedding">
    <p class="section-embedding__notice" role="note" data-testid="embedding-1417-notice">
      {{ t('views.settingsWindow.embedding.notice') }}
      <a
        href="https://github.com/arn0ld87/agora/issues/1417"
        target="_blank"
        rel="noopener noreferrer"
      >#1417</a>
    </p>
    <EmbeddingConfigurationsView embedded />
  </div>
</template>

<style scoped>
.section-embedding {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-embedding__notice {
  margin: 0;
  padding: 10px 12px;
  font-size: 13.5px;
  line-height: 1.45;
  color: var(--fg);
  background: var(--s1);
  border: 1px solid var(--status-orange, var(--fg2));
  border-radius: 8px;
}
</style>
