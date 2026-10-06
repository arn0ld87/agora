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
/**
 * Brotkrumen-Eintrag fuer ein Objekt, das die Route nur ueber seine Kennung
 * kennt. Liegt der Titel ohne Netzwerkaufruf vor (laufende Ablage-Objekte im
 * Shell-Store), steht der Titel als Beschriftung und die Kennung als
 * kopierbare Marke daneben; sonst bleibt die Kennung die Beschriftung.
 * In `computed`/Getter aufrufen, damit der Titel nachgereicht wird.
 */
export function crumbForId(id: string, path?: string): BreadcrumbItem {
  const known = useShellStore().activeObjects.find((o) => o.id === id)
  const title = known?.title.trim()
  return title && title !== id
    ? { label: title, ident: id, ...(path ? { path } : {}) }
    : { label: id, ...(path ? { path } : {}) }
}

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
