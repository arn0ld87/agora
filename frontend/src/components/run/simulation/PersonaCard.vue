<script setup lang="ts">
/**
 * Persona-Karte der Feed-Oberfläche (#1801): Name, Rolle, Haltung, Bio. Ist
 * keine Haltung erfasst, steht das da; es wird nichts geraten. „Befragen"
 * (Etappe 6) erscheint nur, wenn der Aufrufer ein Ziel (`interviewTo`) setzt,
 * also bei abgeschlossener Simulation und gewählter Persona.
 */
import type { RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { RunPersona } from '@/composables/run/simulation/useRunPersonas'

defineProps<{
  /** Persona aus den Profilen; null, wenn keine gewählt oder kein Profil vorliegt. */
  persona: RunPersona | null
  /** Anzeigename aus dem Beitrag, wenn kein Profil vorliegt. */
  fallbackName?: string | null
  /** Ziel des Verweises „Befragen" (Interviews, `persona-<id>`); ohne Angabe fehlt er. */
  interviewTo?: RouteLocationRaw | null
}>()
const { t } = useI18n()
</script>

<template>
  <section class="pcard" :aria-label="t('views.run.simFeed.persona.title')" data-testid="persona-card">
    <template v-if="persona">
      <h3 class="pcard__name" data-testid="persona-card-name">{{ persona.name }}</h3>
      <dl class="pcard__facts">
        <dt>{{ t('views.run.simFeed.persona.role') }}</dt>
        <dd data-testid="persona-card-role">{{ persona.role ?? t('views.run.simFeed.persona.roleMissing') }}</dd>
        <dt>{{ t('views.run.simFeed.persona.stance') }}</dt>
        <dd data-testid="persona-card-stance">
          {{ persona.stance ?? t('views.run.simFeed.persona.stanceMissing') }}
        </dd>
        <template v-if="persona.bio">
          <dt>{{ t('views.run.simFeed.persona.bio') }}</dt>
          <dd data-testid="persona-card-bio">{{ persona.bio }}</dd>
        </template>
      </dl>
    </template>
    <template v-else-if="fallbackName">
      <h3 class="pcard__name" data-testid="persona-card-name">{{ fallbackName }}</h3>
      <p class="pcard__hint" data-testid="persona-card-missing">
        {{ t('views.run.simFeed.persona.profileMissing') }}
      </p>
    </template>
    <p v-else class="pcard__hint" data-testid="persona-card-none">{{ t('views.run.simFeed.persona.none') }}</p>
    <router-link v-if="interviewTo" :to="interviewTo" class="pcard__ask" data-testid="persona-card-interview">
      {{ t('views.run.simFeed.persona.interview') }}
    </router-link>
  </section>
</template>

<style scoped>
.pcard {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
}
.pcard__name {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
}
.pcard__facts {
  display: grid;
  gap: 2px;
  margin: 0;
  font-size: 13px;
}
.pcard__facts dt {
  margin-top: 6px;
  color: var(--fg3);
  font-size: 12px;
  font-weight: 600;
}
.pcard__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.pcard__ask {
  align-self: flex-start;
  padding: 4px 10px;
  border: 1px solid var(--acc-line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font-size: 13px;
  text-decoration: none;
}
.pcard__ask:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}
.pcard__hint {
  margin: 0;
  color: var(--fg2);
  font-size: 13px;
}
</style>
