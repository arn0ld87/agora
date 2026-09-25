<script setup lang="ts">
/**
 * LoginView — Anmelde-Formular für JWT-Auth (#1617).
 */
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../../store/auth'
import { safeNext } from '../../auth/safeNext'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const email = ref('')
const password = ref('')
const pending = ref(false)
const errorMsg = ref('')

async function submit(): Promise<void> {
  errorMsg.value = ''
  pending.value = true
  try {
    await auth.signIn(email.value, password.value)
    await router.replace(safeNext(route.query.next))
  } catch {
    errorMsg.value = t('auth.login.errorGeneric')
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <div class="auth-layout">
    <main class="auth-card" aria-labelledby="login-heading">
      <h1 id="login-heading" class="auth-title">{{ t('auth.login.title') }}</h1>

      <form @submit.prevent="submit" novalidate>
        <div class="form-group">
          <label for="login-email">{{ t('auth.login.emailLabel') }}</label>
          <input
            id="login-email"
            v-model="email"
            type="email"
            autocomplete="email"
            required
            :disabled="pending"
          />
        </div>

        <div class="form-group">
          <label for="login-password">{{ t('auth.login.passwordLabel') }}</label>
          <input
            id="login-password"
            v-model="password"
            type="password"
            autocomplete="current-password"
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
          {{ pending ? t('auth.login.submitting') : t('auth.login.submit') }}
        </button>
      </form>

      <nav class="auth-links">
        <router-link :to="{ name: 'PasswordReset' }">{{ t('auth.login.forgotPassword') }}</router-link>
        <router-link :to="{ name: 'Register' }">{{ t('auth.login.toRegister') }}</router-link>
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

.auth-error {
  color: var(--color-error, #f38ba8);
  font-size: var(--text-sm, 0.875rem);
  margin-bottom: var(--space-4, 1rem);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  background: var(--color-error-bg, rgba(243, 139, 168, 0.1));
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
