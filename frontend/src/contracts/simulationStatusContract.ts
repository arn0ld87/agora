/**
 * Simulationsstatus-Contract — Zod-Spiegel zu
 * backend/app/contracts/simulation_status_contract.py (`SimulationStatusResponse`).
 *
 * Gespiegelt wird die Antwortform von `GET /api/simulation/<id>`.
 *
 * Anlass (#1713): Nach dem Simulationsende meldete die Route weiter `running`,
 * weil die Env für Interviews offen bleibt. Seitdem projiziert das Backend
 * `status` auf den terminalen `runner_status` und meldet den Interview-Modus
 * getrennt in `interview_env_alive`. Beides soll im Frontend nicht wieder
 * über eine `[key: string]: unknown`-Signatur verschwinden, deshalb `.strict()`.
 */
import { z } from "zod";

export const RunnerStatusSchema = z.enum([
  "idle",
  "starting",
  "running",
  "paused",
  "stopping",
  "stopped",
  "completed",
  "failed",
  "ready",
]);
export type RunnerStatus = z.infer<typeof RunnerStatusSchema>;

export const SimulationStatusResponseSchema = z
  .object({
    simulation_id: z.string().min(1),
    project_id: z.string(),
    graph_id: z.string(),
    enable_twitter: z.boolean(),
    enable_reddit: z.boolean(),
    status: z.string(),
    entities_count: z.number().int(),
    profiles_count: z.number().int(),
    entity_types: z.array(z.unknown()),
    config_generated: z.boolean(),
    config_reasoning: z.string(),
    current_round: z.number().int(),
    twitter_status: z.string(),
    reddit_status: z.string(),
    created_at: z.string(),
    updated_at: z.string(),
    branch_depth: z.number().int(),
    interview_env_alive: z.boolean(),

    branch_name: z.string().nullable().optional(),
    error: z.string().nullable().optional(),
    persona_floor: z.number().int().nullable().optional(),
    root_simulation_id: z.string().nullable().optional(),
    source_simulation_id: z.string().nullable().optional(),
    run_instructions: z.record(z.string(), z.unknown()).nullable().optional(),
    runner_status: RunnerStatusSchema.nullable().optional(),
  })
  .strict();
export type SimulationStatusResponse = z.infer<typeof SimulationStatusResponseSchema>;
