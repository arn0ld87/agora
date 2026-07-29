<script setup lang="ts">
/**
 * CommandPalette — Spotlight-artige globale Command-Palette
 *
 * Architektur:
 * - DialogRoot (reka-ui) steuert Modal-Overlay + ESC-Handling
 * - ComboboxRoot (reka-ui) liefert Keyboard-Navigation + Filterung
 * - useCommandPalette: isOpen/query/recent-State
 * - useCommandsStore: statische Nav-Commands + filter/getOrdered
 *
 * Oeffnen: Cmd+K / Ctrl+K (AppShell.vue-Listener) oder Topbar-Search-Icon
 * Schliessen: ESC, Click auf Overlay, oder nach Item-Pick
 */
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  DialogRoot,
  DialogPortal,
  DialogOverlay,
  DialogContent,
} from 'reka-ui'
import {
  ComboboxRoot,
  ComboboxAnchor,
  ComboboxInput,
  ComboboxContent,
  ComboboxViewport,
  ComboboxItem,
  ComboboxEmpty,
  ComboboxGroup,
  ComboboxLabel,
  ComboboxSeparator,
} from 'reka-ui'
import { useCommandPalette } from '@/composables/useCommandPalette'
import { useCommandsStore } from '@/stores/commandsStore'
import type { Command } from '@/stores/commandsStore'

const { isOpen, query, close, pushRecent } = useCommandPalette()
const store = useCommandsStore()
const { t, locale } = useI18n()
const router = useRouter()

// Statische Commands einmalig bauen und mit aktuellem Locale verknuepfen
const staticCommands = computed<Command[]>(() =>
  store.buildStaticCommands(router, locale.value as 'de' | 'en'),
)

// Gefilterte und nach Recent geordnete Commands
const ordered = computed<Command[]>(() => store.getOrdered(staticCommands.value))
const filtered = computed<Command[]>(() => store.filter(ordered.value, query.value))

// Gruppierung fuer die Anzeige: recent-Commands zuerst, dann nav-Commands
const recentCommands = computed(() => filtered.value.filter((c) => c.group === 'recent'))
const navCommands = computed(() => filtered.value.filter((c) => c.group === 'nav'))

function pickCommand(value: unknown): void {
  if (!value || typeof value !== 'string') return
  const cmd = staticCommands.value.find((c) => c.id === value)
  if (!cmd) return
  pushRecent(value)
  close()
  cmd.action()
}

// DialogRoot erwartet Booleens ueber v-model:open;
// ComboboxRoot benoetigt filterFunction=false da wir selbst filtern
</script>

<template>
  <DialogRoot :open="isOpen" @update:open="(v) => !v && close()">
    <DialogPortal>
      <DialogOverlay class="cmdk-overlay" @click="close" />
      <DialogContent
        class="cmdk-content"
        :aria-label="t('cmd.title')"
        @escape-key-down="close"
      >
        <ComboboxRoot
          :model-value="undefined"
          :filter-function="() => true"
          class="cmdk-combobox"
          @update:model-value="pickCommand"
        >
          <ComboboxAnchor class="cmdk-anchor">
            <ComboboxInput
              v-model="query"
              class="cmdk-input"
              :placeholder="t('cmd.placeholder')"
              :auto-focus="true"
            />
          </ComboboxAnchor>

          <ComboboxContent class="cmdk-list-wrapper">
            <ComboboxViewport class="cmdk-list">
              <!-- Recent-Gruppe -->
              <ComboboxGroup v-if="recentCommands.length > 0">
                <ComboboxLabel class="cmdk-group-label">
                  {{ t('cmd.groups.recent') }}
                </ComboboxLabel>
                <ComboboxItem
                  v-for="cmd in recentCommands"
                  :key="cmd.id"
                  :value="cmd.id"
                  class="cmdk-item v4-state-selectable"
                >
                  <span class="cmdk-item__label">{{ cmd.label }}</span>
                  <span class="cmdk-item__badge cmdk-item__badge--recent">
                    {{ t('cmd.groups.recent') }}
                  </span>
                </ComboboxItem>
                <ComboboxSeparator v-if="navCommands.length > 0" class="cmdk-separator" />
              </ComboboxGroup>

              <!-- Nav-Gruppe -->
              <ComboboxGroup v-if="navCommands.length > 0">
                <ComboboxLabel class="cmdk-group-label">
                  {{ t('cmd.groups.nav') }}
                </ComboboxLabel>
                <ComboboxItem
                  v-for="cmd in navCommands"
                  :key="cmd.id"
                  :value="cmd.id"
                  class="cmdk-item v4-state-selectable"
                >
                  <span class="cmdk-item__label">{{ cmd.label }}</span>
                </ComboboxItem>
              </ComboboxGroup>

              <!-- Empty-State -->
              <ComboboxEmpty class="cmdk-empty">
                {{ t('cmd.noResults') }}
              </ComboboxEmpty>
            </ComboboxViewport>
          </ComboboxContent>
        </ComboboxRoot>

        <!-- Hint-Leiste -->
        <div class="cmdk-footer">
          <span class="cmdk-hint">
            <kbd class="cmdk-key">↵</kbd> {{ t('cmd.hints.select') }}
          </span>
          <span class="cmdk-hint">
            <kbd class="cmdk-key">↑↓</kbd> {{ t('cmd.hints.navigate') }}
          </span>
          <span class="cmdk-hint">
            <kbd class="cmdk-key">Esc</kbd> {{ t('cmd.hints.close') }}
          </span>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
/* Overlay — dunkles Backdrop hinter der Palette */
.cmdk-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(2px);
  z-index: 200;
  animation: cmdk-overlay-in 120ms ease;
}

@keyframes cmdk-overlay-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/* Dialog-Content: zentriertes Panel */
.cmdk-content {
  position: fixed;
  top: 20%;
  left: 50%;
  transform: translateX(-50%);
  z-index: 201;
  width: min(600px, calc(100vw - 32px));
  background: var(--surface-base, #fff);
  border-radius: 12px;
  box-shadow:
    0 0 0 1px var(--hairline),
    0 20px 60px rgba(0, 0, 0, 0.18),
    0 8px 20px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  animation: cmdk-content-in 140ms cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes cmdk-content-in {
  from { opacity: 0; transform: translateX(-50%) translateY(-8px) scale(0.97); }
  to   { opacity: 1; transform: translateX(-50%) translateY(0)    scale(1);    }
}

/* Combobox-Wrapper */
.cmdk-combobox {
  display: flex;
  flex-direction: column;
}

.cmdk-anchor {
  display: block;
}

/* Input */
.cmdk-input {
  width: 100%;
  padding: 16px 20px;
  font-size: 16px;
  font-weight: 400;
  line-height: 1.4;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--hairline);
  color: var(--text-secondary);
  outline: none;
  box-sizing: border-box;
}

.cmdk-input::placeholder {
  color: var(--text-tertiary, var(--text-secondary));
}

/* Liste */
.cmdk-list-wrapper {
  position: static;
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 0;
  max-height: 360px;
  overflow-y: auto;
}

.cmdk-list {
  padding: 8px 0;
}

/* Gruppen-Label */
.cmdk-group-label {
  padding: 6px 20px 2px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary, var(--text-secondary));
  pointer-events: none;
}

/* Trennlinie */
.cmdk-separator {
  height: 1px;
  background: var(--hairline);
  margin: 4px 12px;
}

/* Item */
.cmdk-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 20px;
  font-size: 14px;
  border-radius: 0;
  border: none;
  outline: none;
  cursor: pointer;
  user-select: none;
}

.cmdk-item[data-highlighted] {
  background: var(--surface-hover, rgba(0, 0, 0, 0.04));
}

.cmdk-item:focus-visible {
  outline: 2px solid var(--accent, currentColor);
  outline-offset: -2px;
}

.cmdk-item__label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cmdk-item__badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.cmdk-item__badge--recent {
  background: var(--accent-tint-bg, rgba(0, 122, 255, 0.08));
  color: var(--accent, #007aff);
}

/* Empty-State */
.cmdk-empty {
  padding: 20px;
  text-align: center;
  font-size: 14px;
  color: var(--text-secondary);
}

/* Footer / Hint-Leiste */
.cmdk-footer {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 20px;
  border-top: 1px solid var(--hairline);
  background: var(--surface-canvas, var(--surface-base));
}

.cmdk-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-tertiary, var(--text-secondary));
}

.cmdk-key {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 4px;
  border-radius: 4px;
  background: var(--surface-hover, rgba(0, 0, 0, 0.06));
  border: 1px solid var(--hairline);
  font-family: inherit;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
}

/* Scrollbar-Styling (WebKit) */
.cmdk-list-wrapper::-webkit-scrollbar {
  width: 6px;
}
.cmdk-list-wrapper::-webkit-scrollbar-thumb {
  background: var(--hairline-strong, var(--hairline));
  border-radius: 3px;
}

/* Reduced-motion */
@media (prefers-reduced-motion: reduce) {
  .cmdk-overlay,
  .cmdk-content {
    animation: none;
  }
}
</style>
