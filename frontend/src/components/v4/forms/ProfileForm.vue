<script setup lang="ts">
/**
 * ProfileForm — wiederverwendbares Profil-Formular (Onboarding Slice 2).
 *
 * Reines Props/Emits-Component ohne eigenes Fetching — sowohl
 * `OnboardingView` (Schritt "profile") als auch `SettingsProfileView`
 * binden es ein und übernehmen Store-Zugriff + Persistenz selbst.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Field from './Field.vue'
import Input from './Input.vue'
import Select from './Select.vue'
import Button from './Button.vue'
import {
  ALLOWED_AVATAR_MIME_TYPES,
  MAX_AVATAR_BYTES,
  TIMEZONE_SUGGESTIONS,
} from './profileFormConstants'
import type { UserProfile, UserProfileUpdateRequest } from '@/contracts/userProfileContract'

const { t } = useI18n()

const props = withDefaults(
  defineProps<{
    profile: UserProfile | null
    avatarUrl?: string | null
    saving?: boolean
  }>(),
  {
    avatarUrl: null,
    saving: false,
  },
)

const emit = defineEmits<{
  save: [payload: UserProfileUpdateRequest]
  'upload-avatar': [file: File]
  'delete-avatar': []
}>()

// ---------------------------------------------------------------------------
// Form-State (lokal, aus `profile`-Prop synchronisiert)
// ---------------------------------------------------------------------------
const displayName = ref('')
const username = ref('')
const role = ref('')
const organisation = ref('')
const language = ref('de')
const timezone = ref('Europe/Berlin')
const reportLanguage = ref('de')
const theme = ref('system')
const privacyMode = ref('standard')

function syncFromProfile(profile: UserProfile | null): void {
  displayName.value = profile?.display_name ?? ''
  username.value = profile?.username ?? ''
  role.value = profile?.role ?? ''
  organisation.value = profile?.organisation ?? ''
  language.value = profile?.language ?? 'de'
  timezone.value = profile?.timezone ?? 'Europe/Berlin'
  reportLanguage.value = profile?.report_language ?? 'de'
  theme.value = profile?.theme ?? 'system'
  privacyMode.value = profile?.privacy_mode ?? 'standard'
}
watch(() => props.profile, syncFromProfile, { immediate: true })

// ---------------------------------------------------------------------------
// Optionen für Select-Felder
// ---------------------------------------------------------------------------
const languageOptions = computed(() => [
  { value: 'de', label: t('profileSettings.form.language.de') },
  { value: 'en', label: t('profileSettings.form.language.en') },
])
const themeOptions = computed(() => [
  { value: 'system', label: t('profileSettings.form.theme.system') },
  { value: 'light', label: t('profileSettings.form.theme.light') },
  { value: 'dark', label: t('profileSettings.form.theme.dark') },
])
const privacyModeOptions = computed(() => [
  { value: 'standard', label: t('profileSettings.form.privacyMode.standard') },
  { value: 'strict', label: t('profileSettings.form.privacyMode.strict') },
])

// ---------------------------------------------------------------------------
// Validierung + Submit
// ---------------------------------------------------------------------------
const displayNameTouched = ref(false)
const displayNameInvalid = computed(() => displayName.value.trim().length === 0)
const canSave = computed(() => !displayNameInvalid.value && !props.saving)

function handleSubmit(): void {
  displayNameTouched.value = true
  if (!canSave.value) return
  const payload: UserProfileUpdateRequest = {
    display_name: displayName.value.trim(),
    username: username.value.trim() || null,
    role: role.value.trim() || null,
    organisation: organisation.value.trim() || null,
    language: language.value as UserProfileUpdateRequest['language'],
    timezone: timezone.value.trim() || null,
    report_language: reportLanguage.value as UserProfileUpdateRequest['report_language'],
    theme: theme.value as UserProfileUpdateRequest['theme'],
    privacy_mode: privacyMode.value as UserProfileUpdateRequest['privacy_mode'],
  }
  emit('save', payload)
}

// ---------------------------------------------------------------------------
// Avatar — Client-Vorprüfung (Größe + Typ) vor Emit
// ---------------------------------------------------------------------------
const avatarError = ref<string | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

function triggerFileInput(): void {
  fileInputRef.value?.click()
}

function onAvatarFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  // Reset, damit dieselbe Datei erneut ausgewählt werden kann.
  input.value = ''
  if (!file) return

  avatarError.value = null
  if (!ALLOWED_AVATAR_MIME_TYPES.has(file.type)) {
    avatarError.value = t('profileSettings.form.avatarUnsupportedType')
    return
  }
  if (file.size > MAX_AVATAR_BYTES) {
    avatarError.value = t('profileSettings.form.avatarTooLarge')
    return
  }
  emit('upload-avatar', file)
}

function handleDeleteAvatar(): void {
  emit('delete-avatar')
}

// ---------------------------------------------------------------------------
// Initialen-Fallback
// ---------------------------------------------------------------------------
const initials = computed(() => {
  const name = displayName.value.trim()
  if (!name) return '?'
  const parts = name.split(/\s+/).filter(Boolean)
  const first = parts[0]?.charAt(0) ?? ''
  const last = parts.length > 1 ? parts[parts.length - 1].charAt(0) : ''
  return (first + last).toUpperCase()
})

defineExpose({ canSave, handleSubmit })
</script>

<template>
  <div class="profile-form">
    <div class="profile-form__avatar-row">
      <div class="profile-form__avatar">
        <img
          v-if="avatarUrl"
          :src="avatarUrl"
          :alt="displayName"
          class="profile-form__avatar-img"
        />
        <span v-else class="profile-form__avatar-initials" aria-hidden="true">{{ initials }}</span>
      </div>
      <div class="profile-form__avatar-actions">
        <Button
          variant="secondary"
          size="sm"
          type="button"
          :disabled="saving"
          @click="triggerFileInput"
        >
          {{ t('profileSettings.form.avatarUploadBtn') }}
        </Button>
        <Button
          v-if="avatarUrl"
          variant="ghost"
          size="sm"
          type="button"
          :disabled="saving"
          @click="handleDeleteAvatar"
        >
          {{ t('profileSettings.form.avatarDeleteBtn') }}
        </Button>
        <input
          ref="fileInputRef"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          :aria-label="t('profileSettings.form.avatarUploadBtn')"
          class="profile-form__avatar-input"
          data-testid="avatar-file-input"
          @change="onAvatarFileChange"
        />
      </div>
    </div>
    <p v-if="avatarError" class="profile-form__error" role="alert">{{ avatarError }}</p>

    <div class="profile-form__fields">
      <Field :label="t('profileSettings.form.displayNameLabel')">
        <Input
          v-model="displayName"
          :disabled="saving"
          data-testid="profile-form-display-name"
          @blur="displayNameTouched = true"
        />
        <span v-if="displayNameTouched && displayNameInvalid" class="profile-form__error">
          {{ t('profileSettings.form.displayNameRequired') }}
        </span>
      </Field>

      <Field :label="t('profileSettings.form.usernameLabel')">
        <Input v-model="username" :disabled="saving" />
      </Field>

      <Field :label="t('profileSettings.form.roleLabel')">
        <Input v-model="role" :disabled="saving" />
      </Field>

      <Field :label="t('profileSettings.form.organisationLabel')">
        <Input v-model="organisation" :disabled="saving" />
      </Field>

      <Field :label="t('profileSettings.form.languageLabel')">
        <Select v-model="language" :options="languageOptions" :disabled="saving" />
      </Field>

      <Field :label="t('profileSettings.form.timezoneLabel')">
        <input
          v-model="timezone"
          list="profile-form-timezones"
          class="v4-input v4-state-interactive"
          :disabled="saving"
        />
        <datalist id="profile-form-timezones">
          <option v-for="tz in TIMEZONE_SUGGESTIONS" :key="tz" :value="tz" />
        </datalist>
      </Field>

      <Field :label="t('profileSettings.form.reportLanguageLabel')">
        <Select v-model="reportLanguage" :options="languageOptions" :disabled="saving" />
      </Field>

      <Field :label="t('profileSettings.form.themeLabel')">
        <Select v-model="theme" :options="themeOptions" :disabled="saving" />
      </Field>

      <Field :label="t('profileSettings.form.privacyModeLabel')">
        <Select v-model="privacyMode" :options="privacyModeOptions" :disabled="saving" />
      </Field>
    </div>

    <div class="profile-form__footer">
      <Button
        variant="primary"
        type="button"
        :disabled="!canSave"
        :loading="saving"
        @click="handleSubmit"
      >
        {{ t('profileSettings.saveBtn') }}
      </Button>
    </div>
  </div>
</template>

<style scoped>
.profile-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.profile-form__avatar-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.profile-form__avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-inset, #f2f2f7);
  border: 1px solid var(--hairline);
  flex-shrink: 0;
}

.profile-form__avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.profile-form__avatar-initials {
  font-family: var(--font-sans);
  font-size: 20px;
  font-weight: 600;
  color: var(--text-secondary);
}

.profile-form__avatar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.profile-form__avatar-input {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.profile-form__fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 640px) {
  .profile-form__fields {
    grid-template-columns: 1fr;
  }
}

.profile-form__error {
  font-family: var(--font-sans);
  font-size: 12.5px;
  color: var(--status-red, #c0392b);
}

.profile-form__footer {
  display: flex;
  justify-content: flex-end;
}
</style>
