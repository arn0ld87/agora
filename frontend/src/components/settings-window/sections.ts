/**
 * Abschnitte des Einstellungsfensters (Bauplan §5) — die eine Quelle.
 *
 * Fenster, Router (Zugangsregeln) und später die Befehlspalette lesen von
 * hier. Reihenfolge = Sichtreihenfolge der Liste.
 *
 * Zugangsregeln spiegeln die `meta`-Flags der bisherigen Einstellungsrouten
 * (`operatorOnly`: prozessweiter Betreiber-Zustand, `requiresAuth`: Token
 * nötig):
 *  - general      ← settings/general        (operatorOnly)
 *  - providers    ← settings/llm-providers  (operatorOnly + requiresAuth);
 *                   workspace/provider-keys (nur requiresAuth) bleibt für
 *                   Nicht-Betreiber erreichbar, deshalb hier nicht operatorOnly.
 *  - profiles     ← settings/llm-routing    (operatorOnly + requiresAuth)
 *  - embedding    ← settings/embedding      (operatorOnly + requiresAuth)
 *  - pipeline     ← settings/integrations   (operatorOnly)
 *  - access       ← settings/api-keys, audit-logs, profile (operatorOnly). `requiresAuth`
 *                   bewusst aus: `settings/profile` war ohne Token erreichbar; die
 *                   Gruppen Schlüssel und Audit-Protokoll prüfen Token/Sitzung selbst.
 *  - appearance, system: bisher nirgends als Einstellung geführt, nur lokale
 *    Darstellung bzw. Lesezugriff auf den Systemzustand — offen.
 *  - budgets: neu, schreibt Standardgrenzen des Betreibers — operatorOnly.
 */
import { defineAsyncComponent, type Component } from 'vue'

export const SETTINGS_SECTION_IDS = [
  'general',
  'appearance',
  'providers',
  'profiles',
  'embedding',
  'pipeline',
  'budgets',
  'access',
  'system',
] as const

export type SettingsSectionId = (typeof SETTINGS_SECTION_IDS)[number]

export const DEFAULT_SETTINGS_SECTION: SettingsSectionId = 'general'

/** Adresse, auf die „Schließen“ ohne bekannte vorherige Ansicht führt. */
export const SETTINGS_FALLBACK_PATH = '/library/runs'

export interface SettingsSectionDef {
  id: SettingsSectionId
  /** i18n-Schlüssel der Beschriftung (de/en). */
  labelKey: string
  /** Zeichen im runden Symbol der Liste (Entwurf AgoraEinstellungen). */
  glyph: string
  component: Component
  /** Nur Betreiber dürfen ändern; Besucher der Demo-Instanz sehen eine Vorschau. */
  operatorOnly: boolean
  /** Ohne Token nicht erreichbar (wie `meta.requiresAuth` der alten Routen). */
  requiresAuth: boolean
}

function lazy(loader: () => Promise<{ default: Component }>): Component {
  return defineAsyncComponent(loader)
}

export const SETTINGS_SECTIONS: readonly SettingsSectionDef[] = [
  {
    id: 'general',
    labelKey: 'views.settingsWindow.sections.general',
    glyph: '⚙︎',
    component: lazy(() => import('./sections/SectionGeneral.vue')),
    operatorOnly: true,
    requiresAuth: false,
  },
  {
    id: 'appearance',
    labelKey: 'views.settingsWindow.sections.appearance',
    glyph: 'Aa',
    component: lazy(() => import('./sections/SectionAppearance.vue')),
    operatorOnly: false,
    requiresAuth: false,
  },
  {
    id: 'providers',
    labelKey: 'views.settingsWindow.sections.providers',
    glyph: '◎',
    component: lazy(() => import('./sections/SectionProviders.vue')),
    operatorOnly: false,
    requiresAuth: true,
  },
  {
    id: 'profiles',
    labelKey: 'views.settingsWindow.sections.profiles',
    glyph: '≡',
    component: lazy(() => import('./sections/SectionProfiles.vue')),
    operatorOnly: true,
    requiresAuth: true,
  },
  {
    id: 'embedding',
    labelKey: 'views.settingsWindow.sections.embedding',
    glyph: '∷',
    component: lazy(() => import('./sections/SectionEmbedding.vue')),
    operatorOnly: true,
    requiresAuth: true,
  },
  {
    id: 'pipeline',
    labelKey: 'views.settingsWindow.sections.pipeline',
    glyph: '→',
    component: lazy(() => import('./sections/SectionPipeline.vue')),
    operatorOnly: true,
    requiresAuth: false,
  },
  {
    id: 'budgets',
    labelKey: 'views.settingsWindow.sections.budgets',
    glyph: '€',
    component: lazy(() => import('./sections/SectionBudgets.vue')),
    operatorOnly: true,
    requiresAuth: false,
  },
  {
    id: 'access',
    labelKey: 'views.settingsWindow.sections.access',
    glyph: '⊡',
    component: lazy(() => import('./sections/SectionAccess.vue')),
    operatorOnly: true,
    requiresAuth: false,
  },
  {
    id: 'system',
    labelKey: 'views.settingsWindow.sections.system',
    glyph: '▤',
    component: lazy(() => import('./sections/SectionSystem.vue')),
    operatorOnly: false,
    requiresAuth: false,
  },
]

export function isSettingsSectionId(value: unknown): value is SettingsSectionId {
  return typeof value === 'string' && (SETTINGS_SECTION_IDS as readonly string[]).includes(value)
}

/** Unbekannte Kennung → `general`. */
export function normalizeSettingsSection(value: unknown): SettingsSectionId {
  return isSettingsSectionId(value) ? value : DEFAULT_SETTINGS_SECTION
}

export function getSettingsSection(id: SettingsSectionId): SettingsSectionDef {
  const found = SETTINGS_SECTIONS.find((s) => s.id === id)
  // SETTINGS_SECTIONS deckt SETTINGS_SECTION_IDS vollständig ab (Spec prüft das).
  return found ?? SETTINGS_SECTIONS[0]
}

export function settingsSectionPath(id: SettingsSectionId): string {
  return `/settings/${id}`
}

/**
 * Abschnitte, die in der Liste erscheinen. Betreiber sehen alle; auf der
 * Demo-Instanz sehen Besucher auch die Betreiber-Abschnitte (als Vorschau);
 * sonst nur die offenen.
 */
export function visibleSettingsSections(access: {
  operator: boolean
  demoPreview: boolean
}): SettingsSectionDef[] {
  return SETTINGS_SECTIONS.filter((s) => !s.operatorOnly || access.operator || access.demoPreview)
}

/** Betreiber-Abschnitt ohne Betreiber-Zugang: Inhalt nur als Vorschau, nicht bedienbar. */
export function isSectionLocked(section: SettingsSectionDef, operator: boolean): boolean {
  return section.operatorOnly && !operator
}
