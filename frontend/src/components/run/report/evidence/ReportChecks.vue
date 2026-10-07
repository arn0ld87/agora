<script setup lang="ts">
/**
 * Prüfhinweise des Berichts (Etappe 5, #1804): Binding-/Gate-Probleme, also
 * zitierte Belege ohne Bindung (`unbound_evidence_refs`), im Text verbliebene
 * unbelegte Aussagen (`unverified_statements`), Gate-Entscheidungen
 * (`gate_decision_log`) und abgestufte Claims (`degradation_log`). Einklappbar,
 * die Zahl steht im Titel. Ein fehlgeschlagenes Binding ist ein Problem der
 * Prüfung und nie eine Datenlücke; Datenlücken stehen in der Claim-Liste.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ReportChecks } from '@/composables/run/report/reportClaims'
import type { EvidenceDegradation } from '@/contracts/reportContract'

const props = defineProps<{ checks: ReportChecks }>()
const { t } = useI18n()

const hasAny = computed(() => props.checks.total > 0)

function line(d: EvidenceDegradation): string {
  return t('views.run.report.checks.entry', {
    claim: d.claim_id,
    n: d.section_index,
    violation: d.violation,
    action: d.action,
    detail: d.detail,
  })
}
</script>

<template>
  <details class="rk" data-testid="report-checks">
    <summary class="rk__summary" data-testid="report-checks-summary">
      {{ t('views.run.report.checks.title', { n: checks.total }) }}
    </summary>
    <div class="rk__body">
      <p class="rk__note">{{ t('views.run.report.checks.intro') }}</p>
      <p v-if="!hasAny" class="rk__note" data-testid="report-checks-none">{{ t('views.run.report.checks.none') }}</p>

      <section v-if="checks.unbound.length > 0" data-testid="report-checks-unbound">
        <h4 class="rk__sub">{{ t('views.run.report.checks.unbound.title') }}</h4>
        <ul class="rk__list">
          <li v-for="u in checks.unbound" :key="u.sectionIndex">
            {{ t('views.run.report.checks.unbound.item', { n: u.sectionIndex, title: u.sectionTitle, refs: u.refs.join(', ') }) }}
          </li>
        </ul>
      </section>

      <section v-if="checks.unverified.length > 0" data-testid="report-checks-unverified">
        <h4 class="rk__sub">{{ t('views.run.report.checks.unverified.title') }}</h4>
        <ul class="rk__list">
          <template v-for="u in checks.unverified" :key="u.sectionIndex">
            <li v-for="(s, i) in u.statements" :key="`${u.sectionIndex}-${i}`">
              {{
                t('views.run.report.checks.unverified.item', {
                  n: u.sectionIndex,
                  text: s.statement_text,
                  verdict: s.verdict,
                  reason: s.reason,
                })
              }}
            </li>
          </template>
        </ul>
      </section>

      <section v-if="checks.gateDecisions.length > 0" data-testid="report-checks-gate">
        <h4 class="rk__sub">{{ t('views.run.report.checks.gate.title') }}</h4>
        <ul class="rk__list">
          <li v-for="(d, i) in checks.gateDecisions" :key="i">{{ line(d) }}</li>
        </ul>
      </section>

      <section v-if="checks.degradations.length > 0" data-testid="report-checks-degradation">
        <h4 class="rk__sub">{{ t('views.run.report.checks.degradation.title') }}</h4>
        <ul class="rk__list">
          <li v-for="(d, i) in checks.degradations" :key="i">{{ line(d) }}</li>
        </ul>
      </section>
    </div>
  </details>
</template>

<style scoped>
.rk {
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
}
.rk__summary {
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 650;
  color: var(--fg);
  cursor: pointer;
}
.rk__summary:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.rk__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 10px 10px;
}
.rk__note {
  margin: 0;
  font-size: 12px;
  color: var(--fg2);
}
.rk__sub {
  margin: 0 0 2px;
  font-size: 12px;
  font-weight: 650;
  color: var(--fg3);
}
.rk__list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--fg);
  overflow-wrap: anywhere;
}
</style>
