<script setup lang="ts">
/**
 * Rechte Spalte der Interviews (#1805, Etappe 6). In diesem Ticket nur die
 * wiederverwendete `PersonaCard`; das Folgeticket ergänzt "Beiträge im Feed"
 * und "Im Bericht zitiert".
 *
 * Schnittstelle: Props `selection` (geparste conversationId oder null) und
 * `personaById`. Bei Gruppen oder ohne Auswahl bleibt die Karte leer.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import PersonaCard from '@/components/run/simulation/PersonaCard.vue'
import type { RunPersona } from '@/composables/run/simulation/useRunPersonas'
import type { ParsedConversationId } from '@/composables/run/interviews/conversations'

const props = defineProps<{
  selection: ParsedConversationId | null
  personaById: (personaId: string) => RunPersona | null
}>()
const { t } = useI18n()

const persona = computed(() =>
  props.selection?.kind === 'persona' ? props.personaById(String(props.selection.agentId)) : null,
)
const fallbackName = computed(() =>
  props.selection?.kind === 'persona' && !persona.value
    ? t('views.run.interviews.agentFallback', { n: props.selection.agentId })
    : null,
)
</script>

<template>
  <aside class="ipane" data-testid="interview-persona-pane">
    <PersonaCard :persona="persona" :fallback-name="fallbackName" />
  </aside>
</template>

<style scoped>
.ipane {
  min-width: 0;
}
</style>
