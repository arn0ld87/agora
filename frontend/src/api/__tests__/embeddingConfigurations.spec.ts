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

  it("syncLegacyEmbeddingConfiguration sendet POST mit provider_connection_id und parst die Envelope", async () => {
    serviceMock.post.mockResolvedValueOnce({
      success: true,
      data: { configuration: PROPOSED_CONFIGURATION },
    });

    const result = await syncLegacyEmbeddingConfiguration("ollama");

    expect(serviceMock.post).toHaveBeenCalledWith(
      "/api/llm/embedding/configurations/sync-legacy",
      { provider_connection_id: "ollama" },
    );
    expect(result).toMatchObject({ id: "cfg-legacy-sync", status: "proposed" });
  });

  it("syncLegacyEmbeddingConfiguration wirft strukturiert bei Schema-Drift statt tolerant weiterzurendern", async () => {
    serviceMock.post.mockResolvedValueOnce({
      success: true,
      // status fehlt -> muss an der Response-Grenze scheitern.
      data: { configuration: { ...PROPOSED_CONFIGURATION, status: undefined } },
    });

    await expect(syncLegacyEmbeddingConfiguration("ollama")).rejects.toThrow(
      /schema mismatch/,
    );
  });
});
