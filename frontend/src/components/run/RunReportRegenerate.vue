<script setup lang="ts">
/**
 * "Neu erzeugen mit …" in der Berichtszeile (#1799, Ticket 6). Legt über
 * `POST /api/report/generate` mit `ai_model_ref` und `force_regenerate` eine
 * weitere Fassung an: neue `report_id`, nichts wird überschrieben. Fehler
 * (auch Budget- und Rate-Limit) bleiben im Dialog sichtbar. Der Auslöser ist
 * der DialogTrigger, damit der Fokus nach dem Schließen dorthin zurückkehrt.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
  DialogTrigger,
} from 'reka-ui'
import AiModelPicker from '@/components/v4/forms/AiModelPicker.vue'
import { generateReport, type AiModelRefPayload } from '@/api/report'
import type { AiModelRef } from '@/contracts/aiModelRef'

const props = defineProps<{ simulationId: string }>()
const emit = defineEmits<{ done: [] }>()
const { t } = useI18n()

const open = ref(false)
const picked = ref<AiModelRef | null>(null)
const pending = ref(false)
const failure = ref<string | null>(null)
const canConfirm = computed(() => !!picked.value && !pending.value)

function onOpen(value: boolean): void {
  open.value = value
  if (value) {
    picked.value = null
    failure.value = null
  }
}

function describe(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  return String(err)
}

async function confirm(): Promise<void> {
  const ref_ = picked.value
  if (!ref_ || pending.value) return
  const payload: AiModelRefPayload = {
    provider_connection_id: ref_.provider_connection_id,
    model_id: ref_.model_id,
    source: ref_.source,
  }
  if (ref_.fallback_reason) payload.fallback_reason = ref_.fallback_reason
  pending.value = true
  failure.value = null
  try {
    const res = await generateReport({
      simulation_id: props.simulationId,
      force_regenerate: true,
      ai_model_ref: payload,
    })
    if (!res || res.success !== true) {
      const err = res as { error?: string; message?: string } | undefined
      failure.value = err?.error || err?.message || 'unknown'
      return
    }
    open.value = false
    emit('done')
  } catch (err) {
    failure.value = describe(err)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <DialogRoot :open="open" @update:open="onOpen">
    <DialogTrigger as-child>
      <button
        type="button"
        class="run-regen__trigger"
        :data-testid="`stage-regenerate-report`"
      >
        {{ t('views.run.overview.regenerate.button') }}
      </button>
    </DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="run-regen__overlay" />
      <DialogContent class="run-regen__content" data-testid="regenerate-dialog">
        <DialogTitle class="run-regen__title">{{ t('views.run.overview.regenerate.title') }}</DialogTitle>
        <DialogDescription class="run-regen__desc">
          {{ t('views.run.overview.regenerate.description') }}
        </DialogDescription>
        <p class="run-regen__label" id="run-regen-pick">{{ t('views.run.overview.regenerate.pickLabel') }}</p>
        <div aria-labelledby="run-regen-pick" role="group">
          <AiModelPicker
            v-model="picked"
            mode="chat"
            :placeholder="t('views.run.overview.regenerate.pickPlaceholder')"
          />
        </div>
        <p v-if="failure" class="run-regen__error" role="alert" data-testid="regenerate-error">
          {{ t('views.run.overview.regenerate.failed', { reason: failure }) }}
        </p>
        <div class="run-regen__actions">
          <DialogClose as-child>
            <button type="button" class="run-regen__btn" data-testid="regenerate-cancel">
              {{ t('views.run.overview.regenerate.cancel') }}
            </button>
          </DialogClose>
          <button
            type="button"
            class="run-regen__btn run-regen__btn--primary"
            :disabled="!canConfirm"
            data-testid="regenerate-confirm"
            @click="confirm"
          >
            {{ pending ? t('views.run.overview.regenerate.pending') : t('views.run.overview.regenerate.confirm') }}
          </button>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.run-regen__trigger,
.run-regen__btn {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.run-regen__trigger {
  margin-top: 6px;
}
.run-regen__btn--primary {
  background: var(--acc);
  border-color: var(--acc);
  color: var(--on-acc);
}
.run-regen__btn:disabled {
  color: var(--fg3);
  background: var(--s3);
  border-color: var(--line);
  cursor: not-allowed;
}
.run-regen__trigger:focus-visible,
.run-regen__btn:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.run-regen__overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 60;
}
.run-regen__content {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 61;
  width: min(480px, calc(100vw - 32px));
  padding: 20px;
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.run-regen__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.run-regen__desc {
  margin: 0;
  font-size: 13px;
  color: var(--fg2);
}
.run-regen__label {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--fg3);
}
.run-regen__error {
  margin: 0;
  font-size: 13px;
  color: var(--fg);
}
.run-regen__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
