<template>
  <ShellRoot :current="selected" :active-objects="shelf.activeObjects.value" @select="onSelectTarget">
    <template #shelf>
      <Shelf :shelf="shelf" :selected="selected" @select="onSelectObject" @filter-change="shelf.filter.value = $event" />
    </template>
    <template #dossier>
      <Dossier :object="selected" />
    </template>
  </ShellRoot>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import ShellRoot from '../../components/shell/ShellRoot.vue'
import Shelf from '../../components/shell/Shelf.vue'
import Dossier from '../../components/shell/Dossier.vue'
import { useShelf } from '../../composables/useShelf'
import { usePolling } from '../../composables/usePolling'
import type { ShelfObject, ShelfObjectKind } from '../../types/shelf'

/**
 * ShelfView.vue — Route-View der Ablage (Block B3, /ablage und
 * /ablage/:kind/:objectId).
 *
 * `selected` ist bewusst ein reiner computed aus Route-Params +
 * shelf.objects — kein eigener Ref mit manueller Sync-Logik. Ein
 * Klick auf eine Zeile/Pill navigiert (router.push); die Route ist
 * die alleinige Quelle der Auswahl, das macht Deep-Links
 * (/ablage/lauf/sim_xyz) und Browser-Zurueck fuer die Auswahl gratis
 * korrekt.
 *
 * Polling: solange useShelf.activeObjects nicht leer ist, alle 10s
 * neu laden (usePolling, pausiert automatisch im Hintergrund-Tab).
 */

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const shelf = useShelf(t)

const selected = computed<ShelfObject | null>(() => {
  const kind = route.params.kind as ShelfObjectKind | undefined
  const objectId = route.params.objectId as string | undefined
  if (!kind || !objectId) return null
  return shelf.objects.value.find((o) => o.kind === kind && o.id === objectId) ?? null
})

function onSelectObject(obj: ShelfObject): void {
  void router.push({ name: 'ShelfObject', params: { kind: obj.kind, objectId: obj.id } })
}

function onSelectTarget(target: { kind: ShelfObjectKind; id: string } | null): void {
  if (!target) {
    void router.push({ name: 'Shelf' })
    return
  }
  void router.push({ name: 'ShelfObject', params: { kind: target.kind, objectId: target.id } })
}

const polling = usePolling(() => shelf.reload(), 10000, { immediate: false })

watch(
  shelf.activeObjects,
  (list) => {
    if (list.length > 0) void polling.start()
    else polling.stop()
  },
  { immediate: true },
)

onMounted(() => {
  void shelf.reload()
})
</script>
