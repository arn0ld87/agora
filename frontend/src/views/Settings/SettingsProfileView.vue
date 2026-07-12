<script setup lang="ts">
/**
 * SettingsProfileView — Profil-Einstellungen (Onboarding Slice 2).
 *
 * Bettet `ProfileForm` ein, persistiert über `useUserProfileStore` und
 * bietet einen Wiedereinstieg in den Onboarding-Wizard ("Onboarding erneut
 * öffnen"). Ersetzt den "Users & Teams"-Sidebar-Eintrag (IA-Fix).
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import Card from '@/components/v4/forms/Card.vue'
import Button from '@/components/v4/forms/Button.vue'
import ProfileForm from '@/components/v4/forms/ProfileForm.vue'
import { useUserProfileStore } from '@/store/userProfile'
import type { UserProfileUpdateRequest } from '@/contracts/userProfileContract'

const { t } = useI18n()
const router = useRouter()
const store = useUserProfileStore()

const saving = ref(false)
const saveError = ref<string | null>(null)
const saveSuccess = ref(false)

const breadcrumbs = computed(() => [
  { label: t('nav.SettingsGeneral'), to: { name: 'SettingsGeneral' } },
  { label: t('profileSettings.title') },
])

// Primärer Anzeigepfad: Blob-basierte Object-URL aus dem Store (funktioniert
// auch im token-geschützten Modus, da der Fetch über den authentifizierten
// service-Client läuft). Fällt bei Fehlern auf den Initialen-Fallback in
// ProfileForm zurück.
const avatarImageUrl = computed(() => store.avatarObjectUrl)

async function handleSave(payload: UserProfileUpdateRequest): Promise<void> {
  saving.value = true
  saveError.value = null
  saveSuccess.value = false
  try {
    await store.updateProfile(payload)
    saveSuccess.value = true
  } catch {
    saveError.value = store.error ?? t('profileSettings.saveError')
  } finally {
    saving.value = false
  }
}

async function handleUploadAvatar(file: File): Promise<void> {
  saveError.value = null
  try {
    await store.uploadAvatar(file)
  } catch {
    saveError.value = store.error ?? t('profileSettings.form.avatarUploadError')
  }
}

async function handleDeleteAvatar(): Promise<void> {
  saveError.value = null
  try {
    await store.deleteAvatar()
  } catch {
    saveError.value = store.error ?? t('profileSettings.form.avatarDeleteError')
  }
}

async function handleReopenOnboarding(): Promise<void> {
  try {
    await store.reopen()
  } finally {
    void router.push({ name: 'Onboarding' })
  }
}

onMounted(() => {
  void store.ensureLoaded()
})
</script>

<template>
  <AppShell :breadcrumbs="breadcrumbs">
    <PageHeader :title="t('profileSettings.title')" :subtitle="t('profileSettings.subtitle')">
      <template #right>
        <Button variant="secondary" size="sm" type="button" @click="handleReopenOnboarding">
          {{ t('profileSettings.reopenOnboardingBtn') }}
        </Button>
      </template>
    </PageHeader>

    <Card>
      <p
        v-if="saveError"
        class="settings-profile__banner settings-profile__banner--error"
        role="alert"
      >
        {{ saveError }}
      </p>
      <p v-if="saveSuccess" class="settings-profile__banner settings-profile__banner--success">
        {{ t('profileSettings.saveSuccess') }}
      </p>

      <ProfileForm
        :profile="store.profile"
        :avatar-url="avatarImageUrl"
        :saving="saving"
        @save="handleSave"
        @upload-avatar="handleUploadAvatar"
        @delete-avatar="handleDeleteAvatar"
      />
    </Card>
  </AppShell>
</template>

<style scoped>
.settings-profile__banner {
  font-family: var(--font-sans);
  font-size: 13px;
  padding: 8px 12px;
  border-radius: var(--r-4, 8px);
  margin-bottom: 16px;
}

.settings-profile__banner--error {
  color: var(--status-red, #c0392b);
  border: 1px solid var(--status-red, #c0392b);
}

.settings-profile__banner--success {
  color: var(--status-green, #2e7d32);
  border: 1px solid var(--status-green, #2e7d32);
}
</style>
