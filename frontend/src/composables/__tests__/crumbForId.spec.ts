import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { crumbForId } from '../useShellBreadcrumbs'
import { useShellStore } from '@/stores/shell'
import type { ShelfObject } from '@/types/shelf'

function shelfObject(id: string, title: string): ShelfObject {
  return { kind: 'lauf', id, title } as ShelfObject
}

describe('crumbForId', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('nutzt die Kennung als Beschriftung, solange kein Titel vorliegt', () => {
    expect(crumbForId('sim_1', '/x')).toEqual({ label: 'sim_1', path: '/x' })
  })

  it('zeigt den Titel und haelt die Kennung als Marke, wenn der Titel im Speicher liegt', () => {
    useShellStore().activeObjects = [shelfObject('sim_1', 'Quartalsbericht')]
    expect(crumbForId('sim_1')).toEqual({ label: 'Quartalsbericht', ident: 'sim_1' })
  })

  it('wiederholt die Kennung nicht, wenn der Titel nur die Kennung ist', () => {
    useShellStore().activeObjects = [shelfObject('sim_1', 'sim_1')]
    expect(crumbForId('sim_1')).toEqual({ label: 'sim_1' })
  })
})
