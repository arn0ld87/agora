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
        {{ initials }}
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
 * Profil-Store; ohne Profil steht dort ein neutrales Fragezeichen statt
 * eines erfundenen Kuerzels.
 *
 * Bewusst EINE Komponente fuer beide Huellen: die alte Kopfzeile
 * (v4/shell/Topbar) verschwindet mit dem Umschalten auf die neue Shell,
 * bis dahin soll das Menue an beiden Stellen dasselbe tun.
 */

const { t } = useI18n()
const router = useRouter()
const userProfileStore = useUserProfileStore()

const displayName = computed(() => userProfileStore.profile?.display_name?.trim() || '')

/** Initialen analog ProfileForm.vue — erster + letzter Namensteil. */
const initials = computed(() => {
  const name = displayName.value
  if (!name) return '?'
  const parts = name.split(/\s+/).filter(Boolean)
  const first = parts[0]?.charAt(0) ?? ''
  const last = parts.length > 1 ? parts[parts.length - 1].charAt(0) : ''
  return (first + last).toUpperCase()
})

const triggerLabel = computed(() =>
  displayName.value
    ? t('topbar.userMenu.trigger', { name: displayName.value })
    : t('topbar.userMenu.triggerUnknown'),
)

function goTo(routeName: 'SettingsProfile' | 'SettingsGeneral'): void {
  router.push({ name: routeName })
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
