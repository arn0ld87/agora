/**
 * PersonaQuotaPlan-Contract — Zod-Spiegel.
 *
 * Hand-gepflegt, aber 1:1 zu schemas/persona-quota-plan.schema.json.
 * Backend-Quelle: backend/app/contracts/persona_contract.py:67.
 *
 * Sub-Slice 20c — Frontend nutzt diesen Contract für client-seitige
 * Validierung des Quoten-Editors in Step2EnvSetup.vue, bevor das
 * payload.quota_plan an POST /api/simulations/<id>/prepare geht.
 */
import { z } from "zod";

export const PersonaQuotaPlanSchema = z
  .object({
    targets: z.record(z.string().min(1), z.number().int().min(1).max(200)),
    total: z.number().int().min(1).max(500),
  })
  .strict()
  .superRefine((val, ctx) => {
    const sum = Object.values(val.targets).reduce((acc, v) => acc + v, 0);
    if (sum !== val.total) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["total"],
        message: `total=${val.total} != sum(targets)=${sum}. Plan ist inkonsistent.`,
      });
    }
    if (Object.keys(val.targets).length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["targets"],
        message: "targets muss mindestens ein Segment enthalten.",
      });
    }
  });

export type PersonaQuotaPlan = z.infer<typeof PersonaQuotaPlanSchema>;

/**
 * Helper für UI-State: Reihenfolge erhalten als Array von Tupeln,
 * Konvertierung zu API-konformem `targets`-Dict + `total` für den
 * POST-Body.
 */
export function buildQuotaPlanFromEntries(
  entries: ReadonlyArray<{ segment: string; count: number }>
): { targets: Record<string, number>; total: number } {
  const targets: Record<string, number> = {};
  for (const { segment, count } of entries) {
    if (!segment) continue;
    targets[segment] = count;
  }
  const total = Object.values(targets).reduce((acc, v) => acc + v, 0);
  return { targets, total };
}
