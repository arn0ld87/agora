---
description: "Zwei Frontend-Bugfixes: (1) Pflicht-Prompt-Feld in HeroNewRun, (2) LLM-Provider-Settings sichtbar und nutzbar machen."
agent: agora-frontend-worker
---

# fix-mai-17: Dashboard-Prompt-Pflichtfeld + LLM-Provider-Settings

Du bist `agora-frontend-worker`. Führe beide Fixes vollständig durch.
Worktree: `/private/tmp/agora-mai-17/` (anlegen wie unten beschrieben).
**KEIN push, KEIN `gh pr create`** — Branch lokal fertigstellen, dann dem Lead-Claude melden.

## Kontext

Slice MAI-17 fixiert zwei zusammenhängende Frontend-Bugs im v4-Design-Branch.
- `main` ist Base, Design-v4-Komponenten unter `frontend/src/components/v4/` und `frontend/src/views/v4/`
- `SettingsSectionPanel` ist die generische Settings-UI-Schicht, die über `ALLOWED_SECTIONS` gesteuert wird
- i18n: `frontend/src/i18n/locales/de.json` und `en.json`

## Setup

```bash
git worktree add -b feat/mai-17-dashboard-prompt-llm-settings \
  /private/tmp/agora-mai-17 origin/main
cd /private/tmp/agora-mai-17
ln -sfn /Volumes/T7/Projekte/agora/frontend/node_modules \
  /private/tmp/agora-mai-17/frontend/node_modules
```

---

## Fix A: `HeroNewRun.vue` — Pflicht-Prompt-Feld

### Diagnose

- Datei: `frontend/src/components/v4/dashboard/HeroNewRun.vue`
- `canSubmit` (Zeile ~86): `files.value.length > 0 && !loadingStatus.value`
  → `simulationRequirement` wird nie geprüft
- `startSimulation()` (Zeile ~181): `setPendingUpload(files.value, '')` → immer leer
- `setPendingUpload` Signatur: `(files: File[], requirement: string)`
- Store: `frontend/src/store/pendingUpload.ts` — `simulationRequirement` ist der korrekte Feldname

### Änderungen

**`HeroNewRun.vue` — Script:**

```diff
-const canSubmit = computed(() => files.value.length > 0 && !loadingStatus.value)
+const simulationRequirement = ref('')
+const canSubmit = computed(
+  () => files.value.length > 0 && simulationRequirement.value.trim() !== '' && !loadingStatus.value,
+)
```

```diff
-setPendingUpload(files.value, '')
+setPendingUpload(files.value, simulationRequirement.value.trim())
```

**`HeroNewRun.vue` — Template (Zone 2, nach `hero-lang`-Feld):**

Ergänze in `<div class="hero-zone hero-config">` ein drittes Feld direkt nach dem Sprach-Feld:

```html
<div class="hero-field hero-field--full">
  <label class="hero-label" for="hero-requirement">
    {{ $t('dashboard.hero.requirementLabel') }}
    <span class="hero-required">*</span>
  </label>
  <textarea
    id="hero-requirement"
    v-model="simulationRequirement"
    class="hero-textarea"
    :placeholder="$t('dashboard.hero.requirementPlaceholder')"
    rows="3"
  />
</div>
```

**`HeroNewRun.vue` — Style (neu am Ende von `<style scoped>`):**

```css
.hero-field--full {
  grid-column: 1 / -1;
}

.hero-required {
  color: var(--status-red, #c0392b);
  margin-left: 2px;
}

.hero-textarea {
  font-family: var(--font-sans);
  font-size: 14px;
  padding: 9px 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-elevated, #fff);
  color: var(--text-primary);
  resize: vertical;
  min-height: 72px;
  line-height: 1.5;
}

.hero-textarea:hover {
  border-color: var(--hairline-strong);
}

.hero-textarea:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring);
}
```

**`disabledHint` i18n-Key updaten:**

`de.json`: `"disabledHint": "Erst Datei und Fragestellung eingeben, dann starten."`
`en.json`: `"disabledHint": "Select a file and enter a requirement first."`

**Neue i18n-Keys in `de.json` und `en.json`:**

```json
"requirementLabel": "Fragestellung / Anforderung",
"requirementPlaceholder": "z. B. „Welche politischen Reaktionen sind in der DACH-Region zu erwarten?""
```

```json
"requirementLabel": "Research question / requirement",
"requirementPlaceholder": "e.g. "What political reactions are expected in the DACH region?""
```

### Tests — `HeroNewRun.spec.ts`

Bestehenden Test `'aktiviert CTA nach Datei-Upload und navigiert zu /process/new'` **anpassen**:
Der CTA darf nach reinem Datei-Upload nicht mehr aktiv sein — erst wenn auch Requirement gesetzt.

```typescript
it('CTA bleibt deaktiviert mit Datei aber ohne Requirement', async () => {
  const router = makeRouter()
  await router.push('/dashboard')
  const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
  await flushPromises()

  const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
  const input = w.find<HTMLInputElement>('input[type=file]')
  Object.defineProperty(input.element, 'files', { value: [file] })
  await input.trigger('change')
  await flushPromises()

  const btn = w.find('.hero-cta')
  expect(btn.attributes('disabled')).toBeDefined()
})

it('aktiviert CTA und startet nach Datei + Requirement', async () => {
  const router = makeRouter()
  await router.push('/dashboard')
  const pushSpy = vi.spyOn(router, 'push')
  const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
  await flushPromises()

  const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
  const input = w.find<HTMLInputElement>('input[type=file]')
  Object.defineProperty(input.element, 'files', { value: [file] })
  await input.trigger('change')
  await flushPromises()

  const textarea = w.find<HTMLTextAreaElement>('textarea#hero-requirement')
  await textarea.setValue('Wie reagiert die DACH-Region?')
  await flushPromises()

  const btn = w.find('.hero-cta')
  expect(btn.attributes('disabled')).toBeUndefined()
  await btn.trigger('click')
  await flushPromises()

  expect(setPendingUpload).toHaveBeenCalledWith(
    [file],
    'Wie reagiert die DACH-Region?',
  )
  expect(pushSpy).toHaveBeenCalledWith({ name: 'Process', params: { projectId: 'new' } })
})
```

Den alten Test `'aktiviert CTA nach Datei-Upload und navigiert zu /process/new'` **entfernen** oder durch die beiden neuen Tests ersetzen.

---

## Fix B: LLM-Provider-Settings — Provider-Auswahl und Key-Konfiguration

### Diagnose

- `SettingsGeneralView.vue` zeigt `ALLOWED_SECTIONS = ['llm', ...]` — die Sektion ist da, aber
  `SettingsSectionPanel` rendert sie als generische Formular-Felder ohne Provider-Kontext.
- Das Backend hat nur ein einzelnes `LLM_*`-Set (ein Provider zur Zeit), kein Multi-Provider-Konzept.
- Der User möchte: Provider wählen (Ollama / OpenAI / Gemini / Anthropic / Custom),
  danach die passenden Felder sehen (API Key, Base URL, Modell).

### Lösung: Neue Komponente `LlmProviderCard.vue`

Erstelle `frontend/src/components/v4/forms/LlmProviderCard.vue`.

Diese Komponente rendert über der generischen `SettingsSectionPanel`-Sektion eine
"Schnellauswahl"-Karte, die `LLM_BASE_URL` und `LLM_API_KEY` aus dem Settings-Store
liest/schreibt und dem User eine klare Provider-Vorauswahl bietet.

**Provider-Presets** (hardcoded, über `LLM_BASE_URL` gesteuert):

| Label | `LLM_BASE_URL` | API-Key nötig? |
|---|---|---|
| Ollama (lokal) | `http://localhost:11434/v1` | Nein |
| OpenAI | `https://api.openai.com/v1` | Ja |
| Gemini (OpenAI-compat.) | `https://generativelanguage.googleapis.com/v1beta/openai` | Ja |
| Anthropic (OpenAI-compat.) | `https://api.anthropic.com/v1` | Ja |
| Custom | (manuell) | Optional |

Die Komponente:
1. Liest aktuellen `LLM_BASE_URL`-Wert aus dem Settings-Store (`useSettingsStore`)
2. Zeigt Preset-Buttons (Radio-Style) — aktiver Preset = der dessen URL dem gespeicherten `LLM_BASE_URL` entspricht, sonst "Custom"
3. Bei Klick auf Preset → schreibt `LLM_BASE_URL` ins Store-Draft via `store.draft['LLM_BASE_URL'] = preset.url`
4. Zeigt "API Key"-Input wenn `apiKeyRequired` des gewählten Presets `true`
5. Zeigt "Base URL"-Input immer (vorbelegt mit Preset-URL, bei Custom editierbar)
6. Zeigt "Modell"-Input (spiegelt `LLM_MODEL_NAME`)
7. "Speichern"-Button → `store.save()` (existierende Store-Methode)

**Bindet sich in `SettingsGeneralView.vue` ein:**

Ergänze über `<SettingsSectionPanel>` die neue Karte:

```vue
<LlmProviderCard style="margin-bottom: 16px;" />
<SettingsSectionPanel :allowed-sections="ALLOWED_SECTIONS" />
```

**Datei-Scope:**
- Neu: `frontend/src/components/v4/forms/LlmProviderCard.vue` (≤ 250 LOC)
- Geändert: `frontend/src/views/Settings/SettingsGeneralView.vue` (+3 Zeilen)
- i18n: `settings.v4.llmProvider.*`-Keys in `de.json` und `en.json`

**i18n-Keys de.json:**
```json
"llmProvider": {
  "title": "LLM-Anbieter",
  "subtitle": "Wähle einen Anbieter und hinterlege API-Key und Modell.",
  "presetLabel": "Anbieter",
  "baseUrlLabel": "Base URL",
  "apiKeyLabel": "API Key",
  "modelLabel": "Modell",
  "saveBtn": "Speichern",
  "savedHint": "Gespeichert.",
  "presets": {
    "ollama": "Ollama (lokal)",
    "openai": "OpenAI",
    "gemini": "Gemini",
    "anthropic": "Anthropic",
    "custom": "Eigener Endpunkt"
  }
}
```

**`LlmProviderCard.vue` Grundstruktur (Referenz):**

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Card from './Card.vue'
import { useSettingsStore } from '@/store/settings'

const { t } = useI18n()
const store = useSettingsStore()

const PRESETS = [
  { key: 'ollama',     label: t('settings.v4.llmProvider.presets.ollama'),     url: 'http://localhost:11434/v1', needsKey: false },
  { key: 'openai',     label: t('settings.v4.llmProvider.presets.openai'),     url: 'https://api.openai.com/v1', needsKey: true },
  { key: 'gemini',     label: t('settings.v4.llmProvider.presets.gemini'),     url: 'https://generativelanguage.googleapis.com/v1beta/openai', needsKey: true },
  { key: 'anthropic',  label: t('settings.v4.llmProvider.presets.anthropic'),  url: 'https://api.anthropic.com/v1', needsKey: true },
  { key: 'custom',     label: t('settings.v4.llmProvider.presets.custom'),     url: '', needsKey: false },
] as const

const savedUrl = computed(() => (store.draft['LLM_BASE_URL'] as string) ?? '')
const activePreset = computed(
  () => PRESETS.find(p => p.url && p.url === savedUrl.value) ?? PRESETS[4],
)
const baseUrl    = computed({ get: () => savedUrl.value, set: v => { store.draft['LLM_BASE_URL'] = v } })
const apiKey     = computed({ get: () => (store.draft['LLM_API_KEY'] as string) ?? '', set: v => { store.draft['LLM_API_KEY'] = v } })
const modelName  = computed({ get: () => (store.draft['LLM_MODEL_NAME'] as string) ?? '', set: v => { store.draft['LLM_MODEL_NAME'] = v } })

const saving = ref(false)
const savedHint = ref(false)

function selectPreset(preset: typeof PRESETS[number]): void {
  store.draft['LLM_BASE_URL'] = preset.url
  if (!preset.needsKey) store.draft['LLM_API_KEY'] = ''
}

async function save(): Promise<void> {
  saving.value = true
  savedHint.value = false
  try {
    await store.save()
    savedHint.value = true
    setTimeout(() => { savedHint.value = false }, 2500)
  } finally {
    saving.value = false
  }
}
</script>
```

### Tests — `LlmProviderCard.spec.ts`

Erstelle `frontend/src/components/v4/forms/__tests__/LlmProviderCard.spec.ts`:

- Preset-Buttons rendern
- Klick auf "OpenAI" → `store.draft['LLM_BASE_URL']` = OpenAI-URL, API-Key-Input sichtbar
- Klick auf "Ollama" → `store.draft['LLM_API_KEY']` = `''`, API-Key-Input nicht sichtbar
- "Speichern" ruft `store.save()` auf
- "Gespeichert."-Hint erscheint nach erfolgreicher Speicherung

---

## Verifikation (Pflicht vor Rückmeldung)

```bash
cd /private/tmp/agora-mai-17/frontend
npm run typecheck && npm test -- --run && npm run build && npm run lint
```

Alle Checks müssen grün sein.

## Rückmeldungs-Format

```
Branch: feat/mai-17-dashboard-prompt-llm-settings
Letzter Commit: <hash>
Test-Delta: +N Tests (alle grün)
Build-Delta: <Bundle-Größe vorher → nachher>
Gaps: <falls vorhanden>
```
