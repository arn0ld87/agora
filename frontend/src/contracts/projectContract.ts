/**
 * Projekt-Contract — Zod-Spiegel zu backend/app/contracts/project_contract.py
 *
 * Gespiegelt wird die Antwortform von `GET /project/<id>`, `GET /project/list`
 * und `POST /project/<id>/reset`, also das, was `Project.to_dict()` erzeugt.
 *
 * Dieser Spiegel entsteht aus einem konkreten Anlass: vorher stand an seiner
 * Stelle ein handgeschriebenes Interface mit `[key: string]: unknown`. Darin
 * hiess das Namensfeld `project_name` — ein Feld, das das Backend nie geliefert
 * hat. Die Fluchtklappe machte den Zugriff darauf zu gueltigem TypeScript, und
 * so zeigte das Projektregal jahrelang die rohe `project_id` statt des Namens.
 *
 * Deshalb `.strict()`: eine Abweichung zwischen Backend-Vertrag und diesem
 * Spiegel soll im Test auffallen und nicht in der Oberflaeche.
 */
import { z } from "zod";

export const ProjectStatusSchema = z.enum([
  "created",
  "ontology_generated",
  "graph_building",
  "graph_completed",
  "graph_incomplete",
  "failed",
]);
export type ProjectStatus = z.infer<typeof ProjectStatusSchema>;

export const ProjectSchema = z
  .object({
    project_id: z.string().min(1),
    name: z.string(),
    status: ProjectStatusSchema,
    created_at: z.string(),
    updated_at: z.string(),

    // Artefaktverweise. Die Form der Eintraege ist im Backend bewusst nicht
    // gehaertet (Altbestand), deshalb hier ebenfalls offen.
    files: z.array(z.record(z.string(), z.unknown())),
    total_text_length: z.number(),

    ontology: z.record(z.string(), z.unknown()).nullable(),
    analysis_summary: z.string().nullable(),

    graph_id: z.string().nullable(),
    graph_build_task_id: z.string().nullable(),

    simulation_requirement: z.string().nullable(),
    chunk_size: z.number(),
    chunk_overlap: z.number(),

    // Traegt nur redigierte Metadaten (Provider, Base-URL, api_key_set),
    // nie einen Schluessel.
    llm_model: z.string().nullable(),
    llm_provider: z.record(z.string(), z.unknown()).nullable(),
    llm_profile_id: z.string().nullable(),
    ai_model_ref: z.record(z.string(), z.unknown()).nullable(),

    error: z.string().nullable(),
  })
  .strict();
export type Project = z.infer<typeof ProjectSchema>;

export const ProjectListResponseSchema = z
  .object({
    projects: z.array(ProjectSchema),
  })
  .strict();
export type ProjectListResponse = z.infer<typeof ProjectListResponseSchema>;
