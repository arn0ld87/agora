<script setup lang="ts">
/**
 * EmbeddingConfigurationsView — kanonische Embedding-Konfiguration.
 *
 * Slice 4.2 + 4.3.2. Zeigt fuer jede Konfiguration:
 *   - Status-Badge (proposed / probed / reembedding / validated / active /
 *     rolled_back / failed) — siehe EmbeddingConfigurationStatus
 *   - Modell + Dimension + Provider-Connection-Ref
 *   - Probe-Button (POST /test) und Activate-Button (POST /activate)
 *   - Migrations-Section: Start / Run / Cancel, Progress-Anzeige
 *   - Ollama-Download-Wizard (Modal): Modell-Name mit strikter
 *     Client-Validierung, der mit der Server-Validierung gespiegelt ist.
 *
 * Klartext-API-Keys verlassen dieses View NIE: der Provider-Connection-
 * Link referenziert nur die provider_connection_id; die Keys liegen im
 * Backend-Secret-Store.
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import Card from '@/components/v4/forms/Card.vue'
import Badge from '@/components/v4/forms/Badge.vue'
import { useEmbeddingConfigurationsStore } from '@/store/embeddingConfigurations'
import { listProviderConnections } from '@/api/providerConnections'
import type { ProviderConnection } from '@/contracts/aiProviderContract'
import type {
  EmbeddingConfiguration,
  EmbeddingMigrationJob,
  EmbeddingProviderKind,
} from '@/contracts/embeddingContract'

const { t } = useI18n()

const store = useEmbeddingConfigurationsStore()

const BREADCRUMBS = computed(() => [
  { label: t('common.settings'), to: { name: 'SettingsGeneral' } },
  { label: t('settings.v4.embedding.title', 'Embedding-Konfiguration') },
])

const STATUS_TONE: Record<string, 'gray' | 'green' | 'orange' | 'red' | 'blue' | 'teal'> = {
  proposed: 'gray',
  probed: 'blue',
  reembedding: 'orange',
  validated: 'orange',
  active: 'green',
  rolled_back: 'orange',
  failed: 'red',
}

const STATUS_LABEL_KEY: Record<string, string> = {
  proposed: 'embedding.status.proposed',
  probed: 'embedding.status.probed',
  reembedding: 'embedding.status.reembedding',
  validated: 'embedding.status.validated',
  active: 'embedding.status.active',
  rolled_back: 'embedding.status.rolled_back',
  failed: 'embedding.status.failed',
}

// Ollama-Download-Wizard (Modal)
interface OllamaPullDraft {
  model: string;
  configurationId: string | null;
  isPulling: boolean;
  lastError: string | null;
}

const ollamaDraft = reactive<OllamaPullDraft>({
  model: '',
  configurationId: null,
  isPulling: false,
  lastError: null,
});

const ollamaModalOpen = ref(false);

// Provider-Connections fuer das Anlege-Formular (Slice 4.4, Etappe 1/2).
const providerConnections = ref<ProviderConnection[]>([]);

// Anlege-Formular fuer eine neue Embedding-Konfiguration.
interface CreateConfigDraft {
  providerConnectionId: string;
  modelId: string;
  dimensions: string;
  isSubmitting: boolean;
  lastError: string | null;
}

const createConfigDraft = reactive<CreateConfigDraft>({
  providerConnectionId: '',
  modelId: '',
  dimensions: '',
  isSubmitting: false,
  lastError: null,
});

const createConfigModalOpen = ref(false);

function openCreateConfigModal(): void {
  createConfigDraft.providerConnectionId = providerConnections.value[0]?.id ?? '';
  createConfigDraft.modelId = '';
  createConfigDraft.dimensions = '';
  createConfigDraft.lastError = null;
  createConfigModalOpen.value = true;
}

async function submitCreateConfig(): Promise<void> {
  const connection = providerConnections.value.find(
    (c) => c.id === createConfigDraft.providerConnectionId,
  );
  if (!connection) {
    createConfigDraft.lastError = t('embedding.create.connectionRequired', 'Bitte eine Provider-Connection waehlen.');
    return;
  }
  if (!createConfigDraft.modelId) {
    createConfigDraft.lastError = t('embedding.create.modelRequired', 'Modell-Name ist erforderlich.');
    return;
  }
  const dimensions = Number(createConfigDraft.dimensions);
  if (!Number.isInteger(dimensions) || dimensions <= 0) {
    createConfigDraft.lastError = t('embedding.create.dimensionsInvalid', 'Dimension muss eine positive Ganzzahl sein.');
    return;
  }

  createConfigDraft.isSubmitting = true;
  createConfigDraft.lastError = null;
  try {
    const created = await store.upsertConfiguration('new', {
      provider_connection_id: connection.id,
      provider_kind: connection.provider_kind as EmbeddingProviderKind,
      model_id: createConfigDraft.modelId,
      dimensions,
      scope: 'global',
      project_id: null,
    });
    try {
      await store.testConfiguration(created.id);
    } catch {
      // Eine fehlgeschlagene Probe darf das Anlegen nicht abbrechen —
      // die Konfiguration bleibt sichtbar (Status "proposed"/"failed").
    }
    createConfigModalOpen.value = false;
  } catch (err) {
    createConfigDraft.lastError = errorMessage(err);
  } finally {
    createConfigDraft.isSubmitting = false;
  }
}

// Gemini-Finding (HIGH): die Helferfunktion ``migration``
// wurde pro Render-Zyklus 15 Mal pro Konfiguration aufgerufen. Das
// ist teuer und unnoetig — eine computed-Eigenschaft berechnet das
// Mapping einmal pro Store-Aenderung.
const configsWithMigrations = computed(() =>
  store.configurations.map((config) => ({
    config,
    migration: store.migrationByConfiguration[config.id] ?? null,
  })),
);

function openOllamaModal(): void {
  ollamaDraft.model = '';
  ollamaDraft.configurationId = null;
  ollamaDraft.lastError = null;
  ollamaModalOpen.value = true;
}

async function submitOllamaPull(): Promise<void> {
  if (!ollamaDraft.model) {
    ollamaDraft.lastError = t('embedding.ollama.modelRequired');
    return;
  }
  ollamaDraft.isPulling = true;
  ollamaDraft.lastError = null;
  try {
    await store.pullOllamaEmbeddingModel({
      model: ollamaDraft.model,
      configuration_id: ollamaDraft.configurationId ?? undefined,
    });
    ollamaModalOpen.value = false;
  } catch (err) {
    ollamaDraft.lastError = errorMessage(err);
  } finally {
    ollamaDraft.isPulling = false;
  }
}

const isOllama = (config: EmbeddingConfiguration): boolean =>
  config.provider_kind === 'ollama' || config.provider_kind === 'ollama_cloud';

onMounted(async () => {
  const [, , connectionsResp] = await Promise.all([
    store.loadConfigurations(),
    store.loadActiveConfiguration(),
    listProviderConnections(),
  ]);
  providerConnections.value = connectionsResp.items;
});

const progressPct = (job: EmbeddingMigrationJob): number => {
  if (job.progress.total <= 0) return 0;
  return Math.round(
    ((job.progress.processed + job.progress.failed) / job.progress.total) * 100,
  );
};

async function runTest(config: EmbeddingConfiguration): Promise<void> {
  // Gemini-Finding (MEDIUM): testConfiguration laedt die Liste
  // bereits automatisch neu.
  await store.testConfiguration(config.id);
}

async function runActivate(config: EmbeddingConfiguration): Promise<void> {
  await store.activateConfiguration(config.id);
}

async function runStartMigration(config: EmbeddingConfiguration): Promise<void> {
  // Gemini-Finding (MEDIUM): runMigration laedt active und Liste
  // automatisch neu.
  const job = await store.startMigration(config.id);
  await store.runMigration(job.id);
}

async function runCancelMigration(job: EmbeddingMigrationJob): Promise<void> {
  await store.cancelMigration(job.id);
}

function errorMessage(err: unknown): string {
  // Gemini-Finding (MEDIUM): Pydantic-/Zod-ValidationError haben ein
  // ``issues``-Array mit sprechenden Meldungen. Statt das rohe
  // JSON-String-Repraesentat anzuzeigen, geben wir die erste
  // Issue-Message zurueck.
  if (err && typeof err === 'object') {
    if ('issues' in err && Array.isArray((err as { issues?: unknown }).issues)) {
      const firstIssue = (err as { issues: Array<{ message?: unknown }> })
        .issues[0];
      if (firstIssue && typeof firstIssue === 'object' && 'message' in firstIssue) {
        return String(firstIssue.message);
      }
    }
    if ('message' in err) {
      return String((err as { message?: unknown }).message ?? err);
    }
  }
  return String(err);
}
</script>

<template>
  <AppShell>
    <PageHeader :breadcrumbs="BREADCRUMBS" :title="$t('settings.v4.embedding.title', 'Embedding-Konfiguration')">
      <button
        type="button"
        class="btn btn-primary"
        data-testid="open-create-config"
        @click="openCreateConfigModal"
      >
        {{ $t('embedding.create.open', 'Neue Konfiguration') }}
      </button>
      <button
        type="button"
        class="btn btn-secondary"
        data-testid="open-ollama-pull"
        @click="openOllamaModal"
      >
        {{ $t('embedding.ollama.download', 'Ollama-Modell herunterladen') }}
      </button>
    </PageHeader>

    <section class="grid gap-4">
      <Card
        v-if="store.configurationsError"
        tone="danger"
        :title="$t('embedding.list.error', 'Konfigurationen konnten nicht geladen werden')"
      >
        {{ store.configurationsError }}
      </Card>

      <Card
        v-if="store.activeConfiguration && !store.configurationsLoading"
        tone="success"
        :title="$t('embedding.active.title', 'Aktive Konfiguration')"
      >
        <p>
          <strong>{{ store.activeConfiguration.model_id }}</strong>
          ({{ store.activeConfiguration.dimensions }}d, {{ store.activeConfiguration.provider_kind }})
        </p>
        <p v-if="store.activeSource === 'legacy'" class="text-warn">
          {{ $t('embedding.active.legacyHint', 'Quelle: Legacy Config.EMBEDDING_* — bitte uebernehmen.') }}
        </p>
      </Card>

      <Card
        v-for="{ config, migration } in configsWithMigrations"
        :key="config.id"
        :title="`${config.model_id} (${config.dimensions}d)`"
      >
        <div class="config-row">
          <Badge :tone="STATUS_TONE[config.status] || 'neutral'">
            {{ $t(STATUS_LABEL_KEY[config.status] || 'embedding.status.unknown', config.status) }}
          </Badge>
          <span class="config-meta">
            {{ config.provider_kind }} ·
            scope={{ config.scope }}{{ config.project_id ? `:${config.project_id}` : '' }} ·
            index_version={{ config.index_version }}
          </span>
        </div>

        <p v-if="config.status_message" class="text-warn">
          {{ config.status_message }}
        </p>

        <div class="config-actions">
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="config.status === 'failed'"
            data-testid="probe-config"
            @click="runTest(config)"
          >
            {{ $t('embedding.action.test', 'Probe') }}
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="config.status !== 'probed' && config.status !== 'rolled_back'"
            data-testid="activate-config"
            @click="runActivate(config)"
          >
            {{ $t('embedding.action.activate', 'Aktivieren') }}
          </button>
        </div>

        <!-- Migrations-Section -->
        <div class="migration-section" v-if="config.status === 'probed' || migration">
          <h4>{{ $t('embedding.migration.title', 'Re-Embedding-Migration') }}</h4>
          <p v-if="!migration">
            {{ $t('embedding.migration.intro', 'Migration starten, um die Embedding-Dimension oder das Modell zu wechseln.') }}
          </p>
          <template v-else>
            <div class="migration-row">
              <span class="job-id">{{ migration!.id }}</span>
              <Badge :tone="STATUS_TONE[migration!.status] || 'neutral'">
                {{ $t(STATUS_LABEL_KEY[migration!.status] || 'embedding.status.unknown') }}
              </Badge>
            </div>
            <progress :value="progressPct(migration!)" max="100" />
            <p>
              {{ migration!.progress.processed }} / {{ migration!.progress.total }}
              ({{ migration!.progress.failed }} fehlgeschlagen)
            </p>
            <p v-if="migration!.error_message" class="text-warn">
              {{ migration!.error_message }}
            </p>
          </template>
          <div class="config-actions">
            <button
              v-if="!migration"
              type="button"
              class="btn btn-primary"
              data-testid="start-migration"
              @click="runStartMigration(config)"
            >
              {{ $t('embedding.migration.start', 'Migration starten') }}
            </button>
            <button
              v-if="migration && (migration!.status === 'pending' || migration!.status === 'running' || migration!.status === 'validating')"
              type="button"
              class="btn btn-secondary"
              data-testid="cancel-migration"
              @click="runCancelMigration(migration as EmbeddingMigrationJob)"
            >
              {{ $t('embedding.migration.cancel', 'Abbrechen') }}
            </button>
            <button
              v-if="isOllama(config)"
              type="button"
              class="btn btn-secondary"
              data-testid="open-ollama-pull-inline"
              @click="openOllamaModal"
            >
              {{ $t('embedding.ollama.downloadInline', 'Ollama-Modell hier herunterladen') }}
            </button>
          </div>
        </div>
      </Card>

      <p v-if="!store.configurationsLoading && store.configurations.length === 0">
        {{ $t('embedding.list.empty', 'Noch keine Embedding-Konfigurationen vorhanden.') }}
      </p>
    </section>

    <!-- Ollama-Download-Modal -->
    <div v-if="ollamaModalOpen" class="modal-backdrop" @click.self="ollamaModalOpen = false">
      <div class="modal" data-testid="ollama-pull-modal">
        <h3>{{ $t('embedding.ollama.title', 'Ollama-Modell herunterladen') }}</h3>
        <p class="text-muted">
          {{ $t('embedding.ollama.hint', 'Modell-Name muss ASCII a-z, A-Z, 0-9, -, _, ., : enthalten (max 100 Zeichen).') }}
        </p>
        <label>
          {{ $t('embedding.ollama.model', 'Modell-Name') }}
          <input
            v-model="ollamaDraft.model"
            type="text"
            data-testid="ollama-pull-model"
            placeholder="nomic-embed-text"
          />
        </label>
        <label>
          {{ $t('embedding.ollama.configurationId', 'Provider-Connection (optional)') }}
          <select v-model="ollamaDraft.configurationId" data-testid="ollama-pull-connection">
            <option :value="null">{{ $t('embedding.ollama.autoSelect', 'Auto (erste Ollama-Connection)') }}</option>
            <option v-for="{ config } in configsWithMigrations" :key="config.id" :value="config.provider_connection_id">
              {{ config.provider_connection_id }} ({{ config.provider_kind }})
            </option>
          </select>
        </label>
        <p v-if="ollamaDraft.lastError" class="text-warn">
          {{ ollamaDraft.lastError }}
        </p>
        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" @click="ollamaModalOpen = false">
            {{ $t('common.cancel', 'Abbrechen') }}
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="ollamaDraft.isPulling || !ollamaDraft.model"
            data-testid="ollama-pull-submit"
            @click="submitOllamaPull"
          >
            {{ $t('embedding.ollama.submit', 'Download starten') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Anlege-Modal fuer eine neue Embedding-Konfiguration -->
    <div v-if="createConfigModalOpen" class="modal-backdrop" @click.self="createConfigModalOpen = false">
      <div class="modal" data-testid="create-config-modal">
        <h3>{{ $t('embedding.create.title', 'Neue Embedding-Konfiguration') }}</h3>

        <template v-if="providerConnections.length === 0">
          <p class="text-warn">
            {{ $t('embedding.create.noConnections', 'Keine Provider-Connections vorhanden. Zuerst eine Verbindung anlegen.') }}
          </p>
          <router-link :to="{ name: 'SettingsLlmProviders' }" class="btn btn-secondary">
            {{ $t('embedding.create.toProviders', 'Zu den LLM-Anbietern') }}
          </router-link>
        </template>
        <template v-else>
          <label>
            {{ $t('embedding.create.connection', 'Provider-Connection') }}
            <select v-model="createConfigDraft.providerConnectionId" data-testid="create-config-connection">
              <option v-for="conn in providerConnections" :key="conn.id" :value="conn.id">
                {{ conn.display_name }}
              </option>
            </select>
          </label>
          <label>
            {{ $t('embedding.create.model', 'Modell-Name') }}
            <input
              v-model="createConfigDraft.modelId"
              type="text"
              data-testid="create-config-model"
              placeholder="nomic-embed-text"
            />
          </label>
          <label>
            {{ $t('embedding.create.dimensions', 'Dimension') }}
            <input
              v-model="createConfigDraft.dimensions"
              type="number"
              min="1"
              step="1"
              data-testid="create-config-dimensions"
            />
          </label>
          <p v-if="createConfigDraft.lastError" class="text-warn">
            {{ createConfigDraft.lastError }}
          </p>
          <div class="modal-actions">
            <button type="button" class="btn btn-secondary" @click="createConfigModalOpen = false">
              {{ $t('common.cancel', 'Abbrechen') }}
            </button>
            <button
              type="button"
              class="btn btn-primary"
              :disabled="createConfigDraft.isSubmitting"
              data-testid="create-config-submit"
              @click="submitCreateConfig"
            >
              {{ $t('embedding.create.submit', 'Konfiguration anlegen') }}
            </button>
          </div>
        </template>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.config-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}
.config-meta {
  color: var(--text-muted, #6b7280);
  font-size: 0.875rem;
}
.config-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
  flex-wrap: wrap;
}
.migration-section {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-default, #e5e7eb);
}
.migration-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.5rem 0;
}
.job-id {
  font-family: monospace;
  font-size: 0.875rem;
  color: var(--text-muted, #6b7280);
}
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.modal {
  background: var(--bg-elevated, #fff);
  border-radius: 0.5rem;
  padding: 1.5rem;
  width: min(32rem, 90vw);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.text-warn {
  color: var(--status-orange, #b25000);
}
.text-muted {
  color: var(--text-muted, #6b7280);
}
</style>
