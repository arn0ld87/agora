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
  EmbeddingLegacySyncResult,
  EmbeddingLegacySyncResultSchema,
} from "../contracts/embeddingContract";
import { ApiSuccessEnvelope, isApiError } from "./envelope";
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

/**
 * Uebernimmt ``Config.EMBEDDING_*`` als kanonische Konfiguration (#1417).
 *
 * Drei Faelle, siehe ``EmbeddingLegacySyncResultSchema``: ``created`` (200,
 * keine aktive Konfiguration existierte), ``noop`` (200, identisch zur
 * aktiven Konfiguration, nichts geschrieben) und ``conflict`` (409, die
 * aktive Konfiguration weicht ab — Backend schreibt nichts, meldet den
 * Konflikt ueber ``details.active_configuration``/``details.legacy``).
 * Der 409-Fall wird hier in denselben Ergebnis-Vertrag uebersetzt, statt
 * als Exception durchgereicht zu werden — Aufrufer (Store/View) muessen
 * nur noch auf ``outcome`` verzweigen, nicht auf HTTP-Status.
 */
export async function syncLegacyEmbeddingConfiguration(
  providerConnectionId: string,
): Promise<EmbeddingLegacySyncResult> {
  try {
    const resp = await service.post<ApiSuccessEnvelope<unknown>>(
      "/api/llm/embedding/configurations/sync-legacy",
      { provider_connection_id: providerConnectionId },
    );
    return unwrapAndParse(resp, EmbeddingLegacySyncResultSchema);
  } catch (err) {
    if (isApiError(err) && err.code === "embedding_legacy_conflict" && err.details) {
      return EmbeddingLegacySyncResultSchema.parse({
        outcome: "conflict",
        configuration: null,
        active_configuration: err.details["active_configuration"],
        legacy: err.details["legacy"],
      });
    }
    throw err;
  }
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
