/**
 * embeddingConfigurations Store — Vitest-Specs fuer sync-legacy und
 * Probe-Ergebnis-Tracking (Issue #1193).
 *
 * Deckt gezielt die neuen Anteile ab: `syncLegacy()` ruft die API und
 * laedt Liste + Active-Konfiguration neu; `testConfiguration()`
 * befuellt zusaetzlich `probeByConfiguration`. Bestehendes Store-
 * Verhalten (Slice 4.2/4.3) wird hier nicht erneut getestet.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("../../api/embeddingConfigurations", () => ({
  listEmbeddingConfigurations: vi.fn(),
  getActiveEmbeddingConfiguration: vi.fn(),
  upsertEmbeddingConfiguration: vi.fn(),
  deleteEmbeddingConfiguration: vi.fn(),
  testEmbeddingConfiguration: vi.fn(),
  activateEmbeddingConfiguration: vi.fn(),
  syncLegacyEmbeddingConfiguration: vi.fn(),
  listEmbeddingIndexVersions: vi.fn(),
}));
vi.mock("../../api/embeddingMigrations", () => ({
  startEmbeddingMigration: vi.fn(),
  runEmbeddingMigration: vi.fn(),
  cancelEmbeddingMigration: vi.fn(),
  pullOllamaEmbeddingModel: vi.fn(),
}));

import * as api from "../../api/embeddingConfigurations";
import * as migrationApi from "../../api/embeddingMigrations";
import { useEmbeddingConfigurationsStore } from "../embeddingConfigurations";
import type {
  EmbeddingConfiguration,
  EmbeddingIndexVersion,
  EmbeddingMigrationJob,
} from "../../contracts/embeddingContract";

type MockFn = ReturnType<typeof vi.fn>;
const mock = (fn: unknown): MockFn => fn as unknown as MockFn;

function makeConfiguration(
  overrides: Partial<EmbeddingConfiguration> = {},
): EmbeddingConfiguration {
  return {
    id: "cfg-1",
    provider_connection_id: "ollama",
    provider_kind: "ollama",
    model_id: "nomic-embed-text",
    dimensions: 768,
    scope: "global",
    project_id: null,
    index_version: 1,
    status: "proposed",
    status_message: null,
    created_at: "2026-08-10T10:00:00+00:00",
    updated_at: "2026-08-10T10:00:00+00:00",
    last_validated_at: null,
    ...overrides,
  } as EmbeddingConfiguration;
}

function makeIndexVersion(
  overrides: Partial<EmbeddingIndexVersion> = {},
): EmbeddingIndexVersion {
  return {
    version: 1,
    provider_connection_id: "ollama",
    model_id: "nomic-embed-text",
    dimensions: 768,
    index_name: "entity_embedding_v1",
    property_key: "embedding_v1",
    status: "active",
    created_at: "2026-08-10T10:00:00+00:00",
    retired_at: null,
    ...overrides,
  } as EmbeddingIndexVersion;
}

function makeMigrationJob(
  overrides: Partial<EmbeddingMigrationJob> = {},
): EmbeddingMigrationJob {
  return {
    id: "job-1",
    configuration_id: "cfg-1",
    source_index_version: 1,
    target_index_version: 2,
    status: "pending",
    progress: { total: 0, processed: 0, failed: 0, last_processed_id: null, phase: "entity", started_at: null, finished_at: null },
    error_message: null,
    created_at: "2026-09-22T08:00:00+00:00",
    updated_at: "2026-09-22T08:00:00+00:00",
    ...overrides,
  } as EmbeddingMigrationJob;
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
});

describe("embeddingConfigurations store — syncLegacy()", () => {
  it("ruft die API mit der Provider-Connection-ID und laedt Liste + Active neu", async () => {
    const synced = makeConfiguration({ id: "cfg-synced" });
    mock(api.syncLegacyEmbeddingConfiguration).mockResolvedValue(synced);
    mock(api.listEmbeddingConfigurations).mockResolvedValue({
      configurations: [synced],
    });
    mock(api.getActiveEmbeddingConfiguration).mockResolvedValue({
      configuration: null,
      source: "none",
    });

    const store = useEmbeddingConfigurationsStore();
    const result = await store.syncLegacy("ollama");

    expect(api.syncLegacyEmbeddingConfiguration).toHaveBeenCalledWith("ollama");
    expect(result).toEqual(synced);
    expect(api.listEmbeddingConfigurations).toHaveBeenCalled();
    expect(api.getActiveEmbeddingConfiguration).toHaveBeenCalled();
    expect(store.configurations).toEqual([synced]);
  });

  it("propagiert Fehler der API, ohne den Store in einen inkonsistenten Zustand zu bringen", async () => {
    const err = Object.assign(new Error("no_legacy_config"), {
      code: "no_legacy_config",
    });
    mock(api.syncLegacyEmbeddingConfiguration).mockRejectedValue(err);

    const store = useEmbeddingConfigurationsStore();
    await expect(store.syncLegacy("ollama")).rejects.toThrow("no_legacy_config");
    expect(api.listEmbeddingConfigurations).not.toHaveBeenCalled();
  });
});

describe("embeddingConfigurations store — testConfiguration() Probe-Tracking", () => {
  it("befuellt probeByConfiguration mit dem Probe-Ergebnis unter der configuration-ID", async () => {
    const configuration = makeConfiguration({ id: "cfg-probed", status: "probed" });
    const probe = {
      status: "available" as const,
      status_message: null,
      actual_dimensions: 768,
    };
    mock(api.testEmbeddingConfiguration).mockResolvedValue({ configuration, probe });
    mock(api.listEmbeddingConfigurations).mockResolvedValue({
      configurations: [configuration],
    });

    const store = useEmbeddingConfigurationsStore();
    const result = await store.testConfiguration("cfg-probed");

    expect(result.probe).toEqual(probe);
    expect(store.probeByConfiguration["cfg-probed"]).toEqual(probe);
  });
});

describe("embeddingConfigurations store — Index-Versionen (f006, embedding-ssot)", () => {
  it("loadIndexVersions() befuellt indexVersions aus der API", async () => {
    const versions = [
      makeIndexVersion({ version: 2, status: "building", model_id: "mxbai-embed-large" }),
      makeIndexVersion({ version: 1, status: "active" }),
    ];
    mock(api.listEmbeddingIndexVersions).mockResolvedValue(versions);

    const store = useEmbeddingConfigurationsStore();
    await store.loadIndexVersions();

    expect(store.indexVersions).toEqual(versions);
    expect(store.indexVersionsError).toBeNull();
  });

  it("loadIndexVersions() setzt indexVersionsError bei einem Fehler, statt zu werfen", async () => {
    mock(api.listEmbeddingIndexVersions).mockRejectedValue(new Error("boom"));

    const store = useEmbeddingConfigurationsStore();
    await store.loadIndexVersions();

    expect(store.indexVersionsError).toContain("boom");
    expect(store.indexVersions).toEqual([]);
  });

  it("activeIndexVersion liefert die Version mit status=active", async () => {
    mock(api.listEmbeddingIndexVersions).mockResolvedValue([
      makeIndexVersion({ version: 2, status: "building" }),
      makeIndexVersion({ version: 1, status: "active" }),
    ]);
    const store = useEmbeddingConfigurationsStore();
    await store.loadIndexVersions();

    expect(store.activeIndexVersion?.version).toBe(1);
    expect(store.buildingIndexVersion?.version).toBe(2);
  });

  it("activeIndexVersion ist null ohne jede aufgezeichnete Version (Legacy-Betrieb)", () => {
    const store = useEmbeddingConfigurationsStore();
    expect(store.activeIndexVersion).toBeNull();
    expect(store.buildingIndexVersion).toBeNull();
  });

  it("startMigration() laedt die Indexversionen neu, damit die neue building-Version sofort sichtbar ist", async () => {
    const job = makeMigrationJob({ status: "pending" });
    mock(migrationApi.startEmbeddingMigration).mockResolvedValue(job);
    mock(api.listEmbeddingIndexVersions).mockResolvedValue([
      makeIndexVersion({ version: 2, status: "building" }),
      makeIndexVersion({ version: 1, status: "active" }),
    ]);

    const store = useEmbeddingConfigurationsStore();
    await store.startMigration("cfg-1");

    expect(api.listEmbeddingIndexVersions).toHaveBeenCalled();
    expect(store.buildingIndexVersion?.status).toBe("building");
  });

  it("cancelMigration() laedt die Indexversionen neu, damit der Rollback sichtbar wird", async () => {
    const job = makeMigrationJob({ status: "rolled_back" });
    mock(migrationApi.cancelEmbeddingMigration).mockResolvedValue(job);
    mock(api.listEmbeddingIndexVersions).mockResolvedValue([
      makeIndexVersion({ version: 1, status: "active" }),
    ]);

    const store = useEmbeddingConfigurationsStore();
    await store.cancelMigration("job-1");

    expect(api.listEmbeddingIndexVersions).toHaveBeenCalled();
    expect(store.activeIndexVersion?.version).toBe(1);
    expect(store.buildingIndexVersion).toBeNull();
  });
});
