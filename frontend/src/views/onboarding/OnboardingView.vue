<script setup lang="ts">
/**
 * OnboardingView — resumierbarer Erst-Einrichtungs-Wizard (Onboarding Slice 2
 * + Phase-2-Verfeinerung frontend-next).
 *
 * `providers`/`chat_model`/`embeddings` sind bewusst ehrliche Statusschritte:
 * sie zeigen den realen Konfigurations-Status und verlinken auf die
 * bestehenden Settings-Routen. Die geführte Einrichtung folgt in einem
 * späteren Update — hier gibt es keine Attrappen.
 *
 * Phase 2 Granularität (§3.2.1): `providers` wertet den Connection-Store
 * aus (mindestens eine ProviderConnection existiert), nicht das
 * `chat_model_configured`-Flag. `chat_model` und `embeddings` bleiben am
 * Backend-Requirements-Flag. Damit sind `providers` und `chat_model`
 * nicht mehr redundant und der Status entspricht der echten Konfiguration.
 *
 * Phase 2 Skip-Button (§3.2.4): Auf Statusschritten wird der "Weiter"-
 * Button ausgeblendet, solange der jeweilige Step nicht `configured()` ist.
 * Sonst markiert ein voreilig geklickter "Weiter"-Button den Step als
 * completed, obwohl keine Einrichtung stattgefunden hat. Der "Später
 * einrichten"-Footer bleibt sichtbar als ehrlicher Ausweg.
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import Card from '@/components/v4/forms/Card.vue'
import Button from '@/components/v4/forms/Button.vue'
import ProfileForm from '@/components/v4/forms/ProfileForm.vue'
import { isApiError } from '@/api/envelope'
import { useUserProfileStore } from '@/store/userProfile'
import { useLlmProvidersStore } from '@/store/aiModels'
import { ONBOARDING_STEP_ORDER } from '@/contracts/userProfileContract'
import type {
  OnboardingStepId,
  OperatingMode,
  UserProfileUpdateRequest,
} from '@/contracts/userProfileContract'

const { t } = useI18n()
const router = useRouter()
const store = useUserProfileStore()
const providersStore = useLlmProvidersStore()

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
const stepTitle = ref<HTMLElement | null>(null)

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
    // Phase 2 §3.2.1: providers zeigt Connection-Store-Status (mindestens
    // eine ProviderConnection existiert), nicht das redundante
    // `chat_model_configured`-Flag. Voraussetzung: onMounted ruft
    // `providersStore.loadConnections()` (fail-open per .catch).
    configured: () => Object.keys(providersStore.connections).length > 0,
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

watch(viewStep, async () => {
  await nextTick()
  stepTitle.value?.focus()
})

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
  // Phase 2 §3.2.1: `providers.configured()` braucht den Connection-Store.
  // Parallel zu `ensureLoaded()` laden, fail-open per `.catch` (bei
  // Provider-Endpoint-Fehler bleibt `connections = {}` und der providers-
  // Step zeigt ehrlich "pending" — der User klickt sich dann zu den
  // Settings und sieht dort den realen Stand).
  await Promise.all([
    store.ensureLoaded(),
    providersStore.loadConnections().catch(() => undefined),
  ])
  viewStep.value = store.onboarding.state?.current_step ?? 'welcome'
  selectedOperatingMode.value = store.onboarding.state?.operating_mode ?? null
})
</script>

<template>
  <AppShell :breadcrumbs="[{ label: t('onboarding.wizard.title') }]">
    <PageHeader :title="t('onboarding.wizard.title')" />

    <ol class="onboarding-steps" :aria-label="t('onboarding.wizard.progressLabel')">
      <li
        v-for="step in ONBOARDING_STEP_ORDER"
        :key="step"
        class="onboarding-steps__item"
        :class="`onboarding-steps__item--${stepStatus(step)}`"
        :aria-current="step === viewStep ? 'step' : undefined"
      >
        <span class="onboarding-steps__dot" aria-hidden="true" />
        <span class="onboarding-steps__label">{{ t(`onboarding.steps.${step}`) }}</span>
        <span class="onboarding-steps__status">
          {{ t(`onboarding.wizard.stepStatus.${stepStatus(step)}`) }}
        </span>
      </li>
    </ol>

    <Card>
      <section class="onboarding-surface" aria-labelledby="onboarding-step-title">
      <p v-if="stepError" class="onboarding-error" role="alert">{{ stepError }}</p>

      <!-- welcome -->
      <div v-if="viewStep === 'welcome'" class="onboarding-step">
        <h2 id="onboarding-step-title" ref="stepTitle" class="onboarding-step__title" tabindex="-1">
          {{ t('onboarding.welcome.title') }}
        </h2>
        <p class="onboarding-step__description">{{ t('onboarding.welcome.description') }}</p>

        <p class="onboarding-step__field-label">{{ t('onboarding.welcome.operatingModeLabel') }}</p>
        <div class="onboarding-mode-grid">
          <button
            v-for="mode in OPERATING_MODES"
            :key="mode"
            type="button"
            class="onboarding-mode-card v4-state-interactive"
            :class="{ 'onboarding-mode-card--active': selectedOperatingMode === mode }"
            :aria-pressed="selectedOperatingMode === mode"
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
        <h2 id="onboarding-step-title" ref="stepTitle" class="onboarding-step__title" tabindex="-1">
          {{ t('onboarding.profile.title') }}
        </h2>
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
        <h2 id="onboarding-step-title" ref="stepTitle" class="onboarding-step__title" tabindex="-1">
          {{ t(activeStatusStep.titleKey) }}
        </h2>
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
        <h2 id="onboarding-step-title" ref="stepTitle" class="onboarding-step__title" tabindex="-1">
          {{ t('onboarding.privacy.title') }}
        </h2>
        <p class="onboarding-step__description">{{ t('onboarding.privacy.text') }}</p>
      </div>

      <!-- summary -->
      <div v-else-if="viewStep === 'summary'" class="onboarding-step">
        <h2 id="onboarding-step-title" ref="stepTitle" class="onboarding-step__title" tabindex="-1">
          {{ t('onboarding.summary.title') }}
        </h2>

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
            v-else-if="activeStatusStep && activeStatusStep.configured()"
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
      </section>
    </Card>
  </AppShell>
</template>

<style scoped>
.onboarding-steps {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: var(--sp-2);
  list-style: none;
  margin: 0 0 var(--sp-6);
  padding: 0;
}

.onboarding-steps__item {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-4);
  border: 1px solid var(--hairline);
  background: var(--surface-glass);
  font-family: var(--font-sans);
  font-size: var(--fs-caption-1);
  line-height: var(--lh-caption-1);
  color: var(--text-secondary);
}

.onboarding-steps__item--current {
  border-color: var(--accent-warm);
  background: var(--surface-glass-strong);
  box-shadow: var(--shadow-glass);
  color: var(--accent-ink);
}

.onboarding-steps__item--done {
  color: var(--status-success);
}

.onboarding-steps__dot {
  flex: 0 0 var(--sp-2);
  width: var(--sp-2);
  height: var(--sp-2);
  border-radius: var(--r-pill);
  background: currentColor;
}

.onboarding-steps__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.onboarding-steps__status {
  margin-left: auto;
  color: var(--text-tertiary);
}

.onboarding-surface {
  min-width: 0;
}

.onboarding-step__title {
  width: fit-content;
  margin: 0 0 var(--sp-2);
  border-radius: var(--r-2);
  font-family: var(--font-sans);
  font-size: var(--fs-title-2);
  line-height: var(--lh-title-2);
  font-weight: 600;
  color: var(--text-primary);
  transition: box-shadow var(--v4-state-motion-duration-base) var(--v4-state-motion-ease);
}

.onboarding-step__title:focus {
  outline: none;
  box-shadow: var(--focus-ring-strong);
}

.onboarding-step__description {
  max-width: 68ch;
  margin: 0 0 var(--sp-5);
  font-family: var(--font-sans);
  font-size: var(--fs-body);
  line-height: var(--lh-body);
  color: var(--text-secondary);
}

.onboarding-step__field-label {
  margin: 0 0 var(--sp-3);
  font-family: var(--font-sans);
  font-size: var(--fs-subhead);
  line-height: var(--lh-subhead);
  font-weight: 500;
  color: var(--text-secondary);
}

.onboarding-mode-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-3);
}

.onboarding-mode-card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  align-items: flex-start;
  text-align: left;
  min-width: 0;
  padding: var(--sp-5);
  border-radius: var(--r-5);
  border: 1px solid var(--hairline);
  box-shadow: var(--shadow-hairline);
  --v4-state-rest-bg: var(--surface-glass);
  --v4-state-hover-bg: var(--surface-glass-strong);
  transition:
    border-color var(--v4-state-motion-duration-base) var(--v4-state-motion-ease),
    box-shadow var(--v4-state-motion-duration-base) var(--v4-state-motion-ease),
    transform var(--v4-state-motion-duration-base) var(--v4-state-motion-ease);
}

.onboarding-mode-card:hover {
  transform: translateY(calc(var(--sp-1) * -1));
  box-shadow: var(--shadow-glass);
}

.onboarding-mode-card--active {
  border-color: var(--accent-warm);
  box-shadow: var(--shadow-glass), inset var(--sp-1) 0 0 var(--accent-warm);
  --v4-state-rest-bg: var(--accent-tint-bg);
}

.onboarding-mode-card__label {
  font-family: var(--font-sans);
  font-size: var(--fs-headline);
  line-height: var(--lh-headline);
  font-weight: 600;
  color: var(--text-primary);
}

.onboarding-mode-card__description {
  font-family: var(--font-sans);
  font-size: var(--fs-footnote);
  line-height: var(--lh-footnote);
  color: var(--text-secondary);
}

.onboarding-status {
  display: inline-flex;
  width: fit-content;
  margin: 0 0 var(--sp-3);
  padding: var(--sp-2) var(--sp-4);
  border-radius: var(--r-pill);
  font-family: var(--font-sans);
  font-size: var(--fs-footnote);
  line-height: var(--lh-footnote);
  font-weight: 500;
}

.onboarding-status--ok {
  background: var(--status-success-soft);
  color: var(--status-success);
}

.onboarding-status--pending {
  background: var(--status-coral-bg);
  color: var(--status-coral);
}

.onboarding-step__notice {
  max-width: 68ch;
  margin: 0 0 var(--sp-3);
  font-family: var(--font-sans);
  font-size: var(--fs-subhead);
  line-height: var(--lh-subhead);
  color: var(--text-secondary);
}

.onboarding-step__link {
  display: inline-flex;
  border-radius: var(--r-2);
  font-family: var(--font-sans);
  font-size: var(--fs-subhead);
  line-height: var(--lh-subhead);
  color: var(--accent);
  text-underline-offset: var(--sp-1);
}

.onboarding-step__legacy-hint {
  max-width: 68ch;
  margin: 0 0 var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  border: 1px solid var(--status-coral);
  border-radius: var(--r-4);
  font-family: var(--font-sans);
  font-size: var(--fs-footnote);
  line-height: var(--lh-footnote);
  color: var(--text-secondary);
  background: var(--status-coral-bg);
}

.onboarding-summary-block {
  margin-bottom: var(--sp-3);
  padding: var(--sp-4);
  border: 1px solid var(--hairline);
  border-radius: var(--r-4);
  background: var(--surface-glass);
}

.onboarding-summary-block h3 {
  margin: 0 0 var(--sp-1);
  font-family: var(--font-sans);
  font-size: var(--fs-subhead);
  line-height: var(--lh-subhead);
  font-weight: 600;
  color: var(--text-secondary);
}

.onboarding-summary-block p {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--fs-body);
  line-height: var(--lh-body);
  color: var(--text-primary);
}

.onboarding-requirements-list {
  margin: 0;
  padding-left: var(--sp-5);
  font-family: var(--font-sans);
  font-size: var(--fs-body);
  line-height: var(--lh-body);
  color: var(--text-primary);
}

.onboarding-error {
  margin: 0 0 var(--sp-4);
  padding: var(--sp-3) var(--sp-4);
  border: 1px solid var(--status-error);
  border-radius: var(--r-4);
  font-family: var(--font-sans);
  font-size: var(--fs-subhead);
  line-height: var(--lh-subhead);
  color: var(--status-error);
  background: var(--status-error-soft);
}

.onboarding-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  margin-top: var(--sp-7);
  padding-top: var(--sp-5);
  border-top: 1px solid var(--separator);
}

.onboarding-footer__nav {
  display: flex;
  gap: var(--sp-3);
}

@media (max-width: 48rem) {
  .onboarding-steps {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .onboarding-mode-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 30rem) {
  .onboarding-steps {
    grid-template-columns: 1fr;
  }

  .onboarding-footer,
  .onboarding-footer__nav {
    align-items: stretch;
    flex-direction: column;
  }
}

@media (prefers-reduced-motion: reduce) {
  .onboarding-step__title,
  .onboarding-mode-card {
    transition: none;
  }

  .onboarding-mode-card:hover {
    transform: none;
  }
}
</style>
