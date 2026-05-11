<script setup lang="ts">
/**
 * PersonaCardGrid — Persona-Karten-Liste mit Click/Save/Delete-Aktionen.
 *
 * Sub-Slice 44 (Refs #203): Isoliert den Card-Loop aus Step2EnvSetup.vue.
 *
 * Pure UI-Komponente. Helpers + State werden aus Eltern (usePersonaActions
 * und usePersonaLibrary) als Props injiziert, damit Single-Source-of-Truth
 * mit dem Detail-Modal erhalten bleibt.
 */
import { useI18n } from 'vue-i18n'
import Badge from '../ui/Badge.vue'

interface ReviewIssue {
  code: string
  severity: string
  detail?: { missing?: string[] }
}

interface Props {
  personas: any[]
  savingPersonaKeys: Set<string>
  statusVariant: (status: string) => string
  statusLabel: (status: string) => string
  issueBadgeVariant: (severity: string) => string
  getIssuesFor: (username: string) => ReviewIssue[]
  highestSeverityFor: (username: string) => string
  profileKey: (profile: any) => string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  select: [persona: any]
  remove: [username: string]
  save: [persona: any]
}>()

const { t } = useI18n()
</script>

<template>
  <div class="personas-grid" v-if="personas.length">
    <div
      v-for="(p, i) in personas"
      :key="p.user_id || i"
      class="persona persona--card"
      :class="{ 'persona--manual': p.is_manual }"
    >
      <button
        class="persona-body"
        type="button"
        @click="emit('select', p)"
      >
        <span class="persona-name">
          {{ p.name || p.username || 'agent_' + i }}
          <span
            v-if="p.username && p.name && p.username !== p.name"
            class="persona-handle"
          >@{{ p.username }}</span>
          <span v-if="p.is_manual" class="persona-tag">{{ t('step2.cardGrid.manual') }}</span>
        </span>
        <span class="persona-meta-row">
          <Badge
            v-if="p.review_status"
            :variant="statusVariant(p.review_status)"
            dot
          >{{ statusLabel(p.review_status) }}</Badge>
          <Badge
            v-if="getIssuesFor(p.username).length"
            :variant="issueBadgeVariant(highestSeverityFor(p.username))"
          >{{ t('step2.cardGrid.hintCount', { count: getIssuesFor(p.username).length }, getIssuesFor(p.username).length) }}</Badge>
        </span>
        <span class="persona-bio">{{ (p.bio || '').slice(0, 90) }}{{ (p.bio || '').length > 90 ? '…' : '' }}</span>
        <span v-if="p.interested_topics?.length" class="persona-topics">
          {{ p.interested_topics.slice(0, 3).join(' · ') }}
        </span>
      </button>
      <button
        class="persona-del"
        type="button"
        :title="t('step2.cardGrid.delete')"
        @click.stop="emit('remove', p.username)"
      >×</button>
      <button
        class="persona-save"
        type="button"
        :title="t('step2.cardGrid.save')"
        :disabled="savingPersonaKeys.has(profileKey(p))"
        @click.stop="emit('save', p)"
      >↧</button>
    </div>
  </div>
</template>

<style scoped>
.personas-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--s-3);
}
.persona {
  border: 1px solid var(--rule);
  background: var(--bg-elevated);
  padding: var(--s-3);
  border-radius: var(--r-1);
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  text-align: left;
  cursor: pointer;
  transition: background 150ms ease, border-color 150ms ease;
}
.persona:hover { background: var(--bg-panel-2); border-color: var(--rule-strong); }

.persona--card {
  position: relative;
  padding: 0;
  cursor: default;
}
.persona--manual { border-color: var(--accent); }
.persona-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-3);
  background: transparent;
  border: 0;
  text-align: left;
  color: inherit;
  cursor: pointer;
  width: 100%;
}
.persona-del,
.persona-save {
  position: absolute;
  top: 4px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1px solid var(--rule);
  background: transparent;
  color: var(--fg-muted);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.persona-del { right: 6px; }
.persona-save {
  right: 34px;
  font-size: 13px;
}
.persona-del:hover,
.persona-save:hover {
  background: var(--accent);
  color: var(--accent-ink);
  border-color: var(--accent);
}
.persona-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: var(--s-2) 0;
}
.persona-tag {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  font-size: 9px;
  border-radius: 999px;
  background: var(--accent);
  color: var(--accent-ink);
  letter-spacing: var(--ls-mono);
}
.persona-name {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.persona-bio {
  font-family: var(--ff-sans);
  font-size: var(--fs-16);
  line-height: 1.45;
  color: var(--fg);
}
.persona-topics {
  display: block;
  margin-top: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--accent);
}

/* Design v3 persona cards. */
.persona {
  background: var(--surface-elevated, var(--bg-elevated));
  border-color: var(--hairline, var(--rule));
  border-radius: var(--r-6, var(--r-1));
}
.persona:hover {
  background: var(--surface-hover, var(--bg-panel-2));
  border-color: var(--hairline-strong, var(--rule-strong));
}
.persona-name,
.persona-topics,
.persona-tag {
  font-family: var(--font-sans, var(--ff-sans));
  letter-spacing: 0;
  text-transform: none;
}
.persona-name {
  color: var(--text-secondary, var(--fg-muted));
  font-weight: 600;
}
.persona-bio {
  font-family: var(--font-sans, var(--ff-sans));
  color: var(--text-primary, var(--fg));
}
.persona-tag {
  background: var(--accent-tint-bg, var(--accent));
  color: var(--accent-tint-text, var(--accent-ink));
  font-weight: 600;
}
</style>
