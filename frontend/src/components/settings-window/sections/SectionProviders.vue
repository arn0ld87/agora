<script setup lang="ts">
/**
 * Anbieter (Bauplan §5) — Verbindungen zu den Modell-Anbietern.
 *
 * Zwei bisherige Ansichten in einem Abschnitt, mit ihren Zugangsregeln:
 *  - Anbieterverwaltung (`settings/llm-providers`): nur Betreiber. Wer den
 *    Abschnitt ohne Betreiber-Zugang sieht, bekommt statt der Verwaltung einen
 *    Hinweis — nichts davon wird gerendert.
 *  - Eigene Schlüssel des Workspace (`workspace/provider-keys`): für jede
 *    Anmeldung erreichbar (Bearbeiten nur Owner/Admin, regelt die Ansicht).
 */
import { useI18n } from 'vue-i18n'
import { useOperatorAccess } from '@/composables/useOperatorAccess'
import LlmProvidersView from '@/views/Settings/LlmProvidersView.vue'
import WorkspaceProviderKeysView from '@/views/Settings/WorkspaceProviderKeysView.vue'
import SettingsGroup from '../SettingsGroup.vue'

const { t } = useI18n()
const operator = useOperatorAccess()
</script>

<template>
  <div class="section-providers">
    <SettingsGroup
      :title="t('views.settingsWindow.providers.managementTitle')"
      :description="t('views.settingsWindow.providers.managementDescription')"
    >
      <LlmProvidersView v-if="operator" embedded />
      <p v-else class="section-providers__locked" role="status" data-testid="providers-operator-locked">
        {{ t('views.settingsWindow.providers.managementLocked') }}
      </p>
    </SettingsGroup>

    <SettingsGroup
      :title="t('views.settingsWindow.providers.keysTitle')"
      :description="t('views.settingsWindow.providers.keysDescription')"
    >
      <WorkspaceProviderKeysView embedded />
    </SettingsGroup>
  </div>
</template>

<style scoped>
.section-providers {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-providers__locked {
  margin: 0;
  padding: 12px 0;
  font-size: 13.5px;
  color: var(--fg2);
}
</style>
