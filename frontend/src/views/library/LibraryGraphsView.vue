<script setup lang="ts">
/**
 * Platzhalter (Etappe 2, Ticket 1 „Adressen", #1797): nur Adresse, Titel und
 * Brotkrumen. Der Inhalt kommt mit dem jeweiligen Folge-Ticket.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import { useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'

const { t } = useI18n()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('views.library.title'), path: '/library/runs' },
  { label: t('views.library.graphs.title') },
])
useShellBreadcrumbs(crumbs)
</script>

<template>
  <PageHeader :title="t('views.library.graphs.title')" />
</template>
