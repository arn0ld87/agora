/**
 * Streitfrage-Contract — Zod-Spiegel (Issue #1778, Schritt 1.4).
 *
 * Hand-gepflegt, 1:1 zu:
 *   schemas/contested-question.schema.json
 *
 * Änderungen am Pydantic-Modell
 * (backend/app/contracts/contested_question_contract.py)
 * → Schema-Dump → diese Datei synchronisieren.
 *
 * Regeln (gespiegelt aus dem Backend-Contract):
 *   - Jede Simulationskonfiguration trägt eine Streitfrage oder die
 *     ausdrückliche Angabe, dass es keine gibt (origin="none").
 *   - origin="none" verlangt statement=null; origin assistant/user
 *     verlangt ein statement.
 */
import { z } from "zod";

// === Literale (1:1 zum Pydantic-Contract) ===
export const ContestedQuestionOriginSchema = z.enum([
  "assistant",
  "user",
  "none",
]);
export type ContestedQuestionOrigin = z.infer<
  typeof ContestedQuestionOriginSchema
>;

// === ContestedQuestion (schemas/contested-question.schema.json) ===
export const ContestedQuestionSchema = z
  .object({
    statement: z.string().min(10).max(300).nullable().optional(),
    origin: ContestedQuestionOriginSchema.default("none"),
    absence_reason: z.string().max(300).nullable().optional(),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.origin === "none" && value.statement != null) {
      ctx.addIssue({
        code: "custom",
        path: ["origin"],
        message: "origin=none verlangt statement=null",
      });
    }
    if (value.origin !== "none" && value.statement == null) {
      ctx.addIssue({
        code: "custom",
        path: ["statement"],
        message: "origin assistant/user verlangt ein statement",
      });
    }
  });
export type ContestedQuestion = z.infer<typeof ContestedQuestionSchema>;
