import { createI18n } from 'vue-i18n'
import de from './locales/de.json'
import en from './locales/en.json'

const SUPPORTED: string[] = ['de', 'en']
const STORAGE_KEY = 'agora.locale'
const DEFAULT_LOCALE = 'de'

function safeStorage(): Storage | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null
  } catch {
    return null
  }
}

function safeDocument(): Document | null {
  return typeof document !== 'undefined' ? document : null
}

function readStored(): string | null {
  try {
    return safeStorage()?.getItem(STORAGE_KEY) ?? null
  } catch {
    return null
  }
}

function writeStored(locale: string): void {
  try {
    safeStorage()?.setItem(STORAGE_KEY, locale)
  } catch {
    // Quota exceeded / Safari private mode / SecurityError — locale change
    // remains in-memory + document.lang; persistence is best-effort.
  }
}

function detectLocale(): string {
  const stored = readStored()
  if (stored && SUPPORTED.includes(stored)) return stored
  return DEFAULT_LOCALE
}

const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: detectLocale(),
  fallbackLocale: 'en',
  messages: { de, en },
})

export function setLocale(locale: string): void {
  if (!SUPPORTED.includes(locale)) return
  i18n.global.locale.value = locale as 'de' | 'en'
  writeStored(locale)
  safeDocument()?.documentElement.setAttribute('lang', locale)
}

export function currentLocale(): string {
  return i18n.global.locale.value
}

safeDocument()?.documentElement.setAttribute('lang', detectLocale())

export default i18n
