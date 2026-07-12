/**
 * embeddingMigrations — HTTP-Client fuer Re-Embedding-Migrationen und
 * Ollama-Download (Slice 4.3).
 *
 * Bedient backend/app/api/embedding_migrations.py
 * `/api/llm/embedding/migrations*` und `/api/llm/embedding/ollama/pull`.
 */
import { z } from "zod";
import service from "./index";
import {
  EmbeddingMigrationJob,
  EmbeddingMigrationJobResponseSchema,
  EmbeddingMigrationJobsListResponseSchema,
  EmbeddingMigrationStatus,
  OllamaPullReport,
  OllamaPullReportResponseSchema,
} from "../contracts/embeddingContract";
import { ApiSuccessEnvelope } from "./envelope";
import { unwrapAndParse } from "./parse";

const START_PAYLOAD_SCHEMA = z
  .object({
    configuration_id: z.string().min(1),
  })
  .strict();
export type StartMigrationPayload = z.infer<typeof START_PAYLOAD_SCHEMA>;

const OLLAMA_PULL_PAYLOAD_SCHEMA = z
  .object({
    model: z
      .string()
      .min(1)
      .max(100)
      // Strikte Server-Validierung gespiegelt: ASCII a-z, A-Z, 0-9,
      // '-', '_', '.', ':'. Verhindert versehentliche Shell-Injection
      // auf Modell-Bezeichnungs-Ebene.
      .regex(/^[A-Za-z0-9_.\-:]{1,100}$/u, {
        message:
          "Model-Name darf nur ASCII-Buchstaben, Ziffern, '-', '_', '.', ':' enthalten",
      }),
    configuration_id: z.string().min(1).optional(),
  })
  .strict();
export type OllamaPullPayload = z.infer<typeof OLLAMA_PULL_PAYLOAD_SCHEMA>;

export async function startEmbeddingMigration(
  payload: StartMigrationPayload,
): Promise<EmbeddingMigrationJob> {
  START_PAYLOAD_SCHEMA.parse(payload);
  const resp = await service.post<ApiSuccessEnvelope<unknown>>(
    "/api/llm/embedding/migrations",
    payload,
  );
  return unwrapAndParse(resp, EmbeddingMigrationJobResponseSchema).job;
}

export async function listEmbeddingMigrations(
  configurationId?: string,
): Promise<EmbeddingMigrationJob[]> {
  const query = configurationId
    ? `?configuration_id=${encodeURIComponent(configurationId)}`
    : "";
  const resp = await service.get<ApiSuccessEnvelope<unknown>>(
    `/api/llm/embedding/migrations${query}`,
  );
  return unwrapAndParse(
    resp,
    EmbeddingMigrationJobsListResponseSchema,
  ).jobs;
}

export async function getEmbeddingMigration(
  jobId: string,
): Promise<EmbeddingMigrationJob | null> {
  try {
    const resp = await service.get<ApiSuccessEnvelope<unknown>>(
      `/api/llm/embedding/migrations/${encodeURIComponent(jobId)}`,
    );
    return unwrapAndParse(resp, EmbeddingMigrationJobResponseSchema).job;
  } catch (err) {
    if (isNotFound(err)) {
      return null;
    }
    throw err;
  }
}

export async function runEmbeddingMigration(
  jobId: string,
): Promise<EmbeddingMigrationJob> {
  const resp = await service.post<ApiSuccessEnvelope<unknown>>(
    `/api/llm/embedding/migrations/${encodeURIComponent(jobId)}/run`,
  );
  return unwrapAndParse(resp, EmbeddingMigrationJobResponseSchema).job;
}

export async function cancelEmbeddingMigration(
  jobId: string,
): Promise<EmbeddingMigrationJob> {
  const resp = await service.post<ApiSuccessEnvelope<unknown>>(
    `/api/llm/embedding/migrations/${encodeURIComponent(jobId)}/cancel`,
  );
  return unwrapAndParse(resp, EmbeddingMigrationJobResponseSchema).job;
}

export async function pullOllamaEmbeddingModel(
  payload: OllamaPullPayload,
): Promise<OllamaPullReport> {
  OLLAMA_PULL_PAYLOAD_SCHEMA.parse(payload);
  const resp = await service.post<ApiSuccessEnvelope<unknown>>(
    "/api/llm/embedding/ollama/pull",
    payload,
  );
  return unwrapAndParse(resp, OllamaPullReportResponseSchema).report;
}

function isNotFound(err: unknown): boolean {
  if (err && typeof err === "object" && "response" in err) {
    const response = (err as { response?: { status?: number } }).response;
    return response?.status === 404;
  }
  return false;
}

export type { EmbeddingMigrationJob, EmbeddingMigrationStatus };
