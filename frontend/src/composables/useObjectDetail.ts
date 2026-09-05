import { ref, watch, type Ref } from 'vue'
import { getReport, getReportEvidence } from '../api/report'
import { getGraphData } from '../api/graph'
import { listPersonaTemplates } from '../api/simulation'
import type { ConfidenceLabel } from '../contracts/reportContract'
import type { NextAction, ShelfObject } from '../types/shelf'

type Translate = (key: string, values?: Record<string, unknown>) => string

/**
 * Nachladen der Objektdetails fuer das Dossier (Block B3).
 *
 * Die Ablage-Liste kennt nur, was die Listen-Endpunkte liefern — Titel,
 * Status, Zeitpunkt. Fuer die Uebersicht rechts fehlt damit genau das,
 * was ein Dossier ausmacht: die Bestandteile. Die werden erst beim
 * Auswaehlen geholt, nicht fuer alle Zeilen im Voraus.
 *
 * Personasatz bleibt ohne eigenen Detail-Endpunkt (die Bibliothek liefert
 * alle Saetze auf einmal, siehe unten). Lauf traegt seit Redesign PR 4
 * Bestandteile (Akteure, Ausgabe) — beide aus bereits geladenen Daten
 * (obj.jobs, obj.personaCount) plus ggf. einem Report-Nachschlag fuer die
 * Ausgabe, kein neuer Lauf-Endpunkt. Liefert eine Sorte nichts, zeigt das
 * Dossier weiter seine KPI-Reihe statt eines leeren Geruests.
 */

export interface DetailPart {
  title: string
  description: string
  /** Zahl neben dem Bestandteil (Redesign PR 4: "Bestandteile mit Zahl + Link"). */
  count?: number
  /** Weiter-Link des Bestandteils, wenn ein Routenziel existiert. */
  to?: NextAction['to']
}

/** Redesign PR 4: Vertrauensverteilung eines Berichts (Anzahl Claims je Label). */
export type ConfidenceDistribution = Partial<Record<ConfidenceLabel, number>>

export interface ObjectDetail {
  /** Fliesstext-Zusammenfassung, wenn die Quelle eine hat. */
  summary: string
  /** Bestandteile: Berichtsabschnitte, Graph-Kennzahlen bzw. Lauf-Verlinkungen. */
  parts: DetailPart[]
  /** Nur bei kind='bericht': Anzahl Belege je Confidence-Label. */
  confidenceDistribution?: ConfidenceDistribution
  /** Nur bei kind='bericht': Gesamtzahl Aussagen (Claims) ueber alle Abschnitte. */
  claimsCount?: number
  /** Nur bei kind='bericht': Datenluecken ueber alle Abschnitte. */
  gapsCount?: number
  /** Nur bei kind='bericht': Belegte Abschnitte laut Report-Contract. */
  evidenceSections?: number
  /** Nur bei kind='bericht': Red-Team-Befunde im Klartext. */
  redTeamFindings?: string[]
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
        const report = res?.success ? res.data : null
        const outline = report?.outline
        if (outline) {
          detail.value = {
            summary: outline.summary,
            parts: outline.sections.map((s) => ({ title: s.title, description: s.description })),
            evidenceSections: report?.evidence_sections,
            redTeamFindings: report?.red_team_findings,
          }
        }
        // Confidence-Verteilung und Aussagenzahl leben in der Evidence-Map
        // (sections[].claims[]), nicht im Report selbst — separater
        // bestehender Endpunkt (GET /api/report/<id>/evidence). Ein
        // Fehlschlag hier verwirft nicht die bereits gesetzte Outline.
        try {
          const evidenceRes = await getReportEvidence(obj.id)
          const evidence = evidenceRes?.success ? evidenceRes.data : null
          if (evidence && detail.value) {
            const distribution: ConfidenceDistribution = {}
            let claimsCount = 0
            let gapsCount = 0
            for (const section of evidence.sections) {
              claimsCount += section.claims.length
              gapsCount += section.data_gaps.length
              for (const claim of section.claims) {
                distribution[claim.confidence_label] = (distribution[claim.confidence_label] ?? 0) + 1
              }
            }
            detail.value = { ...detail.value, confidenceDistribution: distribution, claimsCount, gapsCount }
          }
        } catch {
          // Evidence-Map ohne Report zu zeigen waere schlimmer als Report
          // ohne Evidence-Kennzahlen — deshalb kein Rethrow, kein Reset.
        }
      } else if (obj.kind === 'lauf') {
        // Bestandteile eines Laufs: Akteure (Personas) und Ausgabe
        // (verknuepfter Bericht), jeweils mit Zahl + Weiter-Link (Redesign
        // PR 4). Beide Verknuepfungen kommen aus den bereits geladenen
        // Jobs (obj.jobs), kein zusaetzlicher Lauf-Endpunkt.
        const parts: DetailPart[] = []
        const jobs = obj.jobs ?? []
        const envSetupTarget = jobs
          .map((j) => (j.linkedIds.simulation_id as string | undefined) ?? (j.linkedIds.project_id as string | undefined))
          .find((v): v is string => typeof v === 'string' && v.length > 0)
        if (typeof obj.personaCount === 'number' && envSetupTarget) {
          parts.push({
            title: t('views.dossier.parts.actors'),
            description: t('views.dossier.parts.actorsDesc', { n: obj.personaCount }),
            count: obj.personaCount,
            to: { name: 'StepEnvSetup', params: { projectId: envSetupTarget } },
          })
        }
        const reportId = jobs
          .map((j) => j.linkedIds.report_id as string | undefined)
          .find((v): v is string => typeof v === 'string' && v.length > 0)
        if (reportId) {
          const res = await getReport(reportId)
          const report = res?.success ? res.data : null
          if (report) {
            parts.push({
              title: t('views.dossier.parts.output'),
              description: t('views.dossier.parts.outputDesc', { n: report.evidence_sections }),
              count: report.evidence_sections,
              to: { name: 'StepReport', params: { reportId } },
            })
          }
        }
        if (parts.length > 0) detail.value = { summary: '', parts }
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
