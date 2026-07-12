/**
 * Pinia-Store fuer Embedding-Konfigurationen (Slice 4.2 + 4.3.2).
 *
 * Speichert die kanonischen Konfigurationen, den aktiven Migrations-
 * Job pro Konfiguration (read-only mirror) und den Pinia-Status.
 *
 * Konvention: das Store liest die aktive Konfiguration ueber die
 * ``/active``-Route (mit ``source: "store" | "legacy" | "none"``) und
 * faellt nur dann auf Legacy zurueck, wenn der Server explizit
 * ``"source": "legacy"`` meldet. Aufrufer muessen das in der UI
 * sichtbar machen.
 */
import { defineStore } from "pinia";
import * as api from "@/api/embeddingConfigurations";
import * as migrationApi from "@/api/embeddingMigrations";
import type {
  EmbeddingConfiguration,
  EmbeddingConfigurationScope,
  EmbeddingMigrationJob,
  EmbeddingProviderKind,
  OllamaPullReport,
} from "@/contracts/embeddingContract";

interface EmbeddingConfigurationsState {
  configurations: EmbeddingConfiguration[];
  configurationsLoading: boolean;
  configurationsError: string | null;

  activeConfiguration: EmbeddingConfiguration | null;
  activeSource: "store" | "legacy" | "none";
  activeLoading: boolean;
  activeError: string | null;

  /**
   * Read-only mirror des aktuellen Migrations-Jobs pro
   * Konfiguration. Nicht persistent — wird bei jedem
   * ``loadActiveConfiguration()`` neu geladen.
   */
  migrationByConfiguration: Record<string, EmbeddingMigrationJob | null>;

  /**
   * Laufzeit-Cache fuer den zuletzt aufgetretenen Ollama-Pull-Report.
   * Wird vom Ollama-Download-Wizard geschrieben, von der View gelesen.
   */
  lastOllamaPull: OllamaPullReport | null;
}

export const useEmbeddingConfigurationsStore = defineStore(
  "embeddingConfigurations",
  {
    state: (): EmbeddingConfigurationsState => ({
      configurations: [],
      configurationsLoading: false,
      configurationsError: null,
      activeConfiguration: null,
      activeSource: "none",
      activeLoading: false,
      activeError: null,
      migrationByConfiguration: {},
      lastOllamaPull: null,
    }),

    getters: {
      activeGlobalConfiguration(state): EmbeddingConfiguration | null {
        if (!state.activeConfiguration) return null;
        if (state.activeConfiguration.scope !== "global") return null;
        return state.activeConfiguration;
      },
      hasActiveConfiguration(state): boolean {
        return state.activeConfiguration !== null;
      },
    },

    actions: {
      async loadConfigurations(
        scope?: EmbeddingConfigurationScope,
      ): Promise<void> {
        this.configurationsLoading = true;
        this.configurationsError = null;
        try {
          const resp = await api.listEmbeddingConfigurations(scope);
          this.configurations = resp.configurations;
        } catch (err) {
          this.configurationsError = errorMessage(err);
        } finally {
          this.configurationsLoading = false;
        }
      },

      async loadActiveConfiguration(): Promise<void> {
        this.activeLoading = true;
        this.activeError = null;
        try {
          const resp = await api.getActiveEmbeddingConfiguration();
          this.activeConfiguration = resp.configuration;
          this.activeSource = resp.source;
        } catch (err) {
          this.activeError = errorMessage(err);
        } finally {
          this.activeLoading = false;
        }
      },

      async upsertConfiguration(
        configurationId: "new" | string,
        payload: {
          provider_connection_id: string;
          provider_kind: EmbeddingProviderKind;
          model_id: string;
          dimensions: number;
          scope: EmbeddingConfigurationScope;
          project_id: string | null;
        },
      ): Promise<EmbeddingConfiguration> {
        const created = await api.upsertEmbeddingConfiguration(
          configurationId,
          payload,
        );
        await this.loadConfigurations();
        return created;
      },

      async deleteConfiguration(configurationId: string): Promise<void> {
        await api.deleteEmbeddingConfiguration(configurationId);
        await this.loadConfigurations();
        if (this.activeConfiguration?.id === configurationId) {
          this.activeConfiguration = null;
          this.activeSource = "none";
        }
      },

      async testConfiguration(
        configurationId: string,
      ): Promise<{
        configuration: EmbeddingConfiguration;
        probe: {
          status:
            | "available"
            | "unavailable"
            | "invalid_credentials"
            | "degraded"
            | "unsupported";
          status_message: string | null;
          actual_dimensions: number | null;
        };
      }> {
        return await api.testEmbeddingConfiguration(configurationId);
      },

      async activateConfiguration(
        configurationId: string,
      ): Promise<EmbeddingConfiguration> {
        const activated = await api.activateEmbeddingConfiguration(
          configurationId,
        );
        await this.loadActiveConfiguration();
        return activated;
      },

      // ----------------------------------------------------------------
      // Migrations (Slice 4.3)
      // ----------------------------------------------------------------

      async startMigration(
        configurationId: string,
      ): Promise<EmbeddingMigrationJob> {
        const job = await migrationApi.startEmbeddingMigration({
          configuration_id: configurationId,
        });
        this.migrationByConfiguration[configurationId] = job;
        return job;
      },

      async runMigration(jobId: string): Promise<EmbeddingMigrationJob> {
        const job = await migrationApi.runEmbeddingMigration(jobId);
        const configId = job.configuration_id;
        this.migrationByConfiguration[configId] = job;
        return job;
      },

      async cancelMigration(jobId: string): Promise<EmbeddingMigrationJob> {
        const job = await migrationApi.cancelEmbeddingMigration(jobId);
        const configId = job.configuration_id;
        this.migrationByConfiguration[configId] = job;
        return job;
      },

      async pullOllamaEmbeddingModel(
        payload: { model: string; configuration_id?: string },
      ): Promise<OllamaPullReport> {
        const report = await migrationApi.pullOllamaEmbeddingModel(payload);
        this.lastOllamaPull = report;
        return report;
      },
    },
  },
);

function errorMessage(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message?: unknown }).message ?? err);
  }
  return String(err);
}
