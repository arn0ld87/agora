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
  ActiveEmbeddingConfigurationResponse,
  ActiveEmbeddingConfigurationResponseSchema,
  EmbeddingConfiguration,
  EmbeddingConfigurationResponseSchema,
  EmbeddingConfigurationUpsertRequest,
  EmbeddingConfigurationUpsertRequestSchema,
  EmbeddingConfigurationsListResponse,
  EmbeddingConfigurationsListResponseSchema,
  EmbeddingConfigurationScope,
  EmbeddingIndexVersion,
  EmbeddingIndexVersionListResponseSchema,
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

export async function getActiveEmbeddingConfiguration(): Promise<ActiveEmbeddingConfigurationResponse> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>(
    "/api/llm/embedding/configurations/active",
  );
  return unwrapAndParse(resp, ActiveEmbeddingConfigurationResponseSchema);
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

export async function syncLegacyEmbeddingConfiguration(
  providerConnectionId: string,
): Promise<EmbeddingConfiguration> {
  const resp = await service.post<ApiSuccessEnvelope<unknown>>(
    "/api/llm/embedding/configurations/sync-legacy",
    { provider_connection_id: providerConnectionId },
  );
  return unwrapAndParse(resp, EmbeddingConfigurationResponseSchema).configuration;
}

/**
 * Listet alle EmbeddingIndexVersion-Datensätze, neueste zuerst (f006,
 * Slice embedding-ssot). Macht den `building`-Status einer laufenden
 * Migration und die weiterhin aktive Quell-Version sichtbar — vorher
 * hatte die Oberfläche dafür keinen API-Zugriff.
 */
export async function listEmbeddingIndexVersions(): Promise<EmbeddingIndexVersion[]> {
  const resp = await service.get<ApiSuccessEnvelope<unknown>>(
    "/api/llm/embedding/index-versions",
  );
  return unwrapAndParse(resp, EmbeddingIndexVersionListResponseSchema).versions;
}
