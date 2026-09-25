<script setup lang="ts">
/**
 * PasswordResetView — Passwort-Reset für JWT-Auth (#1617).
 *
 * Zwei Modi:
 * 1. Request-Modus: E-Mail eingeben → Link senden.
 * 2. Recovery-Modus: wenn Supabase nach Folgen des Mail-Links die Session in
 *    den Recovery-Zustand versetzt, neues Passwort setzen via updatePassword.
 */
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { PasswordUpdatedSignInRequired, useAuthStore } from '../../store/auth'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

// Recovery-Modus: der Store hat PASSWORD_RECOVERY beim Einlesen des
// Reset-Links gesehen (vor dem Mount dieser View).
const isRecoveryMode = computed(() => auth.passwordRecovery)

const email = ref('')
const newPassword = ref('')
const confirmNewPassword = ref('')
const pending = ref(false)
const errorMsg = ref('')
const success = ref(false)

const submitLabel = computed(() =>
  isRecoveryMode.value ? t('auth.reset.submitNew') : t('auth.reset.submitRequest'),
)

async function submit(): Promise<void> {
  errorMsg.value = ''

  if (isRecoveryMode.value) {
    if (newPassword.value.length < 12) {
      errorMsg.value = t('auth.reset.errorPasswordTooShort')
      return
    }
    if (newPassword.value !== confirmNewPassword.value) {
      errorMsg.value = t('auth.reset.errorPasswordMismatch')
      return
    }
    pending.value = true
    try {
      await auth.updatePassword(newPassword.value)
      await router.replace('/')
    } catch (err) {
      if (err instanceof PasswordUpdatedSignInRequired) {
        // Passwort ist gesetzt; der Workspace kommt mit der Anmeldung.
        await router.replace({ name: 'Login', query: { reset: 'done' } })
        return
      }
      errorMsg.value = t('auth.reset.errorGeneric')
    } finally {
      pending.value = false
    }
  } else {
    pending.value = true
    try {
      await auth.requestPasswordReset(email.value)
      success.value = true
    } catch {
      // Nicht verraten ob E-Mail bekannt ist
      success.value = true
    } finally {
      pending.value = false
    }
  }
}
</script>

<template>
  <div class="auth-layout">
    <main class="auth-card" aria-labelledby="reset-heading">
      <h1 id="reset-heading" class="auth-title">{{ t('auth.reset.title') }}</h1>

      <div
        v-if="success && !isRecoveryMode"
        class="auth-success"
        role="status"
        aria-live="polite"
      >
        {{ t('auth.reset.successMessage') }}
      </div>

      <form v-else @submit.prevent="submit" novalidate>
        <!-- Request-Modus: E-Mail -->
        <template v-if="!isRecoveryMode">
          <div class="form-group">
            <label for="reset-email">{{ t('auth.reset.emailLabel') }}</label>
            <input
              id="reset-email"
              v-model="email"
              type="email"
              autocomplete="email"
              required
              :disabled="pending"
            />
          </div>
        </template>

        <!-- Recovery-Modus: neues Passwort -->
        <template v-else>
          <div class="form-group">
            <label for="reset-new-password">{{ t('auth.reset.newPasswordLabel') }}</label>
            <input
              id="reset-new-password"
              v-model="newPassword"
              type="password"
              autocomplete="new-password"
              required
              minlength="12"
              :disabled="pending"
            />
            <span class="form-hint">{{ t('auth.reset.passwordHint') }}</span>
          </div>
          <div class="form-group">
            <label for="reset-confirm-password">{{ t('auth.reset.confirmPasswordLabel') }}</label>
            <input
              id="reset-confirm-password"
              v-model="confirmNewPassword"
              type="password"
              autocomplete="new-password"
              required
              :disabled="pending"
            />
          </div>
        </template>

        <div
          v-if="errorMsg"
          class="auth-error"
          role="alert"
          aria-live="assertive"
        >
          {{ errorMsg }}
        </div>

        <button
          type="submit"
          class="auth-submit"
          :disabled="pending"
          :aria-busy="pending"
        >
          {{ pending ? t('auth.reset.submitting') : submitLabel }}
        </button>
      </form>

      <nav class="auth-links">
        <router-link :to="{ name: 'Login' }">{{ t('auth.reset.toLogin') }}</router-link>
      </nav>
    </main>
  </div>
</template>

<style scoped>
.auth-layout {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  padding: var(--space-4);
}

.auth-card {
  background: var(--color-surface, #1e1e2e);
  border: 1px solid var(--color-border, #313244);
  border-radius: var(--radius-lg, 12px);
  padding: var(--space-8, 2rem);
  width: 100%;
  max-width: 400px;
}

.auth-title {
  font-size: var(--text-xl, 1.25rem);
  font-weight: 600;
  margin-bottom: var(--space-6, 1.5rem);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1, 0.25rem);
  margin-bottom: var(--space-4, 1rem);
}

.form-group label {
  font-size: var(--text-sm, 0.875rem);
  color: var(--color-text-muted, #a6adc8);
}

.form-group input {
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  background: var(--color-input-bg, #181825);
  border: 1px solid var(--color-border, #313244);
  border-radius: var(--radius-sm, 6px);
  color: var(--color-text, #cdd6f4);
  font-size: var(--text-base, 1rem);
  outline-offset: 2px;
}

.form-group input:focus-visible {
  outline: 2px solid var(--color-accent, #89b4fa);
}

.form-hint {
  font-size: var(--text-xs, 0.75rem);
  color: var(--color-text-muted, #a6adc8);
}

.auth-error {
  color: var(--color-error, #f38ba8);
  font-size: var(--text-sm, 0.875rem);
  margin-bottom: var(--space-4, 1rem);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  background: var(--color-error-bg, rgba(243, 139, 168, 0.1));
  border-radius: var(--radius-sm, 6px);
}

.auth-success {
  color: var(--color-success, #a6e3a1);
  font-size: var(--text-sm, 0.875rem);
  padding: var(--space-3, 0.75rem);
  background: var(--color-success-bg, rgba(166, 227, 161, 0.1));
  border-radius: var(--radius-sm, 6px);
}

.auth-submit {
  width: 100%;
  padding: var(--space-2, 0.5rem) var(--space-4, 1rem);
  background: var(--color-accent, #89b4fa);
  color: var(--color-on-accent, #1e1e2e);
  border: none;
  border-radius: var(--radius-sm, 6px);
  font-size: var(--text-base, 1rem);
  font-weight: 600;
  cursor: pointer;
  margin-bottom: var(--space-4, 1rem);
}

.auth-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.auth-submit:focus-visible {
  outline: 2px solid var(--color-accent, #89b4fa);
  outline-offset: 2px;
}

.auth-links {
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 0.5rem);
  font-size: var(--text-sm, 0.875rem);
}

.auth-links a {
  color: var(--color-accent, #89b4fa);
  text-decoration: underline;
}

.auth-links a:focus-visible {
  outline: 2px solid var(--color-accent, #89b4fa);
  outline-offset: 2px;
}
</style>
