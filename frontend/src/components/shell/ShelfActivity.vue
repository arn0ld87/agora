<template>
  <ActivityIndicator :objects="shellStore.activeObjects" @select="onSelect" />
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useShellStore } from '@/stores/shell'
import type { ShelfObjectKind } from '../../types/shelf'
import ActivityIndicator from './ActivityIndicator.vue'

/**
 * ShelfActivity.vue — Aktivitaets-Indikator in der Kopfleiste der Huelle
 * (#1795, Ticket 5). Zeigt die laufenden Ablage-Objekte, die ShelfView in den
 * Shell-Store meldet; ein Klick auf einen Eintrag oeffnet ihn in der Ablage.
 */

const shellStore = useShellStore()
const router = useRouter()

function onSelect(target: { kind: ShelfObjectKind; id: string }): void {
  void router.push({ name: 'ShelfObject', params: { kind: target.kind, objectId: target.id } })
}
</script>
