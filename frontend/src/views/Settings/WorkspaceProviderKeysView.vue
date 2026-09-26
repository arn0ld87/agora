<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../../store/auth'
import {
  deleteWorkspaceProviderCredential,
  listWorkspaceProviderCredentials,
  saveWorkspaceProviderCredential,
} from '../../api/workspaceProviderCredentials'
import type { WorkspaceProviderCredentialStatus } from '../../contracts/workspaceProviderCredentialsContract'

const { t } = useI18n()
const auth = useAuthStore()
const providers = [
  { id: 'openai', label: 'OpenAI' },
  { id: 'google', label: 'Google Gemini' },
  { id: 'minimax', label: 'MiniMax' },
] as const

const status = ref<Record<string, WorkspaceProviderCredentialStatus>>({})
const input = ref<Record<string, string>>({})
const busy = ref<string | null>(null)
const loading = ref(false)
const message = ref('')
const error = ref('')
let generation = 0

const canEdit = computed(() => {
  const id = auth.activeWorkspaceId
  return !!id && ['owner', 'admin'].includes(auth.roles[id] ?? '')
})

async function load(): Promise<void> {
  const current = ++generation
  loading.value = true
  error.value = ''
  try {
    const result = await listWorkspaceProviderCredentials()
    if (current === generation) {
      status.value = Object.fromEntries(result.items.map((entry) => [entry.provider_id, entry]))
    }
  } catch {
    if (current === generation) error.value = t('auth.workspaceProviderKeys.loadError')
  } finally {
    if (current === generation) loading.value = false
  }
}

async function save(providerId: string): Promise<void> {
  const apiKey = input.value[providerId]?.trim()
  if (!apiKey || apiKey.length < 4 || !canEdit.value) return
  const current = generation
  busy.value = providerId
  error.value = ''
  message.value = ''
  try {
    const result = await saveWorkspaceProviderCredential(providerId, apiKey)
    if (current === generation) {
      status.value[providerId] = result
      input.value[providerId] = ''
      message.value = t('auth.workspaceProviderKeys.saved')
    }
  } catch {
    if (current === generation) error.value = t('auth.workspaceProviderKeys.saveError')
  } finally {
    if (current === generation) busy.value = null
  }
}

async function remove(providerId: string): Promise<void> {
  if (!canEdit.value) return
  const current = generation
  busy.value = providerId
  error.value = ''
  message.value = ''
  try {
    await deleteWorkspaceProviderCredential(providerId)
    if (current === generation) {
      delete status.value[providerId]
      input.value[providerId] = ''
      message.value = t('auth.workspaceProviderKeys.deleted')
    }
  } catch {
    if (current === generation) error.value = t('auth.workspaceProviderKeys.deleteError')
  } finally {
    if (current === generation) busy.value = null
  }
}

watch(() => auth.activeWorkspaceId, () => {
  ++generation
  status.value = {}
  input.value = {}
  busy.value = null
  loading.value = false
  message.value = ''
  if (auth.activeWorkspaceId) void load()
})
onMounted(() => { if (auth.activeWorkspaceId) void load() })
</script>

<template>
  <main class="workspace-keys">
    <h1>{{ t('auth.workspaceProviderKeys.title') }}</h1>
    <p>{{ t('auth.workspaceProviderKeys.description') }}</p>
    <p v-if="!canEdit" role="status">{{ t('auth.workspaceProviderKeys.readOnly') }}</p>
    <p v-if="loading" role="status">{{ t('common.loading') }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>

    <section v-for="provider in providers" :key="provider.id" class="workspace-keys__provider">
      <h2>{{ provider.label }}</h2>
      <p>{{ t(status[provider.id]?.configured ? 'auth.workspaceProviderKeys.configured' : 'auth.workspaceProviderKeys.missing') }}</p>
      <form v-if="canEdit" @submit.prevent="save(provider.id)">
        <label :for="`workspace-key-${provider.id}`">{{ t('auth.workspaceProviderKeys.keyLabel', { provider: provider.label }) }}</label>
        <input
          :id="`workspace-key-${provider.id}`"
          v-model="input[provider.id]"
          type="password"
          autocomplete="off"
          minlength="4"
          required
          :disabled="busy === provider.id"
        />
        <button type="submit" :disabled="busy === provider.id || !input[provider.id]">
          {{ t('auth.workspaceProviderKeys.save') }}
        </button>
        <button
          v-if="status[provider.id]?.configured"
          type="button"
          :disabled="busy === provider.id"
          @click="remove(provider.id)"
        >
          {{ t('auth.workspaceProviderKeys.delete') }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.workspace-keys { max-width: 44rem; margin: 0 auto; padding: 2rem; }
.workspace-keys__provider { border-top: 1px solid var(--hairline); padding: 1.5rem 0; }
.workspace-keys__provider form { display: grid; gap: 0.75rem; }
.workspace-keys__provider input { max-width: 30rem; padding: 0.65rem; }
.workspace-keys__provider button { justify-self: start; }
</style>
