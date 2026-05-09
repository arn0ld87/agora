import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import i18n from './i18n'

import './assets/styles/fonts.css'
import './assets/styles/tokens.css'
if (import.meta.env.VITE_DESIGN_V3 === 'true') {
  // Design Language v3 (Apple Enterprise · Light) — overlays v2 tokens via
  // alias layer in tokens-v3.css. EPIC docu/2026-05-09-design-v3-epic.md.
  // v3 ist light-only. data-theme aus localStorage könnte 'dark' sein und
  // würde sonst beim ersten useTheme()-Call (App.vue → ensureWatcher →
  // applyTheme) das DOM-Attribut wieder überschreiben (Gemini-HIGH #340).
  // Daher: DOM-Attribut + ref-State + localStorage konsistent auf 'light'.
  document.documentElement.setAttribute('data-theme', 'light')
  const { useTheme } = await import('./composables/useTheme')
  useTheme().setTheme('light')
  await import('./assets/styles/tokens-v3.css')
}
import './assets/styles/global.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(i18n)

app.mount('#app')
