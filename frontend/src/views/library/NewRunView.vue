<script setup lang="ts">
/**
 * Neuer Lauf (Etappe 2, #1797): Übergangs-Einstieg bis zum Startdialog der
 * Etappe 3. Bettet `HeroNewRun` unverändert ein; der Start aus einer neuen
 * Quelle führt weiter über `/process/new` (Bauplan §6.2).
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import HeroNewRun from '@/components/v4/dashboard/HeroNewRun.vue'
import { useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'

const { t } = useI18n()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('views.library.title'), path: '/library/runs' },
  { label: t('views.library.runs.title'), path: '/library/runs' },
  { label: t('views.library.newRun.title') },
])
useShellBreadcrumbs(crumbs)
</script>

<template>
  <div>
    <PageHeader :title="t('views.library.newRun.title')" :subtitle="t('views.library.newRun.subtitle')" />
    <HeroNewRun />
  </div>
</template>
