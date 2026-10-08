<script setup lang="ts">
/**
 * Zugang — API-Schlüssel, Audit-Protokoll, Konto, Sicherheit als Gruppen
 * untereinander (keine zweite Navigationsebene). Inhalte der bisherigen
 * Ansichten `settings/api-keys`, `audit-logs` und des Settings-Abschnitts `security`.
 *
 * Der gesamte Abschnitt bleibt Betreiberbereich. API-Schlüssel und
 * Audit-Protokoll prüfen zusätzlich Token oder Sitzung.
 */
import { useI18n } from 'vue-i18n'
import SettingsSectionPanel from '@/components/v4/forms/SettingsSectionPanel.vue'
import SettingsApiKeysView from '@/views/Settings/SettingsApiKeysView.vue'
import SettingsAuditLogsView from '@/views/Settings/SettingsAuditLogsView.vue'
import { useHasCredentials } from '../access/useHasCredentials'

const { t } = useI18n()
const hasCredentials = useHasCredentials()
const SECURITY_SECTIONS = ['security'] as const
</script>

<template>
  <div class="section-access">
    <section class="section-access__group" aria-labelledby="access-keys-title">
      <h3 id="access-keys-title" class="section-access__title">
        {{ t('views.settingsWindow.access.apiKeys') }}
      </h3>
      <SettingsApiKeysView v-if="hasCredentials" embedded />
      <p v-else class="section-access__needs-auth" role="status">
        {{ t('views.settingsWindow.access.needsAuth') }}
      </p>
    </section>

    <section class="section-access__group" aria-labelledby="access-audit-title">
      <h3 id="access-audit-title" class="section-access__title">
        {{ t('views.settingsWindow.access.audit') }}
      </h3>
      <SettingsAuditLogsView v-if="hasCredentials" embedded />
      <p v-else class="section-access__needs-auth" role="status">
        {{ t('views.settingsWindow.access.needsAuth') }}
      </p>
    </section>

    <section class="section-access__group" aria-labelledby="access-security-title">
      <h3 id="access-security-title" class="section-access__title">
        {{ t('views.settingsWindow.access.security') }}
      </h3>
      <SettingsSectionPanel :allowed-sections="SECURITY_SECTIONS" />
    </section>
  </div>
</template>

<style scoped>
.section-access {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.section-access__group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.section-access__title {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  color: var(--fg);
}

.section-access__needs-auth {
  margin: 0;
  font-size: 13.5px;
  color: var(--fg2);
}
</style>
