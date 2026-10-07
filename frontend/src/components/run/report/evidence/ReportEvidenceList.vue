<script setup lang="ts">
/**
 * Belege des gewählten Claims (Etappe 5, #1804, Bauplan 4.6), nach Quellenart
 * gruppiert: Klartext-Etikett, Auszug, Herkunft (Quelle/Anker, Stimme, Gruppe),
 * Bindung an den Claim (stützt, widerspricht, Entailment) und ein Knopf zum
 * Kopieren des Auszugs. Ohne Auswahl: Hinweis und Übersicht der Quellenarten.
 *
 * Prop   `claim`      gewählter Claim samt Belegen, sonst `null`
 * Prop   `overview`   Belege je Quellenart über den ganzen Bericht
 * Slot   `jump`       (Prop `item`) Sprung an den Ursprung eines Belegs
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { groupEvidenceByKind, type ClaimEvidenceView, type ClaimView } from '@/composables/run/report/reportClaims'
import type { EvidenceSourceKind } from '@/contracts/reportContract'

const props = defineProps<{
  claim: ClaimView | null
  overview: Array<{ kind: EvidenceSourceKind; count: number }>
}>()
const { t } = useI18n()

const groups = computed(() => (props.claim ? groupEvidenceByKind(props.claim.evidence) : []))
const overviewTotal = computed(() => props.overview.reduce((n, o) => n + o.count, 0))
const copied = ref<string | null>(null)
const copyFailed = ref(false)

function excerpt(item: ClaimEvidenceView): string {
  return item.record.quote || item.record.snippet
}

function bindingKey(item: ClaimEvidenceView): 'supports' | 'contradicts' | 'neutral' {
  if (item.binding.contradicts_claim === true) return 'contradicts'
  if (item.binding.supports_claim === true) return 'supports'
  return 'neutral'
}

async function copy(item: ClaimEvidenceView): Promise<void> {
  copyFailed.value = false
  try {
    await navigator.clipboard.writeText(excerpt(item))
    copied.value = item.evidenceId
  } catch {
    copied.value = null
    copyFailed.value = true
  }
}
</script>

<template>
  <section class="rel" aria-labelledby="report-evidence-title" data-testid="report-evidence-list">
    <h3 id="report-evidence-title" class="rel__title">{{ t('views.run.report.evidence.title') }}</h3>

    <template v-if="!claim">
      <p class="rel__note" data-testid="report-evidence-hint">{{ t('views.run.report.evidence.noSelection') }}</p>
      <template v-if="overviewTotal > 0">
        <p class="rel__note" data-testid="report-evidence-overview-total">
          {{ t('views.run.report.evidence.overviewTotal', { n: overviewTotal }, overviewTotal) }}
        </p>
        <ul class="rel__overview" data-testid="report-evidence-overview">
          <li v-for="o in overview" :key="o.kind">{{ t(`views.run.report.evidence.kind.${o.kind}`) }}: {{ o.count }}</li>
        </ul>
      </template>
    </template>

    <template v-else>
      <p class="rel__note" data-testid="report-evidence-for">
        {{ t('views.run.report.evidence.forClaim', { id: claim.claimId }) }}
      </p>
      <p v-if="claim.evidence.length === 0" class="rel__note" data-testid="report-evidence-none">
        {{ t('views.run.report.evidence.none') }}
      </p>
      <p v-if="claim.missingEvidence > 0" class="rel__problem" role="alert" data-testid="report-evidence-missing">
        {{ t('views.run.report.evidence.missing', { n: claim.missingEvidence }, claim.missingEvidence) }}
      </p>

      <section v-for="group in groups" :key="group.kind" class="rel__group" data-testid="report-evidence-group" :data-kind="group.kind">
        <h4 class="rel__kind">{{ t(`views.run.report.evidence.kind.${group.kind}`) }} ({{ group.items.length }})</h4>
        <ul class="rel__items">
          <li v-for="item in group.items" :key="item.evidenceId" class="rel__item" data-testid="report-evidence-item">
            <blockquote class="rel__excerpt">{{ excerpt(item) }}</blockquote>
            <dl class="rel__origin" :aria-label="t('views.run.report.evidence.origin')">
              <div>
                <dt>{{ t('views.run.report.evidence.sourceLabel') }}</dt>
                <dd>{{ item.record.source }}</dd>
              </div>
              <div v-if="item.record.source_id_anchor">
                <dt>{{ t('views.run.report.evidence.anchorLabel') }}</dt>
                <dd>{{ item.record.source_id_anchor }}</dd>
              </div>
              <div v-if="item.record.voice_key">
                <dt>{{ t('views.run.report.evidence.voiceLabel') }}</dt>
                <dd>{{ item.record.voice_key }}</dd>
              </div>
              <div v-if="item.record.persona_stakeholder_group">
                <dt>{{ t('views.run.report.evidence.groupLabel') }}</dt>
                <dd>{{ item.record.persona_stakeholder_group }}</dd>
              </div>
              <div>
                <dt>{{ t('views.run.report.evidence.bindingLabel') }}</dt>
                <dd>
                  {{ t(`views.run.report.evidence.binding.${bindingKey(item)}`) }}
                  <template v-if="item.binding.entailment"> · {{ t(`views.run.report.evidence.entailment.${item.binding.entailment}`) }}</template>
                </dd>
              </div>
            </dl>
            <div class="rel__actions">
              <button type="button" class="rel__btn" data-testid="report-evidence-copy" @click="copy(item)">
                {{ t('views.run.report.evidence.copy') }}
              </button>
              <slot name="jump" :item="item" />
            </div>
            <p v-if="copied === item.evidenceId" class="rel__note" role="status" data-testid="report-evidence-copied">
              {{ t('views.run.report.evidence.copied') }}
            </p>
          </li>
        </ul>
      </section>
      <p v-if="copyFailed" class="rel__problem" role="alert" data-testid="report-evidence-copy-failed">
        {{ t('views.run.report.evidence.copyFailed') }}
      </p>
    </template>
  </section>
</template>

<style scoped>
.rel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.rel__title {
  margin: 0;
  font-size: 13px;
  font-weight: 650;
  color: var(--fg);
}
.rel__note {
  margin: 0;
  font-size: 12px;
  color: var(--fg2);
}
.rel__problem {
  margin: 0;
  font-size: 12px;
  color: var(--err);
}
.rel__overview {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--fg2);
}
.rel__kind {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 650;
  color: var(--fg3);
}
.rel__items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.rel__item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
}
.rel__excerpt {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--fg);
  overflow-wrap: anywhere;
}
.rel__origin {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  font-size: 12px;
  color: var(--fg2);
}
.rel__origin div {
  display: flex;
  gap: 6px;
}
.rel__origin dt {
  font-weight: 600;
  color: var(--fg3);
}
.rel__origin dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.rel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.rel__btn {
  height: 28px;
  padding: 0 10px;
  border: 0;
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.rel__btn:hover {
  background: var(--s4);
}
.rel__btn:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
</style>
