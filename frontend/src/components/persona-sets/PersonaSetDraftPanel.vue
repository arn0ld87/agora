<script setup lang="ts">
/**
 * KI-Entwurf im Personasatz (#1807, E7-F3): Auftrag an das Modell, Vorschau des
 * Beispielbeitrags.
 *
 * Zwei getrennte Fehler, weil zwei getrennte Handlungen daraus folgen. Ein nicht
 * erreichbarer Anbieter (502) ist nicht der Fehler des Auftrags — der nächste
 * Versuch hilft, und die Oberfläche sagt das, statt den Nutzer am Brief zweifeln
 * zu lassen. Ein abgelehnter Auftrag (400) ist umgekehrt am Brief.
 *
 * Der Entwurf wird **nicht** gespeichert, nur angezeigt: der Nutzer entscheidet,
 * ob der Eintrag bleibt. Die Kartenliste bekommt ihn erst über den Server.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PersonaDraftExamplePost } from '@/contracts/personaSetContract'
import { PersonaSetDetailTestId as Id } from './detailTestIds'

const props = defineProps<{
  /** Der Auftrag läuft gerade. */
  drafting: boolean
  /** 502: der Anbieter war schuld, nicht der Auftrag. */
  providerError: boolean
  /** 400 oder ein Fehler, der den Auftrag betrifft. */
  actionError: string | null
  /** Beispielbeitrag des letzten Entwurfs, getrennt vom Eintrag. */
  example: PersonaDraftExamplePost | null
  /** Der Satz ist gesperrt: Entwürfe sind dann nicht möglich. */
  locked: boolean
}>()
const emit = defineEmits<{ (e: 'draft', brief: string): void; (e: 'dismiss'): void }>()
const { t } = useI18n()

const brief = ref('')
const trimmed = computed(() => brief.value.trim())
const canSubmit = computed(() => trimmed.value.length > 0 && !props.drafting && !props.locked)

function submit(): void {
  if (!canSubmit.value) return
  emit('draft', trimmed.value)
}
</script>

<template>
  <section class="pdraft" :data-testid="Id.draft">
    <h3 class="pdraft__title">{{ t('views.personaSets.detail.draft.title') }}</h3>

    <form v-if="!locked" class="pdraft__form" @submit.prevent="submit">
      <label class="pdraft__label" :for="Id.draftBrief">{{ t('views.personaSets.detail.draft.brief') }}</label>
      <textarea
        :id="Id.draftBrief"
        v-model="brief"
        class="pdraft__brief"
        rows="3"
        maxlength="2000"
        :placeholder="t('views.personaSets.detail.draft.briefPlaceholder')"
        :disabled="drafting"
        :data-testid="Id.draftBrief"
      />
      <button type="submit" :disabled="!canSubmit" :data-testid="Id.draftSubmit">
        {{ drafting ? t('views.personaSets.detail.draft.running') : t('views.personaSets.detail.draft.submit') }}
      </button>
    </form>

    <p v-else class="pdraft__locked" role="status" :data-testid="Id.draftLocked">
      {{ t('views.personaSets.detail.draft.locked') }}
    </p>

    <!-- Die zwei Fehler bleiben getrennt: ein 502 betrifft den Anbieter und ist
         durch einen anderen Brief nicht behebbar, das steht hier auch so. -->
    <p v-if="providerError" role="alert" class="pdraft__error" :data-testid="Id.draftProviderError">
      {{ t('views.personaSets.detail.draft.providerError') }}
    </p>
    <p v-else-if="actionError" role="alert" class="pdraft__error" :data-testid="Id.draftActionError">
      {{ actionError }}
    </p>

    <figure v-if="example" class="pdraft__preview" :data-testid="Id.draftPreview">
      <figcaption class="pdraft__previewHead">
        <span class="pdraft__sim" aria-hidden="true">SIM</span>
        {{ t('views.personaSets.detail.draft.previewLabel') }}
        <span class="pdraft__network">{{ example.network }}</span>
      </figcaption>
      <blockquote class="pdraft__quote">{{ example.content }}</blockquote>
      <button type="button" class="pdraft__dismiss" :data-testid="Id.draftDismiss" @click="emit('dismiss')">
        {{ t('views.personaSets.detail.draft.dismiss') }}
      </button>
    </figure>
  </section>
</template>

<style scoped>
.pdraft {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2, 8px);
  padding: var(--sp-4, 16px);
  border: 1px solid var(--hairline, var(--border-subtle));
  border-radius: var(--r-7, var(--r-3));
}
.pdraft__title { margin: 0; font-size: var(--fs-3, 1rem); }
.pdraft__form { display: flex; flex-direction: column; gap: var(--sp-2, 8px); }
.pdraft__label { font-size: var(--fs-1, 0.875rem); color: var(--text-secondary, var(--fg-muted)); }
.pdraft__brief {
  font: inherit;
  padding: var(--sp-2, 8px);
  border: 1px solid var(--hairline, var(--border-subtle));
  border-radius: var(--r-2, var(--r-1));
  background: var(--surface, var(--bg-elevated));
  color: inherit;
  resize: vertical;
}
.pdraft__error { margin: 0; color: var(--danger, var(--danger-fg)); }
.pdraft__locked { margin: 0; color: var(--text-secondary, var(--fg-muted)); }
.pdraft__preview {
  margin: 0;
  padding: var(--sp-3, 12px);
  border-left: 3px solid var(--accent, var(--accent-border));
  background: var(--surface-elevated, var(--bg-elevated));
}
.pdraft__previewHead {
  display: flex;
  align-items: center;
  gap: var(--sp-2, 8px);
  font-size: var(--fs-1, 0.875rem);
  color: var(--text-secondary, var(--fg-muted));
}
.pdraft__sim {
  padding: 0 var(--sp-1, 4px);
  border: 1px solid var(--hairline-strong, var(--hairline));
  border-radius: var(--r-1, 2px);
  font-size: var(--fs-0, 0.75rem);
  letter-spacing: 0.04em;
}
.pdraft__network { margin-inline-start: auto; }
.pdraft__quote { margin: var(--sp-2, 8px) 0 0; }
.pdraft__dismiss {
  margin-block-start: var(--sp-2, 8px);
  font: inherit;
  background: none;
  border: none;
  color: var(--text-secondary, var(--fg-muted));
  text-decoration: underline;
  cursor: pointer;
}
</style>
