<script setup lang="ts">
/**
 * PersonaLibraryPanel — Persona-Template-Bibliothek mit Refresh/Use/Delete.
 *
 * Sub-Slice 45 (Refs #203): Isoliert die Library-Section aus Step2EnvSetup.vue.
 *
 * Pure UI-Komponente. State und Actions kommen aus Eltern (`usePersonaLibrary`).
 */
import { useI18n } from 'vue-i18n'

interface Template {
  template_id: string
  username?: string
  name?: string
  bio?: string
  persona?: string
}

interface Props {
  templates: Template[]
  loading: boolean
  error: string
  usingIds: Set<string>
}

const props = defineProps<Props>()

const emit = defineEmits<{
  refresh: []
  use: [template: Template]
  remove: [templateId: string]
}>()

const { t } = useI18n()

function templateBio(template: Template): string {
  const text = template.bio || template.persona || ''
  return text.length > 120 ? text.slice(0, 120) + '…' : text
}
</script>

<template>
  <section class="persona-library">
    <header class="persona-library-head">
      <div>
        <span class="kicker-mono">{{ t('step2.library.title') }}</span>
        <p class="meta">{{ t('step2.library.hint') }}</p>
      </div>
      <button
        class="persona-more-btn"
        type="button"
        :disabled="loading"
        @click="emit('refresh')"
      >
        {{ t('step2.library.refresh') }}
      </button>
    </header>
    <p v-if="error" class="meta">{{ error }}</p>
    <div v-if="templates.length" class="persona-library-list">
      <article
        v-for="template in templates"
        :key="template.template_id"
        class="persona-template"
      >
        <div>
          <strong>{{ template.name || template.username }}</strong>
          <span v-if="template.username" class="persona-handle">@{{ template.username }}</span>
          <p>{{ templateBio(template) }}</p>
        </div>
        <div class="persona-template-actions">
          <button
            type="button"
            :disabled="usingIds.has(template.template_id)"
            @click="emit('use', template)"
          >
            {{ t('step2.library.use') }}
          </button>
          <button type="button" @click="emit('remove', template.template_id)">×</button>
        </div>
      </article>
    </div>
    <p v-else class="meta">{{ t('step2.library.empty') }}</p>
  </section>
</template>

<style scoped>
.persona-library {
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.persona-library-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-3);
}
.persona-library-list {
  display: grid;
  gap: var(--s-2);
}
.persona-template {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--s-3);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  padding: var(--s-3);
  background: var(--bg-elevated);
}
.persona-template strong {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
}
.persona-template p {
  margin: var(--s-1) 0 0;
  color: var(--fg-body);
}
.persona-template-actions {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}
.persona-template-actions button {
  border: 1px solid var(--rule);
  background: transparent;
  color: var(--fg);
  border-radius: var(--r-1);
  padding: 6px 8px;
  cursor: pointer;
}
.persona-template-actions button:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.persona-more-btn {
  background: transparent;
  border: 1px dashed var(--rule-strong);
  border-radius: var(--r-1);
  padding: var(--s-3);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  cursor: pointer;
  transition: border-color 150ms ease, color 150ms ease;
}
.persona-more-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
}
.persona-handle {
  font-family: var(--ff-mono);
  font-size: 11px;
  color: var(--fg-muted);
  margin-left: var(--s-1);
}
.kicker-mono {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: var(--s-2);
}
.meta {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}

/* Design v3 library list polish. */
.persona-more-btn,
.persona-handle,
.kicker-mono,
.meta {
  font-family: var(--font-sans, var(--ff-sans));
  letter-spacing: 0;
  text-transform: none;
}
.persona-more-btn {
  border-style: solid;
  border-color: var(--hairline, var(--rule-strong));
  border-radius: var(--r-5, var(--r-1));
  background: var(--surface-elevated, transparent);
}
.persona-more-btn:hover,
.persona-template-actions button:hover {
  background: var(--surface-hover, transparent);
}
.persona-handle,
.meta {
  color: var(--text-secondary, var(--fg-muted));
}
</style>
