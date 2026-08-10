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
}));
vi.mock("../../api/embeddingMigrations", () => ({
  startEmbeddingMigration: vi.fn(),
  runEmbeddingMigration: vi.fn(),
  cancelEmbeddingMigration: vi.fn(),
  pullOllamaEmbeddingModel: vi.fn(),
}));

import * as api from "../../api/embeddingConfigurations";
import { useEmbeddingConfigurationsStore } from "../embeddingConfigurations";
import type { EmbeddingConfiguration } from "../../contracts/embeddingContract";

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
