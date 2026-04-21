import { createI18n } from 'vue-i18n'
import de from './locales/de.json'
import en from './locales/en.json'

const SUPPORTED = ['de', 'en']
const STORAGE_KEY = 'agora.locale'

function detectLocale() {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored && SUPPORTED.includes(stored)) return stored
  // Default: German
  return 'de'
}

const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: detectLocale(),
  fallbackLocale: 'en',
  messages: { de, en },
})

export function setLocale(locale) {
  if (!SUPPORTED.includes(locale)) return
  i18n.global.locale.value = locale
  localStorage.setItem(STORAGE_KEY, locale)
  document.documentElement.setAttribute('lang', locale)
}

export function currentLocale() {
  return i18n.global.locale.value
}

document.documentElement.setAttribute('lang', detectLocale())

export default i18n
