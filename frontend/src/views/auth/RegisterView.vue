<script setup lang="ts">
/**
 * RegisterView — Registrierungs-Formular für JWT-Auth (#1617).
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../../store/auth'

const { t } = useI18n()
const auth = useAuthStore()

const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const pending = ref(false)
const errorMsg = ref('')
const success = ref(false)

async function submit(): Promise<void> {
  errorMsg.value = ''

  if (password.value.length < 12) {
    errorMsg.value = t('auth.register.errorPasswordTooShort')
    return
  }

  if (password.value !== confirmPassword.value) {
    errorMsg.value = t('auth.register.errorPasswordMismatch')
    return
  }

  pending.value = true
  try {
    await auth.signUp(email.value, password.value)
    success.value = true
  } catch {
    errorMsg.value = t('auth.register.errorGeneric')
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <div class="auth-layout">
    <main class="auth-card" aria-labelledby="register-heading">
      <h1 id="register-heading" class="auth-title">{{ t('auth.register.title') }}</h1>

      <div
        v-if="success"
        class="auth-success"
        role="status"
        aria-live="polite"
      >
        {{ t('auth.register.successMessage') }}
      </div>

      <form v-else @submit.prevent="submit" novalidate>
        <div class="form-group">
          <label for="register-email">{{ t('auth.register.emailLabel') }}</label>
          <input
            id="register-email"
            v-model="email"
            type="email"
            autocomplete="email"
            required
            :disabled="pending"
          />
        </div>

        <div class="form-group">
          <label for="register-password">{{ t('auth.register.passwordLabel') }}</label>
          <input
            id="register-password"
            v-model="password"
            type="password"
            autocomplete="new-password"
            required
            minlength="12"
            :disabled="pending"
          />
          <span class="form-hint">{{ t('auth.register.passwordHint') }}</span>
        </div>

        <div class="form-group">
          <label for="register-confirm">{{ t('auth.register.confirmLabel') }}</label>
          <input
            id="register-confirm"
            v-model="confirmPassword"
            type="password"
            autocomplete="new-password"
            required
            :disabled="pending"
          />
        </div>

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
          {{ pending ? t('auth.register.submitting') : t('auth.register.submit') }}
        </button>
      </form>

      <nav v-if="!success" class="auth-links">
        <router-link :to="{ name: 'Login' }">{{ t('auth.register.toLogin') }}</router-link>
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
