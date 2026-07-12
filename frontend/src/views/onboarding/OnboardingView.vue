<script setup lang="ts">
/**
 * OnboardingView — resumierbarer Erst-Einrichtungs-Wizard (Onboarding Slice 2).
 *
 * `providers`/`chat_model`/`embeddings` sind bewusst ehrliche Statusschritte:
 * sie zeigen den realen `requirements`-Status und verlinken auf die
 * bestehenden Settings-Routen. Die geführte Einrichtung folgt in einem
 * späteren Update — hier gibt es keine Attrappen.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import Card from '@/components/v4/forms/Card.vue'
import Button from '@/components/v4/forms/Button.vue'
import ProfileForm from '@/components/v4/forms/ProfileForm.vue'
import { isApiError } from '@/api/envelope'
import { useUserProfileStore } from '@/store/userProfile'
import { ONBOARDING_STEP_ORDER } from '@/contracts/userProfileContract'
import type {
  OnboardingStepId,
  OperatingMode,
  UserProfileUpdateRequest,
} from '@/contracts/userProfileContract'

const { t } = useI18n()
const router = useRouter()
const store = useUserProfileStore()

const OPERATING_MODES: readonly OperatingMode[] = ['local', 'hybrid', 'server']

interface StatusStepConfig {
  step: OnboardingStepId
  titleKey: string
  descriptionKey: string
  futureNoticeKey: string
  settingsLinkKey: string
  settingsRouteName: string
  configured: () => boolean
  /**
   * Optionaler Hinweis-Key, der nur gerendert wird, wenn
   * ``legacyHintMatcher`` true zurueckgibt. Wird genutzt, um
   * im Onboarding fuer den Embedding-Step den Legacy-Pfad
   * (Config.EMBEDDING_*) explizit zu markieren, damit der
   * Operator weiss, dass die Konfiguration noch nicht aus dem
   * kanonischen EmbeddingConfigurationStore kommt.
   */
  legacyHintKey?: string
  legacyHintMatcher?: () => boolean
}

const viewStep = ref<OnboardingStepId>('welcome')
const selectedOperatingMode = ref<OperatingMode | null>(null)
const busy = ref(false)
const profileSaving = ref(false)
const stepError = ref<string | null>(null)
const completeMissing = ref<string[]>([])

const stepIndex = computed(() => ONBOARDING_STEP_ORDER.indexOf(viewStep.value))
const completedSteps = computed(() => store.onboarding.state?.completed_steps ?? [])
// Primärer Anzeigepfad: Blob-basierte Object-URL aus dem Store (siehe
// store/userProfile.ts::_refreshAvatarPreview) — funktioniert auch im
// token-geschützten Modus.
const avatarImageUrl = computed(() => store.avatarObjectUrl)

const statusSteps = computed<StatusStepConfig[]>(() => [
  {
    step: 'providers',
    titleKey: 'onboarding.providers.title',
    descriptionKey: 'onboarding.providers.description',
    futureNoticeKey: 'onboarding.providers.futureNotice',
    settingsLinkKey: 'onboarding.providers.settingsLink',
    settingsRouteName: 'SettingsLlmProviders',
    configured: () => store.onboarding.requirements?.chat_model_configured ?? false,
  },
  {
    step: 'chat_model',
    titleKey: 'onboarding.chatModel.title',
    descriptionKey: 'onboarding.chatModel.description',
    futureNoticeKey: 'onboarding.chatModel.futureNotice',
    settingsLinkKey: 'onboarding.chatModel.settingsLink',
    settingsRouteName: 'SettingsLlmProviders',
    configured: () => store.onboarding.requirements?.chat_model_configured ?? false,
  },
  {
    step: 'embeddings',
    titleKey: 'onboarding.embeddings.title',
    descriptionKey: 'onboarding.embeddings.description',
    futureNoticeKey: 'onboarding.embeddings.futureNotice',
    settingsLinkKey: 'onboarding.embeddings.settingsLink',
    // Onboarding Slice 4.3.3: embeddings hat eine eigene Settings-Route
    // (Slice 4.2 + 4.3.1 API), nicht mehr LlmProviders.
    settingsRouteName: 'SettingsEmbedding',
    configured: () => store.onboarding.requirements?.embedding_configured ?? false,
    legacyHintKey: 'onboarding.embeddings.legacyHint',
    legacyHintMatcher: () =>
      store.onboarding.requirements?.embedding_source === 'legacy',
  },
])

const activeStatusStep = computed(
  () => statusSteps.value.find((entry) => entry.step === viewStep.value) ?? null,
)

// Backend-Codes für `OnboardingRequirements`-Felder → i18n-Label, damit die
// 409-`missing`-Liste ("profile_valid", "chat_model_configured", …) lesbar
// statt als Rohcode dargestellt wird.
const MISSING_CODE_LABEL_KEYS: Record<string, string> = {
  profile_valid: 'onboarding.requirements.profileValid',
  chat_model_configured: 'onboarding.requirements.chatModelConfigured',
  embedding_configured: 'onboarding.requirements.embeddingConfigured',
}

function labelForMissingCode(code: string): string {
  const key = MISSING_CODE_LABEL_KEYS[code]
  return key ? t(key) : code
}

const requirementsMissing = computed<string[]>(() => {
  const req = store.onboarding.requirements
  if (!req) return []
  const missing: string[] = []
  if (!req.profile_valid) missing.push(t('onboarding.requirements.profileValid'))
  if (!req.chat_model_configured) missing.push(t('onboarding.requirements.chatModelConfigured'))
  if (!req.embedding_configured) missing.push(t('onboarding.requirements.embeddingConfigured'))
  return missing
})

function stepStatus(step: OnboardingStepId): 'done' | 'current' | 'open' {
  if (completedSteps.value.includes(step)) return 'done'
  if (step === viewStep.value) return 'current'
  return 'open'
}

function goBack(): void {
  if (stepIndex.value <= 0) return
  stepError.value = null
  viewStep.value = ONBOARDING_STEP_ORDER[stepIndex.value - 1]
}

function advanceAfterCompletion(): void {
  const next = store.onboarding.state?.current_step
  const fallbackIndex = Math.min(stepIndex.value + 1, ONBOARDING_STEP_ORDER.length - 1)
  viewStep.value = next ?? ONBOARDING_STEP_ORDER[fallbackIndex]
}

async function confirmWelcome(): Promise<void> {
  if (!selectedOperatingMode.value) return
  busy.value = true
  stepError.value = null
  try {
    await store.completeStep('welcome', selectedOperatingMode.value)
    advanceAfterCompletion()
  } catch {
    stepError.value = store.error ?? t('onboarding.errors.saveFailed')
  } finally {
    busy.value = false
  }
}

async function handleProfileSave(payload: UserProfileUpdateRequest): Promise<void> {
  profileSaving.value = true
  stepError.value = null
  try {
    await store.updateProfile(payload)
    await store.completeStep('profile')
    advanceAfterCompletion()
  } catch {
    stepError.value = store.error ?? t('onboarding.errors.saveFailed')
  } finally {
    profileSaving.value = false
  }
}

async function handleUploadAvatar(file: File): Promise<void> {
  stepError.value = null
  try {
    await store.uploadAvatar(file)
  } catch {
    stepError.value = store.error ?? t('profileSettings.form.avatarUploadError')
  }
}

async function handleDeleteAvatar(): Promise<void> {
  stepError.value = null
  try {
    await store.deleteAvatar()
  } catch {
    stepError.value = store.error ?? t('profileSettings.form.avatarDeleteError')
  }
}

async function confirmCurrentStatusStep(): Promise<void> {
  const step = viewStep.value
  busy.value = true
  stepError.value = null
  try {
    await store.completeStep(step)
    advanceAfterCompletion()
  } catch {
    stepError.value = store.error ?? t('onboarding.errors.saveFailed')
  } finally {
    busy.value = false
  }
}

async function handleComplete(): Promise<void> {
  busy.value = true
  stepError.value = null
  completeMissing.value = []
  try {
    await store.complete()
    void router.push({ name: 'Dashboard' })
  } catch (err) {
    if (isApiError(err) && err.code === 'onboarding_incomplete') {
      const rawMissing = err.details?.['missing']
      completeMissing.value = Array.isArray(rawMissing)
        ? rawMissing.map((code) => labelForMissingCode(String(code)))
        : requirementsMissing.value
      stepError.value = t('onboarding.errors.incomplete')
    } else {
      stepError.value = store.error ?? t('onboarding.errors.saveFailed')
    }
  } finally {
    busy.value = false
  }
}

async function handleDismiss(): Promise<void> {
  busy.value = true
  stepError.value = null
  try {
    await store.dismiss()
    void router.push({ name: 'Dashboard' })
  } catch {
    stepError.value = store.error ?? t('onboarding.errors.saveFailed')
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await store.ensureLoaded()
  viewStep.value = store.onboarding.state?.current_step ?? 'welcome'
  selectedOperatingMode.value = store.onboarding.state?.operating_mode ?? null
})
</script>

<template>
  <AppShell :breadcrumbs="[{ label: t('onboarding.wizard.title') }]">
    <PageHeader :title="t('onboarding.wizard.title')" />

    <ol class="onboarding-steps" aria-label="onboarding-steps">
      <li
        v-for="step in ONBOARDING_STEP_ORDER"
        :key="step"
        class="onboarding-steps__item"
        :class="`onboarding-steps__item--${stepStatus(step)}`"
      >
        <span class="onboarding-steps__dot" aria-hidden="true" />
        <span class="onboarding-steps__label">{{ t(`onboarding.steps.${step}`) }}</span>
        <span class="onboarding-steps__status">
          {{ t(`onboarding.wizard.stepStatus.${stepStatus(step)}`) }}
        </span>
      </li>
    </ol>

    <Card>
      <p v-if="stepError" class="onboarding-error" role="alert">{{ stepError }}</p>

      <!-- welcome -->
      <div v-if="viewStep === 'welcome'" class="onboarding-step">
        <h2 class="onboarding-step__title">{{ t('onboarding.welcome.title') }}</h2>
        <p class="onboarding-step__description">{{ t('onboarding.welcome.description') }}</p>

        <p class="onboarding-step__field-label">{{ t('onboarding.welcome.operatingModeLabel') }}</p>
        <div class="onboarding-mode-grid">
          <button
            v-for="mode in OPERATING_MODES"
            :key="mode"
            type="button"
            class="onboarding-mode-card v4-state-interactive"
            :class="{ 'onboarding-mode-card--active': selectedOperatingMode === mode }"
            @click="selectedOperatingMode = mode"
          >
            <span class="onboarding-mode-card__label">
              {{ t(`onboarding.welcome.operatingMode.${mode}.label`) }}
            </span>
            <span class="onboarding-mode-card__description">
              {{ t(`onboarding.welcome.operatingMode.${mode}.description`) }}
            </span>
          </button>
        </div>
      </div>

      <!-- profile -->
      <div v-else-if="viewStep === 'profile'" class="onboarding-step">
        <h2 class="onboarding-step__title">{{ t('onboarding.profile.title') }}</h2>
        <p class="onboarding-step__description">{{ t('onboarding.profile.description') }}</p>
        <ProfileForm
          :profile="store.profile"
          :avatar-url="avatarImageUrl"
          :saving="profileSaving"
          @save="handleProfileSave"
          @upload-avatar="handleUploadAvatar"
          @delete-avatar="handleDeleteAvatar"
        />
      </div>

      <!-- providers / chat_model / embeddings — ehrliche Statusschritte -->
      <div v-else-if="activeStatusStep" class="onboarding-step">
        <h2 class="onboarding-step__title">{{ t(activeStatusStep.titleKey) }}</h2>
        <p class="onboarding-step__description">{{ t(activeStatusStep.descriptionKey) }}</p>
        <p
          class="onboarding-status"
          :class="activeStatusStep.configured() ? 'onboarding-status--ok' : 'onboarding-status--pending'"
        >
          {{
            activeStatusStep.configured()
              ? t('onboarding.providers.configured')
              : t('onboarding.providers.notConfigured')
          }}
        </p>
        <p
          v-if="activeStatusStep.legacyHintKey && activeStatusStep.legacyHintMatcher?.()"
          class="onboarding-step__legacy-hint"
          role="note"
        >
          {{ t(activeStatusStep.legacyHintKey) }}
        </p>
        <p class="onboarding-step__notice">{{ t(activeStatusStep.futureNoticeKey) }}</p>
        <RouterLink :to="{ name: activeStatusStep.settingsRouteName }" class="onboarding-step__link">
          {{ t(activeStatusStep.settingsLinkKey) }}
        </RouterLink>
      </div>

      <!-- privacy -->
      <div v-else-if="viewStep === 'privacy'" class="onboarding-step">
        <h2 class="onboarding-step__title">{{ t('onboarding.privacy.title') }}</h2>
        <p class="onboarding-step__description">{{ t('onboarding.privacy.text') }}</p>
      </div>

      <!-- summary -->
      <div v-else-if="viewStep === 'summary'" class="onboarding-step">
        <h2 class="onboarding-step__title">{{ t('onboarding.summary.title') }}</h2>

        <div class="onboarding-summary-block">
          <h3>{{ t('onboarding.summary.profileHeading') }}</h3>
          <p>{{ store.profile?.display_name ?? '—' }}</p>
        </div>

        <div class="onboarding-summary-block">
          <h3>{{ t('onboarding.summary.modeHeading') }}</h3>
          <p>
            {{
              selectedOperatingMode
                ? t(`onboarding.welcome.operatingMode.${selectedOperatingMode}.label`)
                : '—'
            }}
          </p>
        </div>

        <div class="onboarding-summary-block">
          <h3>{{ t('onboarding.summary.requirementsHeading') }}</h3>
          <ul class="onboarding-requirements-list">
            <li>
              {{ t('onboarding.requirements.profileValid') }}:
              {{ store.onboarding.requirements?.profile_valid ? '✓' : '—' }}
            </li>
            <li>
              {{ t('onboarding.requirements.chatModelConfigured') }}:
              {{ store.onboarding.requirements?.chat_model_configured ? '✓' : '—' }}
            </li>
            <li>
              {{ t('onboarding.requirements.embeddingConfigured') }}:
              {{ store.onboarding.requirements?.embedding_configured ? '✓' : '—' }}
            </li>
          </ul>
        </div>

        <p v-if="completeMissing.length" class="onboarding-error" role="alert">
          {{ t('onboarding.summary.incompleteNotice') }} {{ completeMissing.join(', ') }}
        </p>
      </div>

      <div class="onboarding-footer">
        <Button variant="ghost" type="button" :disabled="busy" @click="handleDismiss">
          {{ t('onboarding.wizard.laterBtn') }}
        </Button>

        <div class="onboarding-footer__nav">
          <Button
            v-if="stepIndex > 0"
            variant="secondary"
            type="button"
            :disabled="busy"
            @click="goBack"
          >
            {{ t('onboarding.wizard.backBtn') }}
          </Button>

          <Button
            v-if="viewStep === 'welcome'"
            variant="primary"
            type="button"
            :disabled="busy || !selectedOperatingMode"
            :loading="busy"
            @click="confirmWelcome"
          >
            {{ t('onboarding.wizard.nextBtn') }}
          </Button>

          <Button
            v-else-if="activeStatusStep"
            variant="primary"
            type="button"
            :disabled="busy"
            :loading="busy"
            @click="confirmCurrentStatusStep"
          >
            {{ t('onboarding.wizard.nextBtn') }}
          </Button>

          <Button
            v-else-if="viewStep === 'privacy'"
            variant="primary"
            type="button"
            :disabled="busy"
            :loading="busy"
            @click="confirmCurrentStatusStep"
          >
            {{ t('onboarding.privacy.confirmBtn') }}
          </Button>

          <Button
            v-else-if="viewStep === 'summary'"
            variant="primary"
            type="button"
            :disabled="busy"
            :loading="busy"
            @click="handleComplete"
          >
            {{ t('onboarding.wizard.finishBtn') }}
          </Button>
        </div>
      </div>
    </Card>
  </AppShell>
</template>

<style scoped>
.onboarding-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  list-style: none;
  margin: 0 0 20px;
  padding: 0;
}

.onboarding-steps__item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--r-pill, 999px);
  border: 1px solid var(--hairline);
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-secondary);
}

.onboarding-steps__item--current {
  border-color: var(--accent);
  color: var(--accent);
}

.onboarding-steps__item--done {
  color: var(--status-green, #2e7d32);
}

.onboarding-steps__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.onboarding-steps__status {
  color: var(--text-tertiary);
}

.onboarding-step__title {
  margin: 0 0 6px;
  font-family: var(--font-sans);
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
}

.onboarding-step__description {
  margin: 0 0 16px;
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-secondary);
}

.onboarding-step__field-label {
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin: 0 0 8px;
}

.onboarding-mode-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

@media (max-width: 720px) {
  .onboarding-mode-grid {
    grid-template-columns: 1fr;
  }
}

.onboarding-mode-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
  text-align: left;
  padding: 12px 14px;
  border-radius: var(--r-4, 8px);
  --v4-state-rest-bg: var(--surface-elevated, #fff);
  --v4-state-hover-bg: var(--surface-elevated, #fff);
}

.onboarding-mode-card--active {
  border-color: var(--accent);
  background: var(--accent-subtle, #f0f5ff);
}

.onboarding-mode-card__label {
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.onboarding-mode-card__description {
  font-family: var(--font-sans);
  font-size: 12.5px;
  color: var(--text-secondary);
}

.onboarding-status {
  display: inline-flex;
  width: fit-content;
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 500;
  padding: 3px 10px;
  border-radius: var(--r-pill, 999px);
  margin: 0 0 10px;
}

.onboarding-status--ok {
  background: var(--status-green-bg);
  color: var(--status-green);
}

.onboarding-status--pending {
  background: var(--status-orange-bg);
  color: var(--status-orange);
}

.onboarding-step__notice {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 10px;
}

.onboarding-step__link {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--accent);
}

.onboarding-step__legacy-hint {
  font-family: var(--font-sans);
  font-size: 12.5px;
  color: var(--text-secondary);
  background: var(--status-orange-bg, #fff4e5);
  border: 1px solid var(--status-orange, #c47b1c);
  border-radius: var(--r-4, 8px);
  padding: 8px 10px;
  margin: 0 0 10px;
}

.onboarding-summary-block {
  margin-bottom: 14px;
}

.onboarding-summary-block h3 {
  margin: 0 0 4px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.onboarding-summary-block p {
  margin: 0;
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-primary);
}

.onboarding-requirements-list {
  margin: 0;
  padding-left: 18px;
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text-primary);
}

.onboarding-error {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--status-red, #c0392b);
  padding: 8px 12px;
  border: 1px solid var(--status-red, #c0392b);
  border-radius: var(--r-4, 8px);
  margin: 0 0 14px;
}

.onboarding-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--separator, var(--hairline));
}

.onboarding-footer__nav {
  display: flex;
  gap: 10px;
}
</style>
