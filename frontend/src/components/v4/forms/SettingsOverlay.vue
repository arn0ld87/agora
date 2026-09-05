<script setup lang="ts">
/**
 * SettingsOverlay — gemeinsame Huelle fuer alle `/settings/*`-Seiten
 * (Redesign PR 9, Audit §5 „Einstellungen“, §7 Zeile 9).
 *
 * Ersetzt die pro Seite wiederholten Breadcrumbs („Settings / General“)
 * durch eine Sektionsliste, die alle Einstellungen-Routen in einem
 * Rahmen zusammenhaelt — genau die Redundanz, die Audit-Punkt 12
 * („Breadcrumb ‚Settings / General‘ ueber Titel ‚Allgemein‘“) kritisiert.
 *
 * Bewusst NICHT umgesetzt: die Vorlage (`docs/design/screens/08-
 * einstellungen.html`) zeigt Einstellungen als schwebendes Panel ueber
 * der eingefrorenen Arbeitsflaeche, ohne Sidebar/Topbar. Das braeuchte
 * einen App.vue-weiten Persistenz-Mechanismus fuer die vorherige Seite
 * (der Router tauscht `router-view` heute komplett aus) und damit
 * Eingriffe ausserhalb von „Settings-Views/-Komponenten“. Diese
 * Komponente bleibt deshalb ein normaler Routeninhalt innerhalb von
 * `AppShell`; das „Zurueck“ bringt zur vorherigen Ansicht zurueck,
 * ersetzt aber kein echtes Escape-Overlay.
 */
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import Button from './Button.vue'
import { SettingsOverlayTestId } from '@/contracts/testIds'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

/**
 * Reihenfolge folgt zunaechst der Vorlage `docs/design/screens/08-
 * einstellungen.html`; `SettingsLlmRouting`/`SettingsAuditLogs` haengen
 * dahinter (Review PR #1439): jede View, die SettingsOverlay einbindet,
 * muss eine aktive Sektion zeigen koennen, sonst haette der Nutzer auf
 * diesen beiden Routen keinen sichtbaren Ort in der Liste. `labelKey`
 * referenziert bestehende Strings (`sidebar.settings.*`, `settings.v4.
 * auditLogs.title`), damit kein zweites Label-Set fuer denselben Bereich
 * entsteht.
 */
const NAV_ITEMS: ReadonlyArray<{ routeName: string; labelKey: string }> = [
  { routeName: 'SettingsGeneral', labelKey: 'sidebar.settings.general' },
  { routeName: 'SettingsIntegrations', labelKey: 'sidebar.settings.integrations' },
  { routeName: 'SettingsProfile', labelKey: 'sidebar.settings.profile' },
  { routeName: 'SettingsApiKeys', labelKey: 'sidebar.settings.apiKeys' },
  { routeName: 'SettingsLlmProviders', labelKey: 'sidebar.settings.llmProviders' },
  { routeName: 'SettingsEmbedding', labelKey: 'sidebar.settings.embedding' },
  { routeName: 'SettingsLlmRouting', labelKey: 'settings.v4.overlay.llmRouting' },
  { routeName: 'SettingsAuditLogs', labelKey: 'settings.v4.auditLogs.title' },
]

function isActive(routeName: string): boolean {
  return route.name === routeName
}

function goBack(): void {
  router.back()
}
</script>

<template>
  <div class="settings-overlay" :data-testid="SettingsOverlayTestId.root">
    <header class="settings-overlay__head">
      <h1 class="settings-overlay__title">{{ t('settings.v4.overlay.title') }}</h1>
      <Button
        variant="ghost"
        size="sm"
        :data-testid="SettingsOverlayTestId.back"
        @click="goBack"
      >
        {{ t('settings.v4.overlay.back') }}
      </Button>
    </header>

    <div class="settings-overlay__body">
      <nav
        class="settings-overlay__nav"
        :aria-label="t('settings.v4.overlay.navLabel')"
        :data-testid="SettingsOverlayTestId.nav"
      >
        <ul>
          <li v-for="item in NAV_ITEMS" :key="item.routeName">
            <router-link
              :to="{ name: item.routeName }"
              class="settings-overlay__nav-link"
              :class="{ 'is-active': isActive(item.routeName) }"
              :aria-current="isActive(item.routeName) ? 'page' : undefined"
              :data-testid="SettingsOverlayTestId.navItem"
            >
              {{ t(item.labelKey) }}
            </router-link>
          </li>
        </ul>
      </nav>

      <section class="settings-overlay__content">
        <slot />
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings-overlay {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
}

.settings-overlay__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  padding-bottom: var(--sp-4);
  border-bottom: 1px solid var(--hairline);
}

.settings-overlay__title {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--fs-title);
  line-height: var(--lh-title);
  letter-spacing: var(--tr-title);
  font-weight: 600;
  color: var(--text-primary);
}

.settings-overlay__body {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: var(--sp-6);
  align-items: start;
}

.settings-overlay__nav ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

.settings-overlay__nav-link {
  display: block;
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-3);
  border-left: 2px solid transparent;
  font-family: var(--font-sans);
  font-size: var(--fs-small);
  color: var(--text-secondary);
  text-decoration: none;
}

.settings-overlay__nav-link:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.settings-overlay__nav-link.is-active {
  background: var(--accent-tint-bg);
  border-left-color: var(--accent);
  color: var(--text-primary);
  font-weight: 600;
}

.settings-overlay__nav-link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.settings-overlay__content {
  min-width: 0;
}

@media (max-width: 820px) {
  .settings-overlay__body {
    grid-template-columns: 1fr;
  }

  .settings-overlay__nav ul {
    flex-direction: row;
    flex-wrap: wrap;
  }
}
</style>
