<template>
  <DropdownMenu align="end">
    <template #trigger="{ isOpen }">
      <!-- as-child: reka-ui uebernimmt das Click-Handling und mergt
           aria-haspopup/aria-expanded auf diesen Button. Ein eigenes
           @click wuerde doppelt togglen (oeffnet-und-schliesst-sofort). -->
      <button
        type="button"
        class="user-menu__trigger"
        :data-testid="ShellTestId.userMenuButton"
        :aria-expanded="isOpen"
        :aria-label="triggerLabel"
      >
        <span v-if="initials">{{ initials }}</span>
        <svg v-else class="user-menu__glyph" aria-hidden="true" viewBox="0 0 24 24" width="14" height="14"
          fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="8.5" r="3.5" />
          <path d="M4.8 19.5c1.35-3.8 4.2-5.8 7.2-5.8s5.85 2 7.2 5.8" />
        </svg>
      </button>
    </template>
    <template #default="{ close }">
      <div class="user-menu__items" role="group" :data-testid="ShellTestId.userMenu">
        <DropdownMenuItem @select="() => { close(); goTo('SettingsProfile') }">
          {{ t('topbar.userMenu.profile') }}
        </DropdownMenuItem>
        <DropdownMenuItem @select="() => { close(); goTo('SettingsGeneral') }">
          {{ t('topbar.userMenu.settings') }}
        </DropdownMenuItem>
        <DropdownMenuItem @select="() => { close(); openHelp() }">
          {{ t('topbar.userMenu.help') }}
        </DropdownMenuItem>
      </div>
    </template>
  </DropdownMenu>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import DropdownMenu from '../v4/forms/DropdownMenu.vue'
import DropdownMenuItem from '../v4/forms/DropdownMenuItem.vue'
import { ShellTestId } from '../../contracts/testIds'
import { useUserProfileStore } from '../../store/userProfile'

/**
 * UserMenu — das Nutzermenue oben rechts.
 *
 * Ersetzt die Attrappe, die dort stand: erst ein `<div>AD</div>` in der
 * alten Kopfzeile, dann ein `AS` in der neuen — beide ohne Funktion, das
 * zweite nicht einmal fokussierbar. Die Initialen kommen jetzt aus dem
 * Profil-Store; ohne Profil greift zuerst der Benutzername, sonst ein
 * neutrales Personen-Symbol — nie ein erfundenes Kuerzel und nie ein
 * Fragezeichen (Redesign-Audit §14 "Chrome-Rauschen": das "?"-Symbol war
 * genau dieser Fallback, siehe 01-visual-audit.md).
 *
 * Bewusst EINE Komponente fuer beide Huellen: die alte Kopfzeile
 * (v4/shell/Topbar) verschwindet mit dem Umschalten auf die neue Shell,
 * bis dahin soll das Menue an beiden Stellen dasselbe tun.
 */

const HELP_URL = 'https://github.com/arn0ld87/agora#readme'

const { t } = useI18n()
const router = useRouter()
const userProfileStore = useUserProfileStore()

const displayName = computed(() => userProfileStore.profile?.display_name?.trim() || '')

/** Initialen analog ProfileForm.vue — erster + letzter Namensteil. Ohne
 *  Anzeigename faellt das auf den ersten Buchstaben des Benutzernamens
 *  zurueck; erst wenn auch der fehlt, zeigt der Trigger gar keinen Text
 *  und das Template rendert stattdessen ein neutrales Personen-Symbol. */
const initials = computed(() => {
  const name = displayName.value
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean)
    const first = parts[0]?.charAt(0) ?? ''
    const last = parts.length > 1 ? parts[parts.length - 1].charAt(0) : ''
    return (first + last).toUpperCase()
  }
  const username = userProfileStore.profile?.username?.trim() ?? ''
  return username ? username.charAt(0).toUpperCase() : ''
})

const triggerLabel = computed(() =>
  displayName.value
    ? t('topbar.userMenu.trigger', { name: displayName.value })
    : t('topbar.userMenu.triggerUnknown'),
)

function goTo(routeName: 'SettingsProfile' | 'SettingsGeneral'): void {
  router.push({ name: routeName })
}

/** Kein Help/Docs-Ziel im Router (geprueft) — Fallback auf den README-Anker.
 *  window.open() statt <a target="_blank" rel="noopener">, weil ein
 *  verschachteltes <a> in einem role="menuitem" ein doppeltes interaktives
 *  Element waere (A11y-Anti-Pattern); "noopener" verhindert den
 *  window.opener-Leak identisch zum rel-Attribut. */
function openHelp(): void {
  window.open(HELP_URL, '_blank', 'noopener,noreferrer')
}
</script>

<style scoped>
.user-menu__trigger {
  width: var(--ctl-h-md);
  height: var(--ctl-h-md);
  border-radius: 50%;
  border: 1px solid var(--hairline);
  background: var(--accent-tint-bg);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: var(--fs-subhead);
  font-weight: 600;
  letter-spacing: 0.02em;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.user-menu__trigger:hover {
  background: var(--accent-tint-bg-strong);
}

.user-menu__trigger:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.user-menu__items {
  display: flex;
  flex-direction: column;
  min-width: 180px;
}
</style>
