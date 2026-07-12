/**
 * embeddingConfigurations — HTTP-Client fuer den kanonischen
 * Embedding-Configuration-Lifecycle (Slice 4.2).
 *
 * Bedient backend/app/api/embedding_configurations.py
 * `/api/llm/embedding/configurations*`. Jede Response-Grenze wird mit
 * den Zod-Schemas aus contracts/embeddingContract validiert — kein
 * `?.`-Durchreichen bei Schema-Drift.
 */
import service from "./index";
import { z } from "zod";
import {
  EmbeddingConfiguration,
  EmbeddingConfigurationResponseSchema,
  EmbeddingConfigurationUpsertRequest,
  EmbeddingConfigurationUpsertRequestSchema,
  EmbeddingConfigurationsListResponse,
  EmbeddingConfigurationsListResponseSchema,
  EmbeddingConfigurationScope,
} from "../contracts/embeddingContract";
import { ApiSuccessEnvelope } from "./envelope";
import { unwrapAndParse } from "./parse";

export async function listEmbeddingConfigurations(
  scope?: EmbeddingConfigurationScope,
): Promise<EmbeddingConfigurationsListResponse> {
  const query = scope ? `?scope=${encodeURIComponent(scope)}` : "";
  const resp = await service.get<ApiSuccessEnvelope<unknown>>(
    `/api/llm/embedding/configurations${query}`,
  );
  return unwrapAndParse(resp, EmbeddingConfigurationsListResponseSchema);
}

export async function getActiveEmbeddingConfiguration(): Promise<{
  configuration: EmbeddingConfiguration | null;
  source: "store" | "legacy" | "none";
}> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>(
    "/api/llm/embedding/configurations/active",
  );
  const parsed = unwrapAndParse(
    resp,
    // active response has the same wrapper; we read the optional fields
    // defensively without a dedicated schema (no extra contract for
    // legacy-sourcing semantics yet).
    EmbeddingConfigurationsListResponseSchema.partial().extend({
      source: z.enum(["store", "legacy", "none"]),
      configuration: EmbeddingConfigurationResponseSchema.shape.configuration.nullable(),
    }),
  );
  return {
    configuration: parsed.configuration ?? null,
    source: parsed.source ?? "none",
  };
}

export async function upsertEmbeddingConfiguration(
  configurationId: "new" | string,
  payload: EmbeddingConfigurationUpsertRequest,
): Promise<EmbeddingConfiguration> {
  // Vorab-Validierung auf Client-Seite (Backend validiert erneut).
  EmbeddingConfigurationUpsertRequestSchema.parse(payload);
  const resp = await service.put<ApiSuccessEnvelope<unknown>>(
    `/api/llm/embedding/configurations/${encodeURIComponent(configurationId)}`,
    payload,
  );
  return unwrapAndParse(resp, EmbeddingConfigurationResponseSchema).configuration;
}

export async function deleteEmbeddingConfiguration(
  configurationId: string,
): Promise<void> {
  await service.delete(
    `/api/llm/embedding/configurations/${encodeURIComponent(configurationId)}`,
  );
}

export async function testEmbeddingConfiguration(
  configurationId: string,
): Promise<{
  configuration: EmbeddingConfiguration;
  probe: {
    status: "available" | "unavailable" | "invalid_credentials" | "degraded" | "unsupported";
    status_message: string | null;
    actual_dimensions: number | null;
  };
}> {
  const resp = await service.post<ApiSuccessEnvelope<unknown>>(
    `/api/llm/embedding/configurations/${encodeURIComponent(configurationId)}/test`,
  );
  const parsed = unwrapAndParse(
    resp,
    EmbeddingConfigurationResponseSchema.extend({
      probe: z.object({
        status: z.enum([
          "available",
          "unavailable",
          "invalid_credentials",
          "degraded",
          "unsupported",
        ]),
        status_message: z.string().nullable(),
        actual_dimensions: z.number().int().nullable(),
      }),
    }),
  );
  return {
    configuration: parsed.configuration,
    probe: parsed.probe,
  };
}

export async function activateEmbeddingConfiguration(
  configurationId: string,
): Promise<EmbeddingConfiguration> {
  const resp = await service.post<ApiSuccessEnvelope<unknown>>(
    `/api/llm/embedding/configurations/${encodeURIComponent(configurationId)}/activate`,
  );
  return unwrapAndParse(resp, EmbeddingConfigurationResponseSchema).configuration;
}
