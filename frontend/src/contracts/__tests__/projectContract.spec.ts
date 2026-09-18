/**
 * Der Zod-Spiegel muss die echte Backend-Antwort strikt parsen.
 *
 * Die Beispiel-Payload hier ist bewusst das, was `Project.to_dict()` in
 * backend/app/contracts/project_contract.py erzeugt — vollstaendig, mit allen
 * neunzehn Schluesseln. Genau daran fehlte es vorher: die Testfixture des
 * Regals erfand ein Feld `project_name`, das das Backend nie geliefert hat,
 * und war deshalb gruen, waehrend die Oberflaeche die rohe Kennung zeigte.
 */
import { describe, expect, it } from 'vitest'

import { ProjectListResponseSchema, ProjectSchema } from '../projectContract'

/** Genau die Schluessel, die `Project.to_dict()` erzeugt. */
const backendPayload = {
  project_id: 'proj_a1b2c3d4e5f6',
  name: 'Testprojekt',
  status: 'graph_completed',
  created_at: '2026-09-01T10:00:00',
  updated_at: '2026-09-02T11:30:00',
  files: [
    {
      original_filename: 'quelle.pdf',
      saved_filename: 'ab12cd34.pdf',
      path: '/uploads/projects/proj_a1b2c3d4e5f6/files/ab12cd34.pdf',
      size: 20481,
    },
  ],
  total_text_length: 4096,
  ontology: { entities: ['Behoerde'] },
  analysis_summary: 'Zusammenfassung',
  graph_id: 'graph_9',
  graph_build_task_id: 'task_7',
  simulation_requirement: 'Wie reagieren Anwohner?',
  chunk_size: 500,
  chunk_overlap: 50,
  llm_model: 'qwen3',
  llm_provider: { provider: 'ollama', api_key_set: true },
  llm_profile_id: 'profile_3',
  ai_model_ref: { connection_id: 'conn_1', model: 'qwen3' },
  error: null,
}

describe('projectContract', () => {
  it('parst die vollstaendige Backend-Antwort strikt', () => {
    const parsed = ProjectSchema.parse(backendPayload)

    expect(parsed.name).toBe('Testprojekt')
    expect(parsed.project_id).toBe('proj_a1b2c3d4e5f6')
  })

  it('kennt kein Feld project_name — das war die Ursache des Regal-Bugs', () => {
    expect(Object.keys(ProjectSchema.shape)).not.toContain('project_name')
    expect(Object.keys(ProjectSchema.shape)).toContain('name')
  })

  it('weist ein unbekanntes Feld ab, statt es durchzureichen', () => {
    // Das ist der Zweck von .strict(): Drift zwischen Backend-Vertrag und
    // Spiegel soll hier auffallen und nicht in der Oberflaeche.
    const result = ProjectSchema.safeParse({
      ...backendPayload,
      project_name: 'erfunden',
    })

    expect(result.success).toBe(false)
  })

  it('akzeptiert nur die Statuswerte, die das Backend-Enum kennt', () => {
    for (const status of [
      'created',
      'ontology_generated',
      'graph_building',
      'graph_completed',
      'graph_incomplete',
      'failed',
    ]) {
      expect(ProjectSchema.safeParse({ ...backendPayload, status }).success).toBe(true)
    }

    // 'completed' gab es nie — useGraphBuildPipeline hat trotzdem dagegen
    // verglichen, bis der Vertrag den Zweig als unerfuellbar auswies.
    expect(ProjectSchema.safeParse({ ...backendPayload, status: 'completed' }).success).toBe(
      false,
    )
  })

  it('parst die Listenantwort', () => {
    const parsed = ProjectListResponseSchema.parse({ projects: [backendPayload] })

    expect(parsed.projects).toHaveLength(1)
  })
})
