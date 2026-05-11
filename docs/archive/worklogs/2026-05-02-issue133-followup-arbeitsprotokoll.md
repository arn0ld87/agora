# Issue #133 Followup — Gemini-Findings auf PR #155

**Datum:** 2026-05-02
**Branch:** `claude/issue-133-followup`
**Bezug:** PR #155 (`feat(settings): runtime .env override layer + UI`) — gemerged 2026-05-02 04:45 UTC; Gemini-Code-Assist hat in der Review drei Findings hinterlassen (1× High, 2× Medium), GitGuardian zusätzlich 10 Triggered-Findings auf Test-Fixtures.

## Findings im Original-PR

| Quelle | Schwere | Datei | Befund |
|---|---|---|---|
| Gemini | **High** | `backend/app/services/settings_validator.py:178` | Cross-Field-Check `EMBEDDING_MODEL` ↔ `VECTOR_DIM` greift nur bei beiden Feldern im selben Payload. Partial-Update lässt Mismatch durch. |
| Gemini | Medium | `backend/app/services/settings_layer.py:355` | `os.replace` außerhalb des `with`-Blocks → bei Fehler in `json.dump`/`fsync` bleibt `settings.*.json.tmp` zurück. |
| Gemini | Medium | `backend/app/services/settings_validator.py:114` | Error-Message für `null` verspricht „Default-Restore via Weglassen" — `apply_payload` macht aber Merge-Update. |
| GitGuardian | — | 4 Test-Files | 10 Generic-Password-Hits auf synthetische Test-Marker (`new-pw`, `tok-xyz`, `super-secret`). |

## Sub-Slices

Workflow: pro Sub-Slice 1 Commit, `npm run check` als Gate, kein Doku-Bruch.

### SUB1 — Validator state-aware + Wording-Fix (Commit `70c4ecd`)

**Änderung:**
- `validate_payload(...)` bekommt optionalen `effective_settings: Mapping[str, Any] | None`-Parameter.
- `_check_embedding_consistency(validated, effective)` merged `effective` unter und `validated` darüber, prüft die Konsistenz, sobald **mindestens** eines der beiden Felder im Payload liegt. Wenn keines im Payload ist, bleibt der Bestand-Mismatch außerhalb der Verantwortung dieses PUT.
- Neuer `SettingsService.effective_snapshot()` liefert `{key: effective_value}` für alle non-secret Felder inkl. Defaults — der API-Layer reicht das Dict in den Validator.
- Wording-Fix in `_coerce_string`: `null als Wert nicht erlaubt — Feld weglassen, um den Default wiederherzustellen` → `null als Wert nicht erlaubt`. Der irreführende Default-Hinweis ist raus; ein expliziter Reset-Endpoint wäre Scope für ein Folgeticket.

**Neue Tests:**
- `test_validate_rejects_partial_update_against_effective_state` — Partial-Update mit nur `EMBEDDING_MODEL` (oder nur `VECTOR_DIM`) gegen mismatching effective-state → `vector_dim_mismatch`.
- `test_validate_partial_update_passes_with_matching_effective_state` — Symmetrische Positiv-Kontrolle.
- `test_validate_skips_cross_field_when_pair_not_involved` — Wenn kein Pair-Feld im Payload, kein Cross-Field-Error trotz mismatching effective state.
- `test_put_settings_rejects_partial_update_against_persisted_state` — End-to-End-Pin via Test-Client: setzt persisted Stand via `apply_payload`, schickt PUT mit nur `EMBEDDING_MODEL`, prüft 400 + unveränderten Persisted-State.
- `test_effective_snapshot_*` (3 Cases): Snapshot-Verhalten — Secrets ausgenommen, Defaults enthalten, Overrides reflektiert.

### SUB2 — Atomic-Write try/finally + tmp-Cleanup (Commit `8ff134b`)

**Änderung:**
- `_write_file_layer_atomic` in `settings_layer.py` packt den Schreibpfad in ein `try/finally`. Im Erfolgsfall (nach `os.replace`) wird `tmp_path = None` gesetzt, sodass der `finally`-Cleanup keine bereits weggerenamte Datei mehr unlinken versucht. Im Fehlerfall (Exception in `json.dump`/`fsync`) räumt `finally` die Tempdatei ab.
- Inneres `try/except OSError: pass` für den Cleanup selbst — wenn auch das Aufräumen scheitert, wird der Original-Fehler durchgereicht.

**Neuer Test:**
- `test_atomic_write_cleans_up_tmp_on_failure` — Monkeypatch auf `json.dump` schreibt einen Teil-Inhalt und wirft anschließend `RuntimeError`. Erwartet: Exception propagiert, kein `settings.*.json.tmp` im Verzeichnis, Ziel-Datei existiert nicht.
- Der bestehende `test_apply_payload_no_tmp_left_behind_on_success` bleibt grün und sichert den Happy-Path.

### SUB3 — GitGuardian-Pfadignore für Test-Fixtures (Commit `2b0619a`)

**Änderung:**
- Neue [`.gitguardian.yaml`](../.gitguardian.yaml) (Schema `version: 2`) listet die vier betroffenen Test-Files explizit unter `secret.ignored-paths`:
  - `backend/tests/test_settings_validator.py`
  - `backend/tests/test_settings_api.py`
  - `backend/tests/test_settings_persistence.py`
  - `frontend/src/store/__tests__/settings.spec.js`
- Production-Code (`backend/app/services/settings_schema.py` u. a.) bleibt voll im Scan. Begründung als Comment im YAML: synthetische Test-Marker, keine echten Credentials, in einem öffentlichen Test-Suite-Lauf bekannt.

## Quality-Gate

`npm run check` grün auf Sub-Slice-Ende für jeden Commit.

- **Backend:** 122 Settings-Tests grün (vorher 121 + 1 SUB1 + 1 SUB2 vs. doppelter Layer-Add). Volle Suite hat fünf bekannte Failures auf `origin/main` (`test_ontology_generator.*` wegen fehlender `LLM_API_KEY` im Worktree-Env, `test_report_claim_model_keeps_legacy_fields_and_numeric_score` wegen Float-Drift `0.6 != 0.65`); reproduzierbar auf `git stash`-Stand und außerhalb meiner Scope.
- **Backend-Lint:** `ruff check app/ tests/` clean.
- **Frontend:** `vitest run` grün, `vue-tsc` ohne neue Warnings, Build 124 KB CSS / 537 KB JS unverändert.

## Out of Scope (Folge-Ticket-Kandidaten)

- **Reset-auf-Default-Endpoint.** Der überarbeitete Wording-Hinweis macht klar, dass `null` im Payload kein Default-Reset auslöst. Ein expliziter `DELETE /api/settings/<key>` (oder `null` als Reset-Sentinel) ließe sich nachziehen — heute existiert nur `service.remove_persisted([...])` als Service-Methode ohne Route.
- **Effective-Snapshot für Secrets.** Aktuell schließt `effective_snapshot()` Secrets aus, weil keine Cross-Field-Regel auf Secrets greift. Falls eine künftige Regel zwei Secrets miteinander vergleichen muss, braucht der Snapshot einen zweiten `include_secrets=True`-Pfad — bewusst nicht vorweggenommen.
