import { ref, watch, type Ref } from 'vue'
import { getReport } from '../api/report'
import { getGraphData } from '../api/graph'
import { listPersonaTemplates } from '../api/simulation'
import type { ShelfObject } from '../types/shelf'

type Translate = (key: string) => string

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

export function useObjectDetail(object: Ref<ShelfObject | null>, t: Translate) {
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
      } else if (obj.kind === 'personasatz') {
        // Die Bibliothek liefert alle Saetze auf einmal; einen Endpunkt
        // fuer einen einzelnen gibt es nicht. Der Eintrag wird deshalb
        // aus der Liste herausgesucht statt neu abgefragt.
        const res = await listPersonaTemplates()
        const all = res?.success ? (res.data?.templates ?? []) : []
        const tpl = all.find(
          (x) => x.template_id === obj.id || x.username === obj.id || x.name === obj.id,
        )
        if (tpl) {
          const topics = Array.isArray(tpl.interested_topics)
            ? (tpl.interested_topics as unknown[]).join(', ')
            : typeof tpl.interested_topics === 'string'
              ? tpl.interested_topics
              : ''
          const parts: DetailPart[] = []
          if (tpl.profession) parts.push({ title: t('shelf.dossier.personaProfession'), description: String(tpl.profession) })
          if (tpl.country) parts.push({ title: t('shelf.dossier.personaCountry'), description: String(tpl.country) })
          if (topics) parts.push({ title: t('shelf.dossier.personaTopics'), description: topics })
          if (tpl.bio) parts.push({ title: t('shelf.dossier.personaBio'), description: String(tpl.bio) })
          detail.value = { summary: tpl.persona ? String(tpl.persona) : '', parts }
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
                { title: t('shelf.dossier.graphEntities'), description: String(data.nodes?.length ?? 0) },
                { title: t('shelf.dossier.graphRelations'), description: String(data.edges?.length ?? 0) },
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
