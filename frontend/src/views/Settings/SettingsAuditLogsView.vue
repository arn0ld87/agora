<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import SettingsOverlay from '@/components/v4/forms/SettingsOverlay.vue'
import ComingSoonCard from '@/components/v4/forms/ComingSoonCard.vue'

const { t } = useI18n()
</script>

<template>
  <SettingsOverlay>
    <PageHeader
      :title="t('settings.v4.auditLogs.title')"
      :subtitle="t('settings.v4.auditLogs.subtitle')"
    />

    <ComingSoonCard
      :title="t('settings.v4.auditLogs.empty.title')"
      :description="t('settings.v4.auditLogs.empty.description')"
    />
  </SettingsOverlay>
</template>
