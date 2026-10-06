import { onBeforeUnmount, toValue, watchEffect } from 'vue'
import type { MaybeRefOrGetter } from 'vue'
import { useShellStore } from '@/stores/shell'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

let nextOwnerId = 0
let activeOwnerId = 0

/**
 * Einheitlicher Weg, wie eine Ansicht der zentralen Huelle (AppShell in
 * App.vue) ihre Brotkrumen mitgibt (#1795, Ticket 4). Die Huelle liest
 * `shellStore.breadcrumbs`; die Ansicht ruft dies im `setup` auf. Beim
 * Abbau der Ansicht werden nur die eigenen Brotkrumen geraeumt, damit eine
 * nachfolgende Ansicht (Transition out-in) nicht ueberschrieben wird.
 */
export function useShellBreadcrumbs(source: MaybeRefOrGetter<BreadcrumbItem[]>): void {
  const store = useShellStore()
  const ownerId = ++nextOwnerId

  watchEffect(() => {
    activeOwnerId = ownerId
    store.breadcrumbs = toValue(source)
  })

  onBeforeUnmount(() => {
    if (activeOwnerId === ownerId) {
      store.breadcrumbs = []
      activeOwnerId = 0
    }
  })
}
