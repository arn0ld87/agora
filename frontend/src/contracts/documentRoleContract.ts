/**
 * Issue #1240: Textsorte eines hochgeladenen Dokuments — Zod-Spiegel von
 * backend/app/contracts/document_manifest_contract.py::DocumentRole.
 *
 * Additiv zu source_kind (ADR-0002 Anker 3 bleibt unberuehrt): source_kind
 * sagt woher, die Rolle welche Art Aussage. scenario_statement, requirement
 * und expected_result stuetzen nie einen Claim.
 *
 * Eigenes Modul, damit der Upload-Dialog nicht den ganzen Report-Contract
 * laden muss.
 */
import { z } from 'zod'

export const DocumentRoleSchema = z.enum([
  'domain_fact',
  'scenario_statement',
  'requirement',
  'expected_result',
  'background',
])
export type DocumentRole = z.infer<typeof DocumentRoleSchema>
