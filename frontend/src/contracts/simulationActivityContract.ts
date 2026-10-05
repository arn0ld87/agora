/**
 * Aktivitätsmodell-Contract — Zod-Spiegel (Issue #1779, Schritt 2.4).
 *
 * Hand-gepflegt, 1:1 zu:
 *   schemas/simulation-activity-model.schema.json
 *
 * Änderungen am Pydantic-Modell
 * (backend/app/contracts/simulation_activity_contract.py)
 * → Schema-Dump → diese Datei synchronisieren.
 *
 * Regeln (gespiegelt aus dem Backend-Contract):
 *   - text_posts_per_day nennt alle Akteursklassen, keine Rate ist negativ.
 *   - hourly_weights hat 24 Werte, keiner negativ, Summe 1,0 (Toleranz 1e-6).
 */
import { z } from "zod";

const HOURS_PER_DAY = 24;
const HOURLY_WEIGHT_SUM_TOLERANCE = 1e-6;

// === ActivityMode ===
export const ActivityModeSchema = z.enum(["realistic", "active"]);
export type ActivityMode = z.infer<typeof ActivityModeSchema>;

// === ActorClass ===
export const ActorClassSchema = z.enum([
  "individual",
  "politician",
  "authority",
  "organisation",
  "media",
]);
export type ActorClass = z.infer<typeof ActorClassSchema>;

// === ActivityModelConfig (schemas/simulation-activity-model.schema.json) ===
export const ActivityModelConfigSchema = z
  .object({
    schema_version: z.literal(1).default(1),
    mode: ActivityModeSchema,
    max_text_actions_per_activation: z.number().int().min(1),
    max_reactions_per_activation: z.number().int().min(0),
    text_posts_per_day: z
      .record(ActorClassSchema, z.number().min(0)),
    hourly_weights: z.array(z.number().min(0)).length(HOURS_PER_DAY),
  })
  .strict()
  .refine(
    (d) =>
      Math.abs(d.hourly_weights.reduce((sum, w) => sum + w, 0) - 1) <=
      HOURLY_WEIGHT_SUM_TOLERANCE,
    { message: "hourly_weights muss die Summe 1,0 ergeben" },
  );
export type ActivityModelConfig = z.infer<typeof ActivityModelConfigSchema>;
