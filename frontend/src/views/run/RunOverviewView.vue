<script setup lang="ts">
/**
 * Platzhalter (Etappe 2, Ticket 1 „Adressen", #1797): nur Adresse, Titel und
 * Brotkrumen. Der Inhalt kommt mit dem jeweiligen Folge-Ticket.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import { crumbForId, useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'

const { t } = useI18n()
const route = useRoute()
const simulationId = computed(() => String(route.params['simulationId'] ?? ''))

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('views.library.runs.title'), path: '/library/runs' },
  crumbForId(simulationId.value),
  { label: t('views.run.overview.title') },
])
useShellBreadcrumbs(crumbs)
</script>

<template>
  <PageHeader :title="t('views.run.overview.title')" />
</template>
