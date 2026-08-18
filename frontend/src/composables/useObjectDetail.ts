import { ref, watch, type Ref } from 'vue'
import { getReport } from '../api/report'
import { getGraphData } from '../api/graph'
import type { ShelfObject } from '../types/shelf'

/**
 * Nachladen der Objektdetails fuer das Dossier (Block B3).
 *
 * Die Ablage-Liste kennt nur, was die Listen-Endpunkte liefern — Titel,
 * Status, Zeitpunkt. Fuer die Uebersicht rechts fehlt damit genau das,
 * was ein Dossier ausmacht: die Bestandteile. Die werden erst beim
 * Auswaehlen geholt, nicht fuer alle Zeilen im Voraus.
 *
 * Sorten ohne eigenen Detail-Endpunkt (Lauf, Personasatz) liefern
 * bewusst nichts zurueck statt eines leeren Geruests — das Dossier
 * zeigt dann weiter seine KPI-Reihe.
 */

export interface DetailPart {
  title: string
  description: string
}

export interface ObjectDetail {
  /** Fliesstext-Zusammenfassung, wenn die Quelle eine hat. */
  summary: string
  /** Bestandteile: Berichtsabschnitte bzw. Graph-Kennzahlen. */
  parts: DetailPart[]
}

export function useObjectDetail(object: Ref<ShelfObject | null>) {
  const detail = ref<ObjectDetail | null>(null)
  const loading = ref(false)

  async function load(obj: ShelfObject | null): Promise<void> {
    detail.value = null
    if (!obj) return
    loading.value = true
    try {
      if (obj.kind === 'bericht') {
        const res = await getReport(obj.id)
        const outline = res?.success ? res.data?.outline : null
        if (outline) {
          detail.value = {
            summary: outline.summary,
            parts: outline.sections.map((s) => ({ title: s.title, description: s.description })),
          }
        }
      } else if (obj.kind === 'graph') {
        // Der Graph selbst haengt am graph_id des Projekts; die Ablage
        // fuehrt das Projekt. Ohne Graph-ID gibt es nichts zu zeigen.
        const graphId = obj.graphId
        if (graphId) {
          const res = await getGraphData(graphId)
          const data = res?.success ? res.data : null
          if (data) {
            detail.value = {
              summary: '',
              parts: [
                { title: 'Entitäten', description: String(data.nodes?.length ?? 0) },
                { title: 'Beziehungen', description: String(data.edges?.length ?? 0) },
              ],
            }
          }
        }
      }
    } catch {
      // Ein fehlgeschlagenes Nachladen darf die Ablage nicht stoeren —
      // das Dossier faellt auf seine KPI-Reihe zurueck.
      detail.value = null
    } finally {
      loading.value = false
    }
  }

  watch(object, (obj) => void load(obj), { immediate: true })

  return { detail, loading }
}
