<script setup lang="ts">
import { useId } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps({
  modelValue: { type: String, required: true },
  isPreparing: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const fieldId = useId()
</script>

<template>
  <div class="contested-question-field">
    <label class="contested-question-label" :for="fieldId">
      {{ t('step2.contestedQuestion.label') }}
    </label>
    <textarea
      :id="fieldId"
      class="contested-question-input"
      rows="2"
      maxlength="300"
      :value="modelValue"
      :disabled="isPreparing"
      :aria-describedby="`${fieldId}-hint`"
      @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
    ></textarea>
    <p :id="`${fieldId}-hint`" class="hint">{{ t('step2.contestedQuestion.hint') }}</p>
  </div>
</template>

<style scoped>
.contested-question-field {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.contested-question-label {
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg);
}
.contested-question-input {
  width: 100%;
  background: transparent;
  border: 1px solid var(--rule-strong);
  font-family: var(--font-sans);
  font-size: var(--fs-16);
  padding: var(--s-2);
  color: var(--fg);
  outline: none;
  resize: vertical;
}
.contested-question-input:focus { border-color: var(--accent); }
.hint {
  font-family: var(--font-sans);
  font-size: 11px;
  color: var(--fg-muted);
  margin: 0;
}
</style>
