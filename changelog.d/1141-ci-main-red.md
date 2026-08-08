### Fixed (CI auf main wieder grün — 2026-08-08)

- **Ruff E101 in `backend/scripts/_sim_common.py`:** Sechs Docstring-Zeilen mit Tab-Einrückung (eingeschleppt via #1136) durch Spaces ersetzt; der push-Job auf main lintet das ganze Backend und schlug deshalb fehl, obwohl das PR-Gate grün war.
- **Ruff-Scope-Lücke geschlossen:** PR-Smoke-Gate (`ci.yml`) und `scripts/pre-push-gate.sh` linten jetzt wie der main-Job `ruff check .` statt nur `app/ tests/` — `scripts/` fällt nicht mehr durch die Lücke.

### Security (Frontend-Dependency-Audit — 2026-08-08)

- **`bun audit --audit-level=high` wieder grün:** Neue High-Advisories gegen axios, brace-expansion, nanoid, postcss und undici behoben — Lockfile frisch aufgelöst, Overrides auf nanoid ≥3.3.18, postcss ≥8.5.26 und undici ≥7.29.0 angehoben.
