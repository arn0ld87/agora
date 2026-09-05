/**
 * Modell-Preset-Contract — Zod-Spiegel zu
 * backend/app/contracts/model_preset_contract.py (Issue #1395).
 * Spiegelt ModelPreset, AvailableModelsResponse.
 */
import { z } from 'zod'

/**
 * Ein Eintrag aus `presets[]` bzw. `ollama[]` von
 * `GET /api/simulation/available-models`.
 *
 * `label` bleibt bewusst ein optionales Legacy-Feld: Ollama-Tag-Eintraege
 * setzen es auf den rohen Modellnamen, aeltere Backends im Mischbetrieb
 * koennen es fuer kuratierte Presets noch liefern. Aufloesungskette in
 * `i18n/modelPresetLabel.ts::resolvePresetLabel`.
 *
 * Rein `optional()`, nicht `nullable()`: der Backend-Contract serialisiert
 * ungesetzte Felder ueber einen ``field_serializer`` mit ``exclude_none``
 * weg statt sie als ``null`` zu senden (siehe
 * ``backend/app/contracts/model_preset_contract.py``) — auf dem Draht
 * fehlt das Feld, es ist nie ``null``.
 */
export const ModelPresetSchema = z
  .object({
    name: z.string().min(1),
    kind: z.string().optional(),
    label: z.string().optional(),
    label_key: z.string().optional(),
    size: z.number().optional(),
    family: z.string().optional(),
    parameter_size: z.string().optional(),
  })
  .strict()
export type ModelPreset = z.infer<typeof ModelPresetSchema>

/**
 * Response von `GET /api/simulation/available-models`.
 */
export const AvailableModelsResponseSchema = z
  .object({
    ollama: z.array(ModelPresetSchema).default(() => []),
    presets: z.array(ModelPresetSchema).default(() => []),
    current_default: z.string().default(''),
    // Vokabular deckungsgleich mit `HttpDetectedProvider`
    // (backend/app/llm/providers/registry.py) — bewusst `string` statt
    // Enum, damit ein neuer Provider den Vertrag nicht bricht.
    default_provider: z.string().default('unknown'),
    ollama_base_url: z.string().nullable().default(null),
    ollama_reachable: z.boolean().default(false),
    ollama_error: z.string().nullable().default(null),
    ollama_skipped: z.boolean().default(false),
    ollama_skipped_provider: z.string().nullable().default(null),
    ollama_skip_reason: z.string().nullable().default(null),
    neo4j_reachable: z.boolean().default(false),
    neo4j_error: z.string().nullable().default(null),
    neo4j_uri: z.string().nullable().default(null),
    default_language: z.string().default('de'),
    agent_tools_enabled: z.boolean().default(false),
    max_tool_calls_per_action: z.number().default(2),
  })
  .strict()
export type AvailableModelsResponse = z.infer<typeof AvailableModelsResponseSchema>
