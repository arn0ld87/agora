<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import Card from '@/components/v4/forms/Card.vue'
import Badge from '@/components/v4/forms/Badge.vue'
import Input from '@/components/v4/forms/Input.vue'
import { useApiKeysStore } from '@/store/apiKeys'
import type { ApiKeyModel, ApiKeyScope } from '@/contracts/apiKeysContract'

const { t, locale } = useI18n()
const store = useApiKeysStore()

const BREADCRUMBS = [
  { label: 'Settings', to: { name: 'SettingsGeneral' } },
  { label: 'API Keys' },
]

// --- Create-Modal-State ---
const createModalOpen = ref(false)
const createLabel = ref('')
const createScopes = ref<ApiKeyScope[]>(['read'])
const createError = ref<string | null>(null)

function openCreateModal(): void {
  createLabel.value = ''
  createScopes.value = ['read']
  createError.value = null
  createModalOpen.value = true
}

function closeCreateModal(): void {
  createModalOpen.value = false
  store.clearLastCreatedToken()
}

function toggleScope(scope: ApiKeyScope): void {
  const idx = createScopes.value.indexOf(scope)
  if (idx === -1) {
    createScopes.value = [...createScopes.value, scope]
  } else {
    createScopes.value = createScopes.value.filter((s) => s !== scope)
  }
}

async function submitCreate(): Promise<void> {
  createError.value = null
  if (!createLabel.value.trim()) {
    createError.value = t('settings.v4.apiKeys.create.labelField') + ' ' + t('common.required', 'ist erforderlich.')
    return
  }
  if (createScopes.value.length === 0) {
    createError.value = t('settings.v4.apiKeys.create.scopesField') + ' ' + t('common.required', 'ist erforderlich.')
    return
  }
  try {
    await store.create(createLabel.value.trim(), createScopes.value)
  } catch {
    createError.value = t('settings.v4.apiKeys.errors.createFailed')
  }
}

// --- Copy-to-Clipboard ---
const tokenCopied = ref(false)

const copyError = ref<string | null>(null)

async function copyToken(): Promise<void> {
  if (!store.lastCreatedToken) return
  copyError.value = null
  try {
    await navigator.clipboard.writeText(store.lastCreatedToken)
    tokenCopied.value = true
    setTimeout(() => { tokenCopied.value = false }, 2000)
  } catch {
    copyError.value = t('settings.v4.apiKeys.errors.copyFailed')
  }
}

// --- Revoke-Dialog-State ---
const revokeTarget = ref<ApiKeyModel | null>(null)
const revokeError = ref<string | null>(null)

function openRevokeDialog(key: ApiKeyModel): void {
  revokeTarget.value = key
  revokeError.value = null
}

function closeRevokeDialog(): void {
  revokeTarget.value = null
  revokeError.value = null
}

async function confirmRevoke(): Promise<void> {
  if (!revokeTarget.value) return
  revokeError.value = null
  try {
    await store.revoke(revokeTarget.value.id)
    closeRevokeDialog()
  } catch {
    revokeError.value = t('settings.v4.apiKeys.errors.revokeFailed')
  }
}

// --- Helpers ---
function formatDate(iso: string | null | undefined): string {
  if (!iso) return t('settings.v4.apiKeys.table.never')
  return new Date(iso).toLocaleDateString(locale.value, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

function statusTone(status: ApiKeyModel['status']): 'green' | 'gray' {
  return status === 'active' ? 'green' : 'gray'
}

const SCOPES: ApiKeyScope[] = ['read', 'write', 'admin']

onMounted(() => {
  store.list().catch(() => { /* error set on store.error */ })
})
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      :title="t('settings.v4.apiKeys.title')"
      :subtitle="t('settings.v4.apiKeys.subtitle')"
    />

    <!-- Fehler-Banner beim Laden -->
    <div v-if="store.error && !store.loading" class="api-keys__error-banner" role="alert">
      {{ store.error }}
    </div>

    <!-- Karte 1: Schlüssel anlegen -->
    <Card :title="t('settings.v4.apiKeys.actions.create')">
      <template #right>
        <button class="v4-btn v4-btn--primary" @click="openCreateModal">
          {{ t('settings.v4.apiKeys.actions.create') }}
        </button>
      </template>
      <p class="api-keys__hint">
        {{ t('settings.v4.apiKeys.empty.description') }}
      </p>
    </Card>

    <!-- Karte 2: Schlüssel-Liste -->
    <Card
      :title="t('settings.v4.apiKeys.title')"
      style="margin-top: 16px;"
    >
      <div v-if="store.loading" class="api-keys__loading">
        {{ t('common.loading') }}
      </div>

      <div v-else-if="store.items.length === 0" class="api-keys__empty">
        <p class="api-keys__empty-title">{{ t('settings.v4.apiKeys.empty.title') }}</p>
        <p class="api-keys__empty-desc">{{ t('settings.v4.apiKeys.empty.description') }}</p>
      </div>

      <div v-else class="api-keys__table-wrap">
        <table class="api-keys__table">
          <thead>
            <tr>
              <th>{{ t('settings.v4.apiKeys.table.label') }}</th>
              <th>{{ t('settings.v4.apiKeys.table.prefix') }}</th>
              <th>{{ t('settings.v4.apiKeys.table.scopes') }}</th>
              <th>{{ t('settings.v4.apiKeys.table.status') }}</th>
              <th>{{ t('settings.v4.apiKeys.table.createdAt') }}</th>
              <th>{{ t('settings.v4.apiKeys.table.lastUsedAt') }}</th>
              <th>{{ t('settings.v4.apiKeys.table.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="key in store.items" :key="key.id">
              <td>{{ key.label }}</td>
              <td><code class="api-keys__prefix">{{ key.prefix }}</code></td>
              <td>
                <span class="api-keys__scope-list">
                  <Badge
                    v-for="scope in key.scopes"
                    :key="scope"
                    tone="blue"
                    :dot="false"
                  >{{ scope }}</Badge>
                </span>
              </td>
              <td>
                <Badge :tone="statusTone(key.status)" :dot="true">
                  {{ t(`settings.v4.apiKeys.status.${key.status}`) }}
                </Badge>
              </td>
              <td>{{ formatDate(key.created_at) }}</td>
              <td>{{ formatDate(key.last_used_at) }}</td>
              <td>
                <button
                  v-if="key.status === 'active'"
                  class="v4-btn v4-btn--ghost v4-btn--danger"
                  @click="openRevokeDialog(key)"
                >
                  {{ t('settings.v4.apiKeys.actions.revoke') }}
                </button>
                <span v-else class="api-keys__revoked-label">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>

    <!-- Create-Modal -->
    <Teleport to="body">
      <div
        v-if="createModalOpen"
        class="v4-modal-backdrop"
        role="dialog"
        aria-modal="true"
        @click.self="closeCreateModal"
      >
        <div class="v4-modal">
          <!-- Token-Display-Mode nach Erstellung -->
          <template v-if="store.lastCreatedToken">
            <h2 class="v4-modal__title">{{ t('settings.v4.apiKeys.created.title') }}</h2>
            <p class="v4-modal__subtitle v4-modal__warning">
              {{ t('settings.v4.apiKeys.created.warning') }}
            </p>
            <label class="v4-form-label">{{ t('settings.v4.apiKeys.created.tokenLabel') }}</label>
            <div class="api-keys__token-row">
              <Input
                :model-value="store.lastCreatedToken"
                :mono="true"
                :disabled="true"
              />
              <button class="v4-btn v4-btn--secondary" @click="copyToken">
                {{ tokenCopied ? t('settings.v4.apiKeys.actions.copied') : t('settings.v4.apiKeys.actions.copy') }}
              </button>
            </div>
            <div v-if="copyError" class="api-keys__form-error" role="alert">
              {{ copyError }}
            </div>
            <div class="v4-modal__footer">
              <button class="v4-btn v4-btn--primary" @click="closeCreateModal">
                {{ t('settings.v4.apiKeys.actions.close') }}
              </button>
            </div>
          </template>

          <!-- Create-Form-Mode -->
          <template v-else>
            <h2 class="v4-modal__title">{{ t('settings.v4.apiKeys.create.modalTitle') }}</h2>
            <p class="v4-modal__subtitle">{{ t('settings.v4.apiKeys.create.modalSubtitle') }}</p>

            <div class="v4-form-group">
              <label class="v4-form-label" for="api-key-label">
                {{ t('settings.v4.apiKeys.create.labelField') }}
              </label>
              <Input
                id="api-key-label"
                v-model="createLabel"
                :placeholder="t('settings.v4.apiKeys.create.labelField')"
              />
            </div>

            <div class="v4-form-group">
              <label class="v4-form-label">{{ t('settings.v4.apiKeys.create.scopesField') }}</label>
              <div class="api-keys__scopes">
                <label
                  v-for="scope in SCOPES"
                  :key="scope"
                  class="api-keys__scope-check"
                >
                  <input
                    type="checkbox"
                    :value="scope"
                    :checked="createScopes.includes(scope)"
                    @change="toggleScope(scope)"
                  />
                  {{ t(`settings.v4.apiKeys.create.scopes.${scope}`) }}
                </label>
              </div>
            </div>

            <div v-if="createError" class="api-keys__form-error" role="alert">
              {{ createError }}
            </div>

            <div class="v4-modal__footer">
              <button
                class="v4-btn v4-btn--ghost"
                :disabled="store.creating"
                @click="closeCreateModal"
              >
                {{ t('settings.v4.apiKeys.actions.cancel') }}
              </button>
              <button
                class="v4-btn v4-btn--primary"
                :disabled="store.creating"
                @click="submitCreate"
              >
                {{ store.creating ? t('common.loading') : t('settings.v4.apiKeys.create.submit') }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </Teleport>

    <!-- Revoke-Confirm-Dialog -->
    <Teleport to="body">
      <div
        v-if="revokeTarget"
        class="v4-modal-backdrop"
        role="dialog"
        aria-modal="true"
        @click.self="closeRevokeDialog"
      >
        <div class="v4-modal v4-modal--narrow">
          <h2 class="v4-modal__title">{{ t('settings.v4.apiKeys.revoke.modalTitle') }}</h2>
          <p class="v4-modal__subtitle">{{ t('settings.v4.apiKeys.revoke.modalSubtitle') }}</p>
          <p class="api-keys__revoke-target">
            <strong>{{ revokeTarget.label }}</strong>
            <code class="api-keys__prefix">{{ revokeTarget.prefix }}</code>
          </p>

          <div v-if="revokeError" class="api-keys__form-error" role="alert">
            {{ revokeError }}
          </div>

          <div class="v4-modal__footer">
            <button class="v4-btn v4-btn--ghost" @click="closeRevokeDialog">
              {{ t('settings.v4.apiKeys.actions.cancel') }}
            </button>
            <button class="v4-btn v4-btn--danger" @click="confirmRevoke">
              {{ t('settings.v4.apiKeys.revoke.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </AppShell>
</template>

<style scoped>
/* Error Banner */
.api-keys__error-banner {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--status-red-bg, #fff1f0);
  color: var(--status-red, #c0392b);
  border-radius: var(--r-4, 8px);
  font-size: 14px;
}

/* Hint text in create card */
.api-keys__hint {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

/* Loading / Empty state */
.api-keys__loading,
.api-keys__empty {
  text-align: center;
  padding: 40px 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.api-keys__empty-title {
  font-weight: 600;
  margin: 0 0 6px;
  color: var(--text-primary);
}

.api-keys__empty-desc {
  margin: 0;
}

/* Table */
.api-keys__table-wrap {
  overflow-x: auto;
}

.api-keys__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.api-keys__table th {
  text-align: left;
  padding: 8px 12px;
  font-weight: 500;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--separator, #e5e5ea);
  white-space: nowrap;
}

.api-keys__table td {
  padding: 10px 12px;
  vertical-align: middle;
  border-bottom: 1px solid var(--hairline, #f2f2f7);
}

.api-keys__table tbody tr:last-child td {
  border-bottom: none;
}

.api-keys__prefix {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  background: var(--surface-inset, #f2f2f7);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--text-secondary);
}

.api-keys__scope-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.api-keys__revoked-label {
  color: var(--text-tertiary);
}

/* Modal */
.v4-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 24px;
}

.v4-modal {
  background: var(--surface-elevated, #fff);
  border-radius: 16px;
  padding: 28px;
  width: 100%;
  max-width: 480px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.18);
}

.v4-modal--narrow {
  max-width: 400px;
}

.v4-modal__title {
  margin: 0 0 6px;
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
}

.v4-modal__subtitle {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.v4-modal__warning {
  color: var(--status-red, #c0392b);
  background: var(--status-red-bg, #fff1f0);
  padding: 10px 12px;
  border-radius: 8px;
}

.v4-modal__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 24px;
}

/* Form */
.v4-form-group {
  margin-bottom: 16px;
}

.v4-form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.api-keys__scopes {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.api-keys__scope-check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text-primary);
  cursor: pointer;
}

.api-keys__token-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}

.api-keys__token-row .v4-btn {
  flex: none;
}

.api-keys__form-error {
  padding: 10px 12px;
  background: var(--status-red-bg, #fff1f0);
  color: var(--status-red, #c0392b);
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 8px;
}

.api-keys__revoke-target {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px;
  font-size: 14px;
}

/* Buttons — lokale Definitionen (kein globales v4-Btn-System vorhanden) */
.v4-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: var(--ctl-h-md, 36px);
  padding: 0 16px;
  border-radius: var(--r-4, 8px);
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: background 120ms ease, opacity 120ms ease;
  white-space: nowrap;
}

.v4-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.v4-btn--primary {
  background: var(--accent, #0071e3);
  color: #fff;
}

.v4-btn--primary:hover:not(:disabled) {
  background: var(--accent-hover, #0077ed);
}

.v4-btn--secondary {
  background: var(--surface-inset, #f2f2f7);
  color: var(--text-primary);
}

.v4-btn--secondary:hover:not(:disabled) {
  background: var(--gray-5, #e5e5ea);
}

.v4-btn--ghost {
  background: transparent;
  color: var(--text-secondary);
}

.v4-btn--ghost:hover:not(:disabled) {
  background: var(--surface-inset, #f2f2f7);
}

.v4-btn--danger {
  background: var(--status-red, #c0392b);
  color: #fff;
}

.v4-btn--danger:hover:not(:disabled) {
  background: var(--status-red-hover, #a93226);
}

.v4-btn--ghost.v4-btn--danger {
  background: transparent;
  color: var(--status-red, #c0392b);
}

.v4-btn--ghost.v4-btn--danger:hover:not(:disabled) {
  background: var(--status-red-bg, #fff1f0);
}
</style>
