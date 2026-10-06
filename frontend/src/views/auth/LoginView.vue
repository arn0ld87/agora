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

const tokenMode = !auth.jwtEnabled
const token = ref('')
const email = ref('')
const password = ref('')
const pending = ref(false)
const errorMsg = ref('')
// Nach dem Passwort-Reset ohne aktivierbaren Workspace (#1617).
const resetDone = route.query.reset === 'done'

async function submit(): Promise<void> {
  errorMsg.value = ''
  pending.value = true
  try {
    if (tokenMode) {
      await auth.signInWithToken(token.value.trim())
      await router.replace(safeNext(route.query.next))
      return
    }
    await auth.signIn(email.value, password.value)
    await router.replace(safeNext(route.query.next))
  } catch {
    errorMsg.value = tokenMode ? t('auth.login.tokenInvalid') : t('auth.login.errorGeneric')
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <div class="auth-layout">
    <main class="auth-card" aria-labelledby="login-heading">
      <h1 id="login-heading" class="auth-title">{{ tokenMode ? t('auth.login.tokenTitle') : t('auth.login.title') }}</h1>

      <form @submit.prevent="submit" novalidate>
        <div v-if="tokenMode" class="form-group">
          <label for="login-token">{{ t('auth.login.tokenLabel') }}</label>
          <input
            id="login-token"
            v-model="token"
            type="password"
            autocomplete="current-password"
            required
            :disabled="pending"
            :aria-invalid="errorMsg ? 'true' : 'false'"
            :aria-describedby="errorMsg ? 'login-token-error' : 'login-token-hint'"
          />
          <p id="login-token-hint" class="auth-hint">{{ t('auth.login.tokenHint') }}</p>
        </div>

        <div v-if="!tokenMode" class="form-group">
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

        <div v-if="!tokenMode" class="form-group">
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

        <p v-if="resetDone && !errorMsg" class="auth-info" role="status">
          {{ t('auth.login.resetDone') }}
        </p>

        <div
          v-if="errorMsg"
          id="login-token-error"
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

      <nav v-if="!tokenMode" class="auth-links">
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
  background: var(--s2);
  border: 1px solid var(--line);
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
  color: var(--fg2);
}

.form-group input {
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  background: var(--field);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm, 6px);
  color: var(--fg);
  font-size: var(--text-base, 1rem);
  outline-offset: 2px;
}

.form-group input:focus-visible {
  outline: 2px solid var(--acc-text);
}

.auth-hint {
  font-size: var(--text-sm, 0.875rem);
  color: var(--fg2);
}

.auth-info {
  font-size: var(--text-sm, 0.875rem);
  margin-bottom: var(--space-4, 1rem);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm, 6px);
}

.auth-error {
  color: var(--err);
  font-size: var(--text-sm, 0.875rem);
  margin-bottom: var(--space-4, 1rem);
  padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
  background: var(--err-soft);
  border-radius: var(--radius-sm, 6px);
}

.auth-submit {
  width: 100%;
  padding: var(--space-2, 0.5rem) var(--space-4, 1rem);
  background: var(--acc);
  color: var(--on-acc);
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
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.auth-links {
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 0.5rem);
  font-size: var(--text-sm, 0.875rem);
}

.auth-links a {
  color: var(--acc-text);
  text-decoration: underline;
}

.auth-links a:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}
</style>
