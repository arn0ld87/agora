<script setup lang="ts">
/**
 * EmailConfirmView — Bestätigung nach E-Mail-Link (#1617).
 *
 * Supabase ruft detectSessionInUrl beim Client-Init auf; wenn der Hash-Token
 * gültig ist, existiert eine Session. Wir prüfen das nach kurzer Wartezeit
 * und leiten auf / oder zeigen einen Fehler.
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../../store/auth'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

const checking = ref(true)
const confirmed = ref(false)
const errorMsg = ref('')

onMounted(async () => {
  // getSession() im Store-Init wartet die URL-Auswertung (detectSessionInUrl)
  // ab; ensureInit() liefert dasselbe Promise, das auch der Guard abwartet.
  await auth.ensureInit()
  checking.value = false

  if (auth.session) {
    confirmed.value = true
    setTimeout(() => {
      router.replace('/')
    }, 1500)
  } else {
    errorMsg.value = t('auth.confirm.errorInvalidLink')
  }
})
</script>

<template>
  <div class="auth-layout">
    <main class="auth-card" aria-labelledby="confirm-heading">
      <h1 id="confirm-heading" class="auth-title">{{ t('auth.confirm.title') }}</h1>

      <div v-if="checking" class="auth-checking" role="status" aria-live="polite">
        {{ t('auth.confirm.checking') }}
      </div>

      <div
        v-else-if="confirmed"
        class="auth-success"
        role="status"
        aria-live="polite"
      >
        {{ t('auth.confirm.successMessage') }}
      </div>

      <div
        v-else
        class="auth-error"
        role="alert"
        aria-live="assertive"
      >
        {{ errorMsg }}
      </div>

      <nav v-if="!checking && !confirmed" class="auth-links">
        <router-link :to="{ name: 'Login' }">{{ t('auth.confirm.toLogin') }}</router-link>
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

.auth-checking {
  color: var(--color-text-muted, #a6adc8);
  font-size: var(--text-sm, 0.875rem);
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

.auth-links {
  margin-top: var(--space-4, 1rem);
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
