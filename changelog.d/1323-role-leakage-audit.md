### Added (Role-Leakage-Audit für Simulationsaktionen — 2026-09-24)

- **Neues Diagnosewerkzeug erkennt Rollenvertauschungen in Simulationsaktionen:** Personas, die aus einer fremden Rolle schreiben (z. B. Agent „Kaufmännischer Geschäftsführer" schreibt „Aus Sicht des Technischen Dienstes …"), werden durch regelbasierte Mustererkennung identifiziert. Kategorien: `foreign_role` (Treffer auf fremde Persona), `foreign_name_signature` (fremde Namens-Signatur am Ende) und `unmatched_self_reference` (Selbstreferenz ohne Persona-Match, schwächere Kategorie). (#1323)
- **`backend/app/services/sim/role_leakage.py`:** Kernlogik — Muster-Extraktion, Persona-Identitäts-Abgleich (Stamm-/Token-Overlap, Genus-Normalisierung), Ausnahmeliste generischer Phrasen, plattformübergreifender Audit.
- **`backend/app/contracts/role_leakage_contract.py`:** Pydantic-v2-Modelle (`RoleConflict`, `RoleLeakagePlatformSummary`, `RoleLeakageSummary`) mit `extra="forbid"`.
- **`backend/scripts/role_leakage_audit.py`:** CLI — `uv run python scripts/role_leakage_audit.py <sim_dir> [--json out.json] [--max-examples N]`; gibt Summary als Tabelle aus, kein LLM, kein Netzwerk.
- **`docs/runbooks/role-leakage-audit.md`:** Runbook mit Zweck, Aufruf, Ausgabe, Grenzen und Baseline (Lauf `sim_54c1c2a6a875`: 154 texttragende Aktionen, 6 Konflikte, 3,9 %, davon 3 `foreign_role`).
- Kein Gate (Slice 5.2); der Audit ist ein Diagnosewerkzeug ohne automatische Schwelle.
