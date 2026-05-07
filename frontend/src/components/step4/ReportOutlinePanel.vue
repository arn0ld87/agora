<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Badge from '../ui/Badge.vue'
import Kicker from '../ui/Kicker.vue'
import ConfidenceBadge from '../ui/ConfidenceBadge.vue'
import { aggregateSectionConfidence } from '../../utils/confidenceUtils'
import type { SectionConfidenceResult } from '../../utils/confidenceUtils'
import type { ReportOutline, ReportSection } from '../../contracts/reportContract'

interface Props {
  outline: ReportOutline
  generatedSections: Record<string, unknown>
  sectionHtml: Record<string, string>
  currentSectionIndex: number | null
  evidenceSections: ReportSection[]
}

const props = defineProps<Props>()
const { t } = useI18n()
const collapsedSections = ref(new Set<number>())

function toggleSection(i: number) {
  const next = new Set(collapsedSections.value)
  next.has(i) ? next.delete(i) : next.add(i)
  collapsedSections.value = next
}

function sectionConfidence(idx: number): SectionConfidenceResult | null {
  if (!props.evidenceSections.length) return null
  const section = props.evidenceSections.find(s => s.section_index === idx + 1) ?? null
  if (!section) return null
  return aggregateSectionConfidence(section)
}

function sectionConfidenceScore(idx: number): number {
  return sectionConfidence(idx)?.score ?? 0
}

function sectionConfidenceLabel(idx: number): 'low' | 'medium' | 'high' | 'verified' {
  return sectionConfidence(idx)?.label ?? 'low'
}

function sectionConfidenceAuditTrail(idx: number): SectionConfidenceResult['auditTrail'] {
  return sectionConfidence(idx)?.auditTrail ?? []
}
</script>

<template>
  <article class="card">
    <header class="card-head">
      <Kicker num="02">{{ t('step4.view.sections') }}</Kicker>
      <Badge variant="ghost">{{ Object.keys(generatedSections).length }} / {{ outline.sections.length }}</Badge>
    </header>
    <ol class="outline">
      <li
        v-for="(sec, i) in outline.sections"
        :key="i"
        :class="{ 'is-current': currentSectionIndex === i }"
      >
        <header class="outline-head" @click="toggleSection(i)">
          <span class="outline-num">{{ String(i + 1).padStart(2, '0') }}</span>
          <span class="outline-title">{{ sec.title }}</span>
          <span class="outline-badges">
            <ConfidenceBadge
              v-if="sectionConfidence(i)"
              :score="sectionConfidenceScore(i)"
              :label="sectionConfidenceLabel(i)"
              :audit-trail="sectionConfidenceAuditTrail(i)"
            />
            <Badge :variant="generatedSections[i + 1] ? 'solid' : 'ghost'">
              {{ generatedSections[i + 1] ? '✓' : (currentSectionIndex === i ? '…' : '—') }}
            </Badge>
          </span>
        </header>
        <div
          v-if="generatedSections[i + 1] && !collapsedSections.has(i)"
          class="outline-body"
        >
          <div class="section-content markdown-body" v-html="sectionHtml[i + 1] || ''"></div>
        </div>
      </li>
    </ol>
  </article>
</template>

<style scoped>
.card {
  background: var(--bg);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-3);
}
.outline {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
}
.outline li {
  border-top: 1px solid var(--rule);
  padding: var(--s-3) 0;
}
.outline li:last-child {
  border-bottom: 1px solid var(--rule);
}
.outline-head {
  display: grid;
  grid-template-columns: 32px 1fr auto;
  gap: var(--s-3);
  align-items: center;
  cursor: pointer;
}
.outline-badges {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}
.outline-num {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  color: var(--fg-muted);
}
.outline-title {
  font-family: var(--ff-serif);
  font-size: var(--fs-20);
  color: var(--fg);
}
.outline-body {
  margin-top: var(--s-3);
  padding-left: 32px;
}
.section-content {
  font-family: var(--ff-serif);
  font-size: var(--fs-16);
  line-height: 1.7;
  color: var(--fg);
  margin: 0;
}
.outline li.is-current .outline-title {
  color: var(--accent);
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  font-family: var(--ff-serif);
  color: var(--fg);
  line-height: 1.25;
  margin: 1.8em 0 0.4em;
  font-weight: 500;
}
.markdown-body :deep(p) {
  margin: 0.9em 0;
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.9em 0 0.9em 1.4em;
  padding: 0;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--accent);
  margin: 1em 0;
  padding: 0.2em 1em;
  color: var(--fg-muted);
  font-style: italic;
}
.markdown-body :deep(code) {
  background: var(--bg-elevated);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: var(--ff-mono);
  font-size: 0.9em;
}
</style>
