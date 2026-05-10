import type { APIRequestContext } from '@playwright/test';

/**
 * Hochladen einer Markdown-Datei via multipart/form-data an
 * POST /api/graph/ontology/generate.
 *
 * Die Route erwartet:
 *   - files[]         : mindestens eine Datei (Markdown, PDF, TXT — Ext. whitelisted in Config.ALLOWED_EXTENSIONS)
 *   - simulation_requirement : Pflichtfeld (sonst 400)
 *   - project_name    : optional, Default "Unnamed Project"
 *
 * Verifiziert gegen backend/app/api/graph.py::generate_ontology (Zeilen 181–288).
 *
 * @returns Parsed JSON-Body mit { project_id, ontology, ... } aus dem json_success-Envelope.
 */
export async function uploadMarkdown(
  ctx: APIRequestContext,
  body: string,
  filename: string,
  baseURL: string,
  authHeader: Record<string, string>,
): Promise<Record<string, unknown>> {
  // Playwright APIRequestContext hat keine native FormData-API mit Blob-Upload.
  // Wir bauen den multipart-Body manuell via multipart-Option.
  const res = await ctx.post(`${baseURL}/api/graph/ontology/generate`, {
    headers: authHeader,
    multipart: {
      // Schlüssel muss 'files' heissen (getlist('files') in Flask)
      files: {
        name: filename,
        mimeType: 'text/markdown',
        buffer: Buffer.from(body, 'utf-8'),
      },
      simulation_requirement: 'Agora E2E-Smoke — Upload + Graph-Pflichtprüfung',
      project_name: 'e2e-smoke-upload-graph',
    },
  });

  if (!res.ok()) {
    const text = await res.text();
    throw new Error(
      `uploadMarkdown: POST /api/graph/ontology/generate fehlgeschlagen (${res.status()}): ${text}`,
    );
  }

  const json = await res.json();
  // json_success-Envelope: { success: true, data: { project_id, ... } }
  if (!json?.data?.project_id) {
    throw new Error(
      `uploadMarkdown: Antwort enthält kein project_id. Body: ${JSON.stringify(json)}`,
    );
  }
  return json.data as Record<string, unknown>;
}
