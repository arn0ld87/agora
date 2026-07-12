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

import {
  deleteProviderConnection,
  listProviderConnectionModels,
  listProviderConnections,
  testProviderConnection,
  upsertProviderConnection,
} from "../providerConnections";

const OPENAI_CONNECTION = {
  id: "openai",
  provider_kind: "openai",
  display_name: "OpenAI",
  transport: "http",
  auth_mode: "api_key",
  base_url: "https://api.openai.com/v1",
  enabled: true,
  status: "connected",
  status_message: null,
  secret_ref: "openai",
  capabilities: {},
  created_at: "2026-07-12T10:00:00+00:00",
  updated_at: "2026-07-12T10:00:00+00:00",
  last_tested_at: "2026-07-12T10:05:00+00:00",
};

const OLLAMA_CONNECTION = {
  id: "ollama",
  provider_kind: "ollama",
  display_name: "Ollama (lokal)",
  transport: "local",
  auth_mode: "none",
  base_url: "http://127.0.0.1:11434",
  enabled: true,
  status: "unknown",
  status_message: null,
  secret_ref: null,
  capabilities: {},
  created_at: "2026-07-12T10:00:00+00:00",
  updated_at: "2026-07-12T10:00:00+00:00",
  last_tested_at: null,
};

describe("providerConnections api client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("listProviderConnections parst eine gültige Envelope über Zod", async () => {
    serviceMock.get.mockResolvedValueOnce({
      success: true,
      data: { items: [OPENAI_CONNECTION], total: 1 },
    });

    const result = await listProviderConnections();

    expect(serviceMock.get).toHaveBeenCalledWith("/api/llm/provider-connections");
    expect(result.total).toBe(1);
    expect(result.items[0]).toMatchObject({ id: "openai", status: "connected" });
  });

  it("listProviderConnections wirft strukturiert bei Schema-Drift statt leer zu rendern", async () => {
    serviceMock.get.mockResolvedValueOnce({
      success: true,
      // provider_kind fehlt -> muss an der Response-Grenze scheitern, nicht
      // stillschweigend als leere Liste durchgereicht werden.
      data: { items: [{ ...OPENAI_CONNECTION, provider_kind: undefined }], total: 1 },
    });

    await expect(listProviderConnections()).rejects.toThrow(/schema mismatch/);
  });

  it("maskiert Connection-Responses enthalten nie einen Klartext-Key", async () => {
    serviceMock.get.mockResolvedValueOnce({
      success: true,
      // Ein API-Key-Feld auf der Connection ist laut Contract nie vorgesehen
      // (`.strict()`); ein Leak muss als Zod-Fehler auffallen, nicht als
      // toleranter Passthrough.
      data: { items: [{ ...OPENAI_CONNECTION, api_key: "sk-leak-should-fail" }], total: 1 },
    });

    await expect(listProviderConnections()).rejects.toThrow(/schema mismatch/);
  });

  it("upsertProviderConnection sendet PUT ohne gespeicherten Klartext-Key im Rückgabewert", async () => {
    serviceMock.put.mockResolvedValueOnce({
      success: true,
      data: { connection: OPENAI_CONNECTION },
    });

    const connection = await upsertProviderConnection("openai", {
      display_name: "OpenAI",
      provider_kind: "openai",
      base_url: "https://api.openai.com/v1",
      api_key: "sk-should-not-be-persisted-client-side",
    });

    expect(serviceMock.put).toHaveBeenCalledWith(
      "/api/llm/provider-connections/openai",
      expect.objectContaining({ api_key: "sk-should-not-be-persisted-client-side" }),
    );
    expect(connection).toMatchObject({ id: "openai" });
    expect(connection).not.toHaveProperty("api_key");
  });

  it("upsertProviderConnection unterstützt den lokalen Ollama-Flow mit Loopback-Base-URL", async () => {
    serviceMock.put.mockResolvedValueOnce({
      success: true,
      data: { connection: OLLAMA_CONNECTION },
    });

    const connection = await upsertProviderConnection("ollama", {
      display_name: "Ollama (lokal)",
      provider_kind: "ollama",
      base_url: "http://127.0.0.1:11434",
      enabled: true,
    });

    expect(connection.transport).toBe("local");
    expect(connection.auth_mode).toBe("none");
    expect(connection.base_url).toBe("http://127.0.0.1:11434");
  });

  it("deleteProviderConnection ruft DELETE auf der Connection-ID auf", async () => {
    serviceMock.delete.mockResolvedValueOnce({ success: true, data: { status: "deleted" } });

    await deleteProviderConnection("openai");

    expect(serviceMock.delete).toHaveBeenCalledWith("/api/llm/provider-connections/openai");
  });

  it("testProviderConnection parst den Test-Status inkl. models_found", async () => {
    serviceMock.post.mockResolvedValueOnce({
      success: true,
      data: { status: "available", status_message: null, models_found: 12 },
    });

    const result = await testProviderConnection("openai");

    expect(serviceMock.post).toHaveBeenCalledWith("/api/llm/provider-connections/openai/test");
    expect(result).toEqual({ status: "available", status_message: null, models_found: 12 });
  });

  it("testProviderConnection lehnt unbekannte Statuswerte über Zod ab", async () => {
    serviceMock.post.mockResolvedValueOnce({
      success: true,
      data: { status: "totally_made_up_status", status_message: null, models_found: 0 },
    });

    await expect(testProviderConnection("openai")).rejects.toThrow(/schema mismatch/);
  });

  it("listProviderConnectionModels parst die Modellliste als AiModel[]", async () => {
    serviceMock.get.mockResolvedValueOnce({
      success: true,
      data: [
        {
          provider_connection_id: "openai",
          model_id: "gpt-4o",
          display_name: "gpt-4o",
          source: "live",
        },
      ],
    });

    const models = await listProviderConnectionModels("openai");

    expect(serviceMock.get).toHaveBeenCalledWith("/api/llm/provider-connections/openai/models");
    expect(models).toHaveLength(1);
    expect(models[0]).toMatchObject({ model_id: "gpt-4o", source: "live" });
  });
});
