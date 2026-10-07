<script setup lang="ts">
/**
 * Sprung eines Belegs an seinen Ursprung (Etappe 5, #1804, Bauplan 4.6). Füllt den
 * Slot `jump` von `ReportEvidenceList`. Ziele und Regeln: `evidenceJumps.ts`.
 *
 * Feed-Sprung nur verifiziert: der Link erscheint erst, wenn der Beitrag im
 * Feed-Snapshot existiert und sein Text zum Beleg passt. Bis dahin ein neutraler
 * Hinweis; bei Abweichung oder Ladefehler ein Hinweis statt Link. Ohne Ziel (auch
 * `inferred`) steht ein ruhiger Grund, nie ein Link.
 *
 * Mehrere Knoten (`entity_summary`): der Beleg trägt nur UUIDs, keine Namen. Darum
 * ein Link je Knoten, nummeriert „(n/m)"; mit Kontext im zugänglichen Namen.
 *
 * Prop `item`          Beleg samt Bindung
 * Prop `simulationId`  Lauf (Ziel der Routen)
 * Prop `reportId`      Berichtsfassung für den Rückweg, sonst `null`
 * Prop `claimId`       gewählter Claim für den Rückweg, sonst `null`
 * Prop `feedState`     Zustand des Feed-Snapshots
 * Prop `feedPosts`     Beiträge des Snapshots
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ClaimEvidenceView } from '@/composables/run/report/reportClaims'
import {
  type NoJumpReason,
  feedRoute,
  graphRoute,
  interviewRoute,
  resolveEvidenceJump,
  verifyFeedJump,
} from '@/composables/run/report/evidenceJumps'
import type { EvidenceFeedState } from '@/composables/run/report/useEvidenceFeedCheck'

const props = defineProps<{
  item: ClaimEvidenceView
  simulationId: string
  reportId: string | null
  claimId: string | null
  feedState: EvidenceFeedState
  feedPosts: ReadonlyArray<{ post_id: string; body: string }>
}>()
const { t } = useI18n()

const ctx = computed(() => ({ simulationId: props.simulationId, claimId: props.claimId, reportId: props.reportId }))
const target = computed(() => resolveEvidenceJump(props.item.record))
const source = computed(() => props.item.record.source)

type Feed =
  | { kind: 'link'; to: ReturnType<typeof feedRoute> }
  | { kind: 'note'; key: 'checking' | 'feedFailed' | 'postMissing' | 'textMismatch' }
const feed = computed<Feed | null>(() => {
  const jump = target.value
  if (jump.kind !== 'feed') return null
  if (props.feedState === 'error') return { kind: 'note', key: 'feedFailed' }
  if (props.feedState !== 'ready') return { kind: 'note', key: 'checking' }
  const check = verifyFeedJump(jump.postId, props.item.record, props.feedPosts)
  return check.ok ? { kind: 'link', to: feedRoute(check.postId, ctx.value) } : { kind: 'note', key: check.reason }
})

const noReason = computed<NoJumpReason | null>(() => (target.value.kind === 'none' ? target.value.reason : null))
const nodes = computed(() => (target.value.kind === 'graph' ? target.value.nodeUuids : []))
</script>

<template>
  <span class="rej" data-testid="report-evidence-jump">
    <template v-if="feed">
      <RouterLink
        v-if="feed.kind === 'link'"
        :to="feed.to"
        class="rej__link"
        :aria-label="t('views.run.report.evidence.jump.feedLabel', { source })"
        data-testid="report-jump-feed"
      >
        {{ t('views.run.report.evidence.jump.feed') }}
      </RouterLink>
      <span v-else class="rej__note" role="status" data-testid="report-jump-note" :data-reason="feed.key">
        {{ t(`views.run.report.evidence.jump.note.${feed.key}`) }}
      </span>
    </template>

    <template v-else-if="target.kind === 'graph'">
      <RouterLink
        v-for="(uuid, i) in nodes"
        :key="uuid"
        :to="graphRoute(uuid, ctx)"
        class="rej__link"
        :aria-label="t('views.run.report.evidence.jump.graphLabel', { source, n: i + 1, total: nodes.length })"
        data-testid="report-jump-graph"
      >
        {{
          nodes.length > 1
            ? t('views.run.report.evidence.jump.graphNth', { n: i + 1, total: nodes.length })
            : t('views.run.report.evidence.jump.graph')
        }}
      </RouterLink>
    </template>

    <RouterLink
      v-else-if="target.kind === 'interview'"
      :to="interviewRoute(ctx)"
      class="rej__link"
      :aria-label="t('views.run.report.evidence.jump.interviewLabel', { source })"
      data-testid="report-jump-interview"
    >
      {{ t('views.run.report.evidence.jump.interview') }}
    </RouterLink>

    <span v-else-if="noReason" class="rej__note" data-testid="report-jump-note" :data-reason="noReason">
      {{ t(`views.run.report.evidence.jump.note.${noReason}`) }}
    </span>
  </span>
</template>

<style scoped>
.rej {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.rej__link {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
}
.rej__link:hover {
  background: var(--s4);
}
.rej__link:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.rej__note {
  font-size: 12px;
  color: var(--fg2);
}
</style>
