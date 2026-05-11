<!--
  StepGraphBuildView — AppShell-Wrapper fuer Step 1 (Graph-Build / Upload).
  Der Inhalt (Step1GraphBuild.vue) bleibt v2-typografiert — Inhalts-Migration
  ist ein eigener Folge-Slice.
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader
      title="Graph Build"
      subtitle="Wissensgraph aus hochgeladenen Dokumenten aufbauen"
    />
    <PipelineStepper :current-step="1" />
    <!-- Step1GraphBuild empfaengt projectData/graphData via Store, kein direkter projectId-Prop -->
    <Step1GraphBuild />
  </AppShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step1GraphBuild from '@/components/Step1GraphBuild.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const props = defineProps<{
  projectId: string
}>()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.projectId },
  { label: 'Graph Build' },
])
</script>
