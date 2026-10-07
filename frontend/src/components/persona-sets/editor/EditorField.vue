<script setup lang="ts">
/**
 * Ein beschriftetes Feld des Persona-Editors (#1807, E7-F3): Label (mit
 * Pflichtmarke), Hilfetext und Fehlertext. Das Bedienelement kommt im Slot und
 * erhält `id`, `describedby` und `invalid`, damit Hinweis und Fehler per
 * `aria-describedby` am Feld hängen.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  id: string
  label: string
  required?: boolean
  hint?: string
  error?: string | null
}>()
const { t } = useI18n()

const hintId = computed(() => `${props.id}-hint`)
const errorId = computed(() => `${props.id}-error`)
const describedby = computed(() => {
  const ids: string[] = []
  if (props.hint) ids.push(hintId.value)
  if (props.error) ids.push(errorId.value)
  return ids.length > 0 ? ids.join(' ') : undefined
})
</script>

<template>
  <div class="pe-field" :class="{ 'pe-field--invalid': !!error }">
    <label class="pe-field__label" :for="id">
      {{ label }}
      <template v-if="required">
        <span aria-hidden="true" class="pe-field__req">*</span>
        <span class="pe-sr">{{ t('views.personaSets.editor.required') }}</span>
      </template>
    </label>
    <slot :id="id" :describedby="describedby" :invalid="!!error" />
    <p v-if="hint" :id="hintId" class="pe-field__hint">{{ hint }}</p>
    <p v-if="error" :id="errorId" class="pe-field__error">
      <span aria-hidden="true">⚠ </span>{{ error }}
    </p>
  </div>
</template>
