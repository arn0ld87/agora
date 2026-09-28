import { beforeEach, describe, expect, it, vi } from "vitest";

const serviceMock = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("../index", () => ({
  default: serviceMock,
}));

import { syncLegacyEmbeddingConfiguration } from "../embeddingConfigurations";
import { ApiError } from "../envelope";

const PROPOSED_CONFIGURATION = {
  id: "cfg-legacy-sync",
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
};

describe("embeddingConfigurations api client — sync-legacy", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("syncLegacyEmbeddingConfiguration sendet POST mit provider_connection_id und parst outcome='created'", async () => {
    serviceMock.post.mockResolvedValueOnce({
      success: true,
      data: {
        outcome: "created",
        configuration: PROPOSED_CONFIGURATION,
        active_configuration: null,
        legacy: null,
      },
    });

    const result = await syncLegacyEmbeddingConfiguration("ollama");

    expect(serviceMock.post).toHaveBeenCalledWith(
      "/api/llm/embedding/configurations/sync-legacy",
      { provider_connection_id: "ollama" },
    );
    expect(result.outcome).toBe("created");
    expect(result.configuration).toMatchObject({ id: "cfg-legacy-sync", status: "proposed" });
  });

  it("syncLegacyEmbeddingConfiguration wirft strukturiert bei Schema-Drift statt tolerant weiterzurendern", async () => {
    serviceMock.post.mockResolvedValueOnce({
      success: true,
      // status fehlt -> muss an der Response-Grenze scheitern.
      data: {
        outcome: "created",
        configuration: { ...PROPOSED_CONFIGURATION, status: undefined },
        active_configuration: null,
        legacy: null,
      },
    });

    await expect(syncLegacyEmbeddingConfiguration("ollama")).rejects.toThrow(
      /schema mismatch/,
    );
  });

  // #1417: ein 409 mit code="embedding_legacy_conflict" wird nicht als
  // Exception durchgereicht, sondern in outcome="conflict" uebersetzt —
  // Aufrufer verzweigen auf `outcome`, nicht auf HTTP-Status/try-catch.
  it("uebersetzt einen 409 embedding_legacy_conflict in outcome='conflict' statt zu werfen", async () => {
    const activeConfiguration = { ...PROPOSED_CONFIGURATION, id: "emb-active", status: "active" };
    const legacy = { provider_kind: "ollama", model_id: "mxbai-embed-large", dimensions: 1024 };
    serviceMock.post.mockRejectedValueOnce(
      new ApiError({
        code: "embedding_legacy_conflict",
        status: 409,
        message: "Aktive Embedding-Konfiguration weicht von Config.EMBEDDING_* ab",
        details: { active_configuration: activeConfiguration, legacy },
      }),
    );

    const result = await syncLegacyEmbeddingConfiguration("ollama");

    expect(result.outcome).toBe("conflict");
    expect(result.configuration).toBeNull();
    expect(result.active_configuration).toMatchObject({ id: "emb-active" });
    expect(result.legacy).toEqual(legacy);
  });

  it("wirft weiterhin bei anderen Fehlern (kein embedding_legacy_conflict)", async () => {
    serviceMock.post.mockRejectedValueOnce(
      new ApiError({ code: "no_legacy_config", status: 409, message: "kein Legacy-Config" }),
    );

    await expect(syncLegacyEmbeddingConfiguration("ollama")).rejects.toMatchObject({
      code: "no_legacy_config",
    });
  });
});
