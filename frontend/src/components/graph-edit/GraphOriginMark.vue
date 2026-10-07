<script setup lang="ts">
/**
 * Herkunftsmarke eines Knotens oder einer Kante (#1808, ADR-0022 §5).
 *
 * Bewusst Text UND Symbol: das Projekt hat ein Accessibility-Gate, und eine
 * nur farblich erkennbare Marke ist für Farbfehlsichtige und im Ausdruck
 * identisch mit einer extrahierten Kante. Das Symbol ist `aria-hidden`, der
 * Text traegt die Bedeutung.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { GraphEditTestId } from '@/contracts/testIds'
import type { GraphOrigin } from '@/contracts/graphEditContract'

const props = defineProps<{
  /** `null` heißt extrahiert (fehlendes Merkmal, Altbestand). */
  origin: GraphOrigin | null
  changedAt?: string | null
}>()

const { t } = useI18n()

const testId = computed(() =>
  props.origin === 'manual'
    ? GraphEditTestId.markManual
    : props.origin === 'edited'
      ? GraphEditTestId.markEdited
      : GraphEditTestId.markExtracted,
)

const label = computed(() => t(`views.graphEdit.origin.${props.origin ?? 'extracted'}`))
</script>

<template>
  <span class="gom" :class="`gom--${origin ?? 'extracted'}`" :data-testid="testId">
    <span aria-hidden="true" class="gom__sym">✎</span>
    <span class="gom__label">{{ label }}</span>
    <span v-if="origin === 'edited' && changedAt" class="gom__when">
      {{ t('views.graphEdit.origin.changedAt', { date: changedAt }) }}
    </span>
  </span>
</template>

<style scoped>
.gom {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  padding: 1px 8px;
  border-radius: var(--ag-r-pill);
  background: var(--s3);
  color: var(--fg2);
  font-size: 11.5px;
  font-weight: 600;
  white-space: nowrap;
}

/* Handarbeit bekommt einen eigenen Ton, aber die Marke bleibt auch ohne Farbe lesbar. */
.gom--manual,
.gom--edited {
  background: var(--acc-soft);
  color: var(--acc-text);
}

.gom__sym {
  font-size: 12px;
}

.gom__when {
  font-weight: 400;
  font-size: 11px;
}
</style>