<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import { useAuthStore } from '../../store/auth'
import {
  deleteWorkspaceProviderCredential,
  listWorkspaceProviderCredentials,
  saveWorkspaceProviderCredential,
} from '../../api/workspaceProviderCredentials'
import type {
  WorkspaceProviderCredentialStatus,
  WorkspaceSupportedProvider,
} from '../../contracts/workspaceProviderCredentialsContract'

const { t } = useI18n()
const auth = useAuthStore()
// Die BYOK-Anbieterliste kommt aus der Backend-Registry (#1688), nie aus
// einer Frontend-Konstante.
const providers = ref<WorkspaceSupportedProvider[]>([])

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
      providers.value = result.supported_providers
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
  providers.value = []
  input.value = {}
  busy.value = null
  loading.value = false
  message.value = ''
  if (auth.activeWorkspaceId) void load()
})
onMounted(() => { if (auth.activeWorkspaceId) void load() })
</script>

<template>
  <AppShell>
    <div class="workspace-keys">
      <h1>{{ t('auth.workspaceProviderKeys.title') }}</h1>
      <p>{{ t('auth.workspaceProviderKeys.description') }}</p>
      <p v-if="!canEdit" role="status">{{ t('auth.workspaceProviderKeys.readOnly') }}</p>
      <p v-if="loading" role="status">{{ t('common.loading') }}</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <p v-if="message" role="status">{{ message }}</p>

      <section v-for="provider in providers" :key="provider.provider_id" class="workspace-keys__provider">
        <h2>{{ provider.display_name }}</h2>
        <p>{{ t(status[provider.provider_id]?.configured ? 'auth.workspaceProviderKeys.configured' : 'auth.workspaceProviderKeys.missing') }}</p>
        <form v-if="canEdit" @submit.prevent="save(provider.provider_id)">
          <label :for="`workspace-key-${provider.provider_id}`">{{ t('auth.workspaceProviderKeys.keyLabel', { provider: provider.display_name }) }}</label>
          <input
            :id="`workspace-key-${provider.provider_id}`"
            v-model="input[provider.provider_id]"
            type="password"
            autocomplete="off"
            minlength="4"
            required
            :disabled="busy === provider.provider_id"
          />
          <button type="submit" :disabled="busy === provider.provider_id || !input[provider.provider_id]">
            {{ t('auth.workspaceProviderKeys.save') }}
          </button>
          <button
            v-if="status[provider.provider_id]?.configured"
            type="button"
            :disabled="busy === provider.provider_id"
            @click="remove(provider.provider_id)"
          >
            {{ t('auth.workspaceProviderKeys.delete') }}
          </button>
        </form>
      </section>
    </div>
  </AppShell>
</template>

<style scoped>
.workspace-keys { max-width: 44rem; margin: 0 auto; padding: 2rem; }
.workspace-keys__provider { border-top: 1px solid var(--hairline); padding: 1.5rem 0; }
.workspace-keys__provider form { display: grid; gap: 0.75rem; }
.workspace-keys__provider input { max-width: 30rem; padding: 0.65rem; }
.workspace-keys__provider button { justify-self: start; }
</style>
