import { z } from 'zod';
import { PersonaTargetSchema } from './personaTargetContract';

/**
 * Prepare-Status — Zod-Spiegel zu
 * `backend/app/contracts/prepare_status_contract.py` (Issue #1174, Muster
 * aus #1458).
 *
 * Deckt die literalen Kurzschluss-Antworten von `POST /api/simulation/prepare`
 * und `POST /api/simulation/prepare/status` ab: Prepared-Shortcut,
 * Task-gestartet-Antwort und die drei Kurzschluesse in `/prepare/status`
 * (already_completed via `simulation_id`, not_started,
 * Task-nicht-gefunden-aber-fertig). Der Live-Task-Zweig (`Task.to_dict()`,
 * sobald ein laufender Task existiert) bleibt aussen vor — er hat eine ganz
 * andere Feldmenge und keinen eigenen Backend-Contract (siehe
 * `TaskStatusData` in `api/simulation.ts`). `parsePrepareStatusResponse`
 * ist deshalb bewusst NICHT in `useSimulationPrepare.ts`s Polling verdrahtet:
 * es wuerde jede Task-Branch-Antwort als Validierungsfehler ablehnen.
 */

/** Die drei Kurzschluss-Zustaende dieser beiden Endpunkte. */
export const PrepareStatusValueSchema = z.enum(['ready', 'preparing', 'not_started']);
export type PrepareStatusValue = z.infer<typeof PrepareStatusValueSchema>;

/** Stabile i18n-Schluessel — siehe `i18n/statusMessage.ts` + `locales/{de,en}.json`. */
export const PrepareMessageKeySchema = z.enum([
  'prepare.already_completed',
  'prepare.task_started',
  'prepare.not_started',
]);
export type PrepareMessageKey = z.infer<typeof PrepareMessageKeySchema>;

export const PrepareStatusResponseSchema = z
  .object({
    simulation_id: z.string(),
    status: PrepareStatusValueSchema,
    message: z.string(),
    message_key: PrepareMessageKeySchema,
    already_prepared: z.boolean(),
    task_id: z.string().optional(),
    run_id: z.string().optional(),
    expected_entities_count: z.number().int().optional(),
    entity_types: z.array(z.string()).optional(),
    persona_target: PersonaTargetSchema.optional(),
    progress: z.number().int().min(0).max(100).optional(),
    /** Form je Aufrufer verschieden (`_check_simulation_prepared`-Diagnose). */
    prepare_info: z.record(z.string(), z.unknown()).optional(),
  })
  .strict();

export type PrepareStatusResponse = z.infer<typeof PrepareStatusResponseSchema>;

/**
 * Tolerant beim Lesen, analog `parsePersonaTarget`: ein unerwartetes Feld
 * darf das Polling nicht kippen — der Aufrufer faellt bei einem Miss auf
 * die lose getypte `TaskStatusData` zurueck.
 */
export function parsePrepareStatusResponse(value: unknown): PrepareStatusResponse | null {
  const result = PrepareStatusResponseSchema.safeParse(value);
  return result.success ? result.data : null;
}
