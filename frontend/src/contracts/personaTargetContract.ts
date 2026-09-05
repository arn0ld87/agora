import { z } from 'zod';

/**
 * Persona-Ziel — Zod-Spiegel zu
 * `backend/app/contracts/persona_target_contract.py` (Issue #1034).
 *
 * Der Fortschrittszähler „Erzeugt X / Y Personas…“ lief über seinen
 * eigenen Nenner: angezeigt wurde `expected_entities_count`, also die
 * Zahl der Graph-Entitäten. Generiert werden aber Personas, und deren
 * Zahl steht erst später fest — entweder über einen `PersonaQuotaPlan`
 * oder über den Persona-Floor, der einen zu kleinen Entity-Pool per
 * Round-Robin hochskaliert. Sieben Entitäten wurden so zu fünfzig
 * Personas, während der Nenner bei sieben blieb.
 *
 * `persona_target_count` ist der korrekte Nenner. `entity_count` bleibt
 * daneben erhalten, weil beide Zahlen etwas Verschiedenes aussagen und
 * `floor_applied` erst im Vergleich Sinn ergibt.
 */

export const PersonaTargetSchema = z.object({
  /** Entitäten nach Eignungsfilter und `max_agents`-Cap. */
  entity_count: z.number().int().min(0),
  /** Das tatsächliche Generierungsziel — der Nenner der Anzeige. */
  persona_target_count: z.number().int().min(0),
  /** Wahr, wenn der Floor das Ziel über die Entitätenzahl angehoben hat. */
  floor_applied: z.boolean(),
  /** Wirksamer Floor: MIN_PERSONA_TABLE_ROWS, gedeckelt durch `max_agents`. */
  floor: z.number().int().min(0),
}).strict();

export type PersonaTarget = z.infer<typeof PersonaTargetSchema>;

/**
 * Tolerant beim Lesen: Ein unbekanntes oder fehlendes Feld darf den
 * Lauf-Start nicht kippen — der Nenner ist eine Anzeige, kein Gate.
 * Fällt die Validierung, bleibt `expectedTotal` schlicht ungesetzt und
 * die Oberfläche zeigt „?“ wie vor diesem Slice.
 */
export function parsePersonaTarget(value: unknown): PersonaTarget | null {
  const result = PersonaTargetSchema.safeParse(value);
  return result.success ? result.data : null;
}
