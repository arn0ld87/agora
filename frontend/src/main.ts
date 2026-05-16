import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { registerI18n } from './i18n/translate'
import { initFrontendTracing } from './observability/tracing'
import { useDensity } from './composables/useDensity'
import { cleanupStaleRuntimeLlmStorage } from './composables/useRuntimeLlmOptions'

import './assets/styles/fonts.css'
import './assets/styles/tokens-v3.css'
import './assets/styles/global.css'
import './assets/styles/states.css'
import './assets/styles/tokens-2026.css'

// Observability: initialise before Vue so the first fetch spans are captured.
initFrontendTracing()

document.documentElement.setAttribute('data-theme', 'light')

// Density: data-density auf <html> setzen bevor Vue mountet → kein FOUC.
// Slice FE-Redesign-6 · 2026-05-15
useDensity().applyOnMount()

const uiVersion = (import.meta.env.VITE_UI_VERSION as string | undefined) ?? 'v4'
;(window as unknown as { __AGORA_UI_VERSION__?: string }).__AGORA_UI_VERSION__ = uiVersion
document.documentElement.setAttribute('data-ui-version', uiVersion)

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(i18n)

// Registriere i18n-Global fuer Stores, die ausserhalb des Vue-Setup-Kontexts
// uebersetzen muessen (z.B. commandsStore). Kein localStorage-Zugriff beim Import.
registerI18n(i18n.global as Parameters<typeof registerI18n>[0])

app.mount('#app')

void cleanupStaleRuntimeLlmStorage()
