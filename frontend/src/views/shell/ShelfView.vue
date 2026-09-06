<template>
  <ShellRoot :current="selected" :active-objects="shelf.activeObjects.value" @select="onSelectTarget">
    <template #shelf>
      <Shelf :shelf="shelf" :selected="selected" @select="onSelectObject" @filter-change="onFilterChange" />
    </template>
    <template #dossier>
      <Dossier :object="selected" :shelf="shelf" />
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
import type { ShelfFilter, ShelfObject, ShelfObjectKind } from '../../types/shelf'

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

// ── Filter aus der Query (Redesign PR 8) ─────────────────────────────
//
// `?filter=` macht den Ablage-Filter teilbar/verlinkbar (Audit Zeile 137:
// „/runs → Redirect /ablage?filter=lauf"). Ungueltige Werte werden
// ignoriert statt zu werfen — ein alter/kaputter Deep-Link darf die
// Ablage nicht crashen lassen, er faellt auf den aktuellen Filter zurueck.
const VALID_SHELF_FILTERS: readonly ShelfFilter[] = ['alle', 'lauf', 'bericht', 'personasatz', 'graph', 'jobs']

function isShelfFilter(value: unknown): value is ShelfFilter {
  return typeof value === 'string' && (VALID_SHELF_FILTERS as readonly string[]).includes(value)
}

function applyFilterFromQuery(): void {
  const raw = route.query.filter
  if (isShelfFilter(raw)) shelf.filter.value = raw
}

onMounted(applyFilterFromQuery)
watch(() => route.query.filter, applyFilterFromQuery)

/**
 * Filterwechsel schreibt den Wert per router.replace in die Query zurueck
 * (statt push — der Filterwechsel ist keine eigene History-Station), damit
 * der Zustand teilbar bleibt und der /runs- bzw. /v4/history-Redirect
 * wirksam ankommt statt sofort wieder zu verschwinden.
 */
function onFilterChange(filter: ShelfFilter): void {
  shelf.filter.value = filter
  void router.replace({ name: route.name ?? 'Shelf', params: route.params, query: { ...route.query, filter } })
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
