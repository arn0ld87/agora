<script setup lang="ts">
/**
 * SettingsWindow — das Einstellungsfenster (Bauplan §5, Etappe 3).
 *
 * Ein modaler Dialog über der zuletzt gezeigten Ansicht: links die Liste der
 * neun Abschnitte als Navigation, rechts der Inhalt des gewählten Abschnitts.
 * Jeder Abschnitt hat eine eigene Adresse (`/settings/:section`); der
 * Abschnittswechsel ersetzt den Verlaufseintrag, damit „Zurück“ das Fenster
 * schließt statt durch die Abschnitte zu laufen.
 *
 * Die Ansicht darunter rendert App.vue (Hintergrundroute, siehe dort); diese
 * Komponente kümmert sich nur um Fenster, Fokus und Schließen.
 *
 * A11y: Fokusfalle und `Esc` kommen von reka-ui, der Fokus kehrt zum Auslöser
 * zurück, Dialog und Inhalt tragen `aria-labelledby`, die Liste markiert den
 * aktuellen Abschnitt mit `aria-current`.
 */
import { computed, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  DialogClose,
  DialogContent,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from 'reka-ui'
import { useOperatorAccess } from '@/composables/useOperatorAccess'
import { useDemoPreview } from '@/composables/useDemoPreview'
import { useSettingsWindowStore } from '@/stores/settingsWindow'
import {
  SETTINGS_FALLBACK_PATH,
  getSettingsSection,
  isSectionLocked,
  normalizeSettingsSection,
  settingsSectionPath,
  visibleSettingsSections,
  type SettingsSectionId,
} from './sections'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useSettingsWindowStore()
const operator = useOperatorAccess()
const demoPreview = useDemoPreview()

const contentTitleId = useId()

/** Auslöser merken, bevor reka-ui den Fokus ins Fenster zieht. */
const opener: Element | null = typeof document === 'undefined' ? null : document.activeElement

const sections = computed(() =>
  visibleSettingsSections({ operator: operator.value, demoPreview: demoPreview.value }),
)

const currentId = computed<SettingsSectionId>(() =>
  normalizeSettingsSection(route.meta?.settingsSection ?? route.params.section),
)
const current = computed(() => getSettingsSection(currentId.value))
const locked = computed(() => isSectionLocked(current.value, operator.value))

function close(): void {
  const target = store.returnTo ?? SETTINGS_FALLBACK_PATH
  // Wurde das Fenster aus der App geöffnet, ist der Eintrag davor die Ansicht
  // darunter: dann ist „Schließen“ dasselbe wie Browser-Zurück.
  const back = (window.history.state as { back?: string | null } | null)?.back
  if (back && back === target) router.back()
  else void router.replace(target)
}

function onSelect(event: Event): void {
  const id = (event.target as HTMLSelectElement).value
  void router.replace(settingsSectionPath(normalizeSettingsSection(id)))
}

function restoreFocus(event: Event): void {
  event.preventDefault()
  if (opener instanceof HTMLElement && opener.isConnected && opener !== document.body) {
    opener.focus()
  }
}
</script>

<template>
  <DialogRoot :open="true" @update:open="(open: boolean) => { if (!open) close() }">
    <DialogPortal>
      <DialogOverlay class="sw-overlay" />
      <DialogContent
        class="sw"
        :aria-describedby="undefined"
        data-testid="settings-window"
        @close-auto-focus="restoreFocus"
      >
        <nav class="sw__nav" :aria-label="t('views.settingsWindow.navLabel')">
          <!-- reka-ui verknuepft DialogTitle automatisch per aria-labelledby mit dem Dialog. -->
          <DialogTitle class="sw__title">{{ t('views.settingsWindow.title') }}</DialogTitle>

          <ul class="sw__list">
            <li v-for="s in sections" :key="s.id">
              <RouterLink
                :to="settingsSectionPath(s.id)"
                replace
                class="sw__item"
                :class="{ 'sw__item--active': s.id === currentId }"
                :aria-current="s.id === currentId ? 'page' : undefined"
                :data-testid="`settings-section-${s.id}`"
              >
                <span class="sw__glyph" aria-hidden="true">{{ s.glyph }}</span>
                <span class="sw__label">{{ t(s.labelKey) }}</span>
              </RouterLink>
            </li>
          </ul>

          <!-- Unter 768 px ersetzt die Auswahl die Liste (siehe CSS). -->
          <select
            class="sw__select"
            :aria-label="t('views.settingsWindow.sectionSelect')"
            :value="currentId"
            @change="onSelect"
          >
            <option v-for="s in sections" :key="s.id" :value="s.id">{{ t(s.labelKey) }}</option>
          </select>
        </nav>

        <div class="sw__main">
          <header class="sw__header">
            <h3 :id="contentTitleId" class="sw__heading">{{ t(current.labelKey) }}</h3>
            <DialogClose class="sw__close" :aria-label="t('views.settingsWindow.close')">
              <span aria-hidden="true">✕</span>
            </DialogClose>
          </header>

          <div
            class="sw__content"
            role="region"
            tabindex="0"
            :aria-labelledby="contentTitleId"
            data-testid="settings-window-content"
          >
            <p v-if="locked" class="sw__locked" role="status">
              {{ t('views.settingsWindow.operatorOnly') }}
            </p>
            <component :is="current.component" v-else :key="current.id" />
          </div>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.sw-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: var(--scrim);
}

.sw {
  position: fixed;
  z-index: 201;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: min(960px, calc(100vw - 32px));
  height: min(660px, calc(100dvh - 32px));
  display: flex;
  background: var(--s2);
  color: var(--fg);
  border-radius: var(--ag-r-16);
  box-shadow: var(--shadow-dlg);
  overflow: hidden;
  font-family: var(--ag-font-sans);
}

.sw__nav {
  width: 232px;
  flex: none;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 16px 10px;
  background: var(--s1);
  overflow-y: auto;
}

.sw__title {
  margin: 0;
  padding: 2px 10px 12px;
  font-size: 15px;
  font-weight: 650;
}

.sw__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sw__item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 34px;
  padding: 0 10px;
  border-radius: var(--ag-r-8);
  color: var(--fg);
  font-size: 13.5px;
  text-decoration: none;
  background: transparent;
}

.sw__item:hover {
  background: var(--s3);
}

.sw__item--active,
.sw__item--active:hover {
  background: var(--acc-soft);
}

.sw__item:focus-visible,
.sw__close:focus-visible,
.sw__content:focus-visible,
.sw__select:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.sw__glyph {
  width: 24px;
  height: 24px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--s3);
  color: var(--fg2);
  font-size: 10.5px;
  font-weight: 700;
}

.sw__item--active .sw__glyph {
  background: var(--acc);
  color: var(--on-acc);
}

.sw__select {
  display: none;
}

.sw__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.sw__header {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 16px 8px 26px;
}

.sw__heading {
  flex: 1;
  margin: 0;
  font-size: 18px;
  font-weight: 650;
}

.sw__close {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: var(--ag-r-8);
  background: transparent;
  color: var(--fg2);
  font: inherit;
  font-size: 15px;
  cursor: pointer;
}

.sw__close:hover {
  background: var(--s3);
}

.sw__content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px 26px 26px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sw__locked {
  margin: 0;
  padding: 12px 14px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  color: var(--fg);
  font-size: 13px;
  line-height: 1.5;
}

@media (max-width: 767px) {
  .sw {
    flex-direction: column;
    width: calc(100vw - 16px);
    height: calc(100dvh - 16px);
  }

  .sw__nav {
    width: auto;
    flex: none;
    overflow: visible;
    padding: 12px 12px 8px;
  }

  .sw__title {
    padding-bottom: 8px;
  }

  .sw__list {
    display: none;
  }

  .sw__select {
    display: block;
    width: 100%;
    height: 36px;
    padding: 0 10px;
    border: 1px solid var(--line);
    border-radius: var(--ag-r-8);
    background: var(--field);
    color: var(--fg);
    font: inherit;
    font-size: 13.5px;
  }

  .sw__header {
    padding: 12px 12px 4px 16px;
  }

  .sw__content {
    padding: 8px 16px 16px;
  }
}
</style>
