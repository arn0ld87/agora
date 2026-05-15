# Issue #450 Härtungs-Roadmap — Arbeitsprotokoll

**Datum:** 2026-05-15
**Branch:** `feat/issue-450-hardening-batch` (Worktree: `/private/tmp/agora-issue-450`)
**Issue:** [#450 roadmap: Agora von 8.3/10 auf 10/10 härten](https://github.com/arn0ld87/agora/issues/450)

---

## Strategie

User-Ansage: *„löse den issue selbstständig und vollständig — keine CI
tests bei github bis zum schluss"*. Umsetzung als sechs Slices (A–F) in
einem Worktree, sechs lokale Commits, **ein PR am Ende** mit
Gemini-Findings-Sichtung. Lokale Gates pro Slice
(`pytest`/`ruff`/`mypy`).

Issue #450 hat 11 nummerierte Punkte. Drei davon sind Policy-Switches
oder upstream-blockiert und gehören **nicht** in einen Pflicht-Roll-out
ohne separates Sign-off:

- Punkt 5 (Trivy blocking): aktuelle SARIF-Findings müssen vorab
  ausgewertet und gegen Fix/Risk-Akzeptanz gehalten werden. Eigener
  Issue #359 bleibt.
- Punkt 6 (harden-runner Block-Modus alle Jobs): pro Job ein
  Egress-Audit nötig; CI kann reihenweise brechen ohne saubere
  Allowlists. Eigener Issue #358.
- Punkt 7 (CVE-Baseline schließen): `camel-oasis==0.2.5`-Pin und
  `transformers`/`unstructured`-CVEs sind upstream-blockiert. Hardstop
  in `.github/workflows/cve-monitor.yml` läuft scharf. Issues #124/#126
  bleiben.

Punkt 10 (Observability-Ausbau) ist eigenes Epic-Format. Punkt 9
(Schema-Drift-Gate) ist bereits durch `contract-gates.yml` grün.

---

## Slice-Status (Punkte des Issues)

| Punkt | Akzeptanzkriterium | Slice | Status |
|---|---|---|---|
| 1 | PR #443 mergen + `/api/status` ohne `_driver`-Zugriff | — | **DONE** vor PR (Pre-Existing) — #443 ist gemerged, Tests `test_neo4j_fork`, `test_status` decken Fork-Reset ab. |
| 2 | `WorkspaceRoutingStore` mit `fcntl.flock` | **A** | **DONE** — `backend/app/services/workspace_routing_store.py` nutzt jetzt `fcntl.LOCK_EX` über die gesamte read-modify-write-Sequenz. Multi-Process-Test mit 7 echten subprocess-Workern grün. |
| 3 | `backend/data` persistent + 0600 + Backup-fähig | **B** | **DONE** — Volume-Mount in `docker-compose.yml`, 0600-Patch in `LlmProviderSecretsStore._write_raw`, `verify-deploy.sh`-Probe, `backup-restore.md`-Section, `.gitignore` schließt `backend/data/*` aus + entfernt versehentlich getrackten Production-Ciphertext aus dem Index. |
| 4 | `AGORA_SECRET_KEY` Lifecycle + Doctor-Script | **C** | **DONE** — `scripts/llm-secrets-doctor.py` (status/verify/rotate), 10 Tests, `docu/secret-key-lifecycle.md` mit Generate/Store/Rotate/Recover. |
| 5 | Trivy `exit-code: "1"` | — | **OUT OF SCOPE** dieses PRs. Issue [#359](https://github.com/arn0ld87/agora/issues/359) offen. |
| 6 | harden-runner Block-Modus alle Jobs | — | **OUT OF SCOPE** dieses PRs. Issue [#358](https://github.com/arn0ld87/agora/issues/358) offen. |
| 7 | CVE-Baseline schließen bis 2026-07-30 | — | **UPSTREAM-BLOCKED**. Issues [#124](https://github.com/arn0ld87/agora/issues/124)/[#126](https://github.com/arn0ld87/agora/issues/126) offen, Hardstop in `cve-monitor.yml` aktiv. |
| 8 | Prod-like E2E-Smoke | **D** | **TEILWEISE** — `scripts/verify-deploy.sh --full` deckt Provider-Setup → Routing → Restart-Persistenz + Secret-Scan vollständig ab. Document-Upload → Graph-Build → Persona → Simulation → Report-Run bleibt einem Followup-Issue vorbehalten (braucht einen sauber durchsteuernden `AGORA_E2E_LLM_MODE=stub`-Pfad durch den Report-Agent-ReACT-Loop). |
| 9 | Schema-Drift-Gate | — | **DONE vor PR** — `contract-gates.yml::dump-and-diff` läuft. |
| 10 | Observability-Ausbau | — | **OUT OF SCOPE** dieses PRs. Eigenes Epic. |
| 11 | `docu/operator-guide.md` | **E** | **DONE** — vollständige Operator-Anleitung inkl. Querverweisen aus `docu/README.md`. |

**Erledigt im PR:** Punkte 2, 3, 4, 8 (teilweise), 11.
**Aus dem PR ausgenommen mit Begründung:** Punkte 1 (war schon DONE), 5, 6, 7, 9 (war schon DONE), 10.

---

## Slice-Detail

### Slice A — fcntl.flock im WorkspaceRoutingStore

Commit `cd3806d`.

- `WorkspaceRoutingStore._file_lock` als Contextmanager mit
  `fcntl.LOCK_EX` auf `<store>.lock`.
- `save`, `set_stage_override`, `set_global_default` umschließen Load
  und Save unter demselben File-Lock.
- `_save_unlocked` setzt 0600 + warnt bei chmod-Fehlern.
- Tests:
  - `test_parallel_processes_no_lost_update`: 7 echte subprocess-Worker
    schreiben disjunkte Stage-Overrides via `set_stage_override`.
    Vorher (nur `threading.Lock`): einzelne Updates gingen verloren.
    Jetzt: alle 7 sind persistiert.
  - `test_concurrent_threads_no_lost_update`: deckt Thread-Lock-Pfad
    parallel ab.
  - `test_save_creates_lock_sidecar`, `test_save_sets_restrictive_permissions`.
  - `test_corrupt_json_is_logged_and_replaced_safely`: ERROR-Log via
    direktem `_ListHandler` (Modul-Logger hat `propagate=False`).

Gates: pytest 11/11, ruff/mypy clean.

### Slice B — backend/data Persistenz + 0600 + .gitignore

Commit `3b8bf5c`.

- `docker-compose.yml`: neuer Mount `./backend/data:/app/backend/data`.
  `docker-compose.prod.yml` erbt per Compose-Merge.
- `LlmProviderSecretsStore._write_raw` setzt 0600 nach `os.replace`
  (chmod-Fehler werden geloggt statt zu crashen, NFS-Edge-Case).
- `scripts/verify-deploy.sh`: neue Sektion „P450-3 (backend/data
  Persistenz)" mit Schreibrechte-Probe + Mode-0600-Probe.
- `docu/backup-restore.md`: neue Asset-Zeile „Multi-Provider-Hub-Daten",
  AGORA_SECRET_KEY-Verlustwarnung, Restic-Beispiel, Restore-Reihenfolge,
  Host-UID-Hinweis.
- `.gitignore`: `backend/data/*` mit Ausnahme `.gitkeep`.
- **Sicherheitsfix als Beifang:** `backend/data/llm_provider_secrets.json`
  und `.lock` waren auf main getrackt (mit produktivem Fernet-Ciphertext).
  Per `git rm --cached` aus dem Index entfernt; Dateien bleiben lokal
  erhalten. **Pending:** AGORA_SECRET_KEY-Rotation in produktiven
  Deployments (siehe Doctor-Script Slice C). Force-Push-History-Rewrite
  ist eine User-Entscheidung und kein Slice.

### Slice C — Secret-Key Lifecycle + Doctor-Script

Commit `ceafd77`.

- `scripts/llm-secrets-doctor.py` (executable):
  - `status`: `AGORA_SECRET_KEY` valid? Welche Provider sind gespeichert?
  - `verify`: Decrypt-Roundtrip pro Eintrag (Klartext bleibt im Memory).
  - `rotate --old-key-env <X> --new-key-env <Y>`: Re-Encrypt aller
    Einträge mit neuem Fernet-Key. Niemals Keys als CLI-Argument.
  - Exit-Codes: 0 ok / 1 Konfig / 2 Roundtrip.
  - Importiert `app.services.llm_provider_secrets_store` aus dem
    Backend-venv (Aufruf via `uv run --project backend python …`).
- `backend/tests/scripts/test_llm_secrets_doctor.py`: 10 Tests
  (status/verify/rotate × Success + Failure + Edge-Cases). Klartext-Keys
  landen in keinem Test in stdout/stderr.
- `docu/secret-key-lifecycle.md`: Generate, Store-Optionen (.env,
  pass, systemd-CredentialsLoad, Vault), Routine-Check, Rotation-Ablauf,
  Verlust-Verhalten mit Recovery-Pfad.

### Slice D — Prod-like Persistenz-Smoke

Commit `b626dbc`.

- `scripts/verify-deploy.sh --full`-Flag mit vier Phasen:
  1. Provider-Setup + Routing schreiben (PUT
     `/api/llm/providers/openai/api-key`, PUT
     `/api/llm/routing/defaults/global`).
  2. `docker compose restart agora` + Health-Wait (max 60 s).
  3. Persistenz-Verifikation: Provider-Maske + Routing-Default sind
     nach Restart noch da.
  4. Secret-Scan: `grep -rE` des Smoke-Keys in `/app/backend/{data,instance}`
     außer `llm_provider_secrets.json`. Treffer = Fail.
- Cleanup: Smoke-Provider-Key wird per DELETE wieder entfernt.
- Bewusst NICHT: vollständiger Document → Graph → Persona → Simulation
  → Report-Run mit `AGORA_E2E_LLM_MODE=stub`. Das gehört in einen
  eigenen CI-Smoke + eigenen Followup-Issue.

### Slice E — Operator-Guide

Commit `079136e`.

- `docu/operator-guide.md` (7 Sektionen + DoD-Checkliste):
  Voraussetzungen, Initial-Install, Provider-Key-Verwaltung,
  Backup/Restore, Update-Prozess, Fehlerdiagnose, Security-Hinweise.
- `docu/README.md` bekommt einen Abschnitt „Betrieb (Operator)" mit
  Direktlinks auf den Guide + die drei Quer-Files (Secret-Key-Lifecycle,
  Backup-Restore, Deployment-Prod-Like).
- `/docs/` ist via `.gitignore` ausgeschlossen — der Guide liegt nach
  Repo-Konvention unter `/docu/`.

### Slice F — Dieses Worklog + PR

Commit dieser Datei + `gh pr create` (folgt im nächsten Schritt).

---

## Followups (separate Issues)

| Followup | Auslöser | Empfohlene Aktion |
|---|---|---|
| AGORA_SECRET_KEY rotieren in Production | Slice B Sicherheitsfix: Production-Ciphertext lag historisch auf main | Operator führt `scripts/llm-secrets-doctor.py rotate` einmalig aus und aktualisiert `.env`. |
| Git-History tilgen | Production-Ciphertext liegt weiter in alten Commits auf main | Eigenständige Security-Action mit Force-Push (`git filter-repo`-Pfad). User-Entscheidung. |
| Vollständiger E2E-Smoke mit Stub-LLM | Issue #450 P1.8 verlangt mehr als nur Persistenz | Neuer Issue für CI-Job mit `AGORA_E2E_LLM_MODE=stub` und Document-Upload → Report-Export. |
| Trivy auf blocking schalten | Issue #359 | Nach SARIF-Baseline-Audit. |
| harden-runner Block-Modus | Issue #358 | Nach Egress-Profil-Audit pro Job. |
| CVE-Baseline | Issues #124/#126 | Hängt an Upstream-Patch für `camel-oasis`/`transformers`. |
| Observability-Ausbau | Issue #450 P2.10 | Eigenes Epic. |

---

## Lokale Gates (am Ende)

```bash
# Backend
cd /private/tmp/agora-issue-450/backend
uv run pytest tests/services/test_workspace_routing_store.py \
              tests/services/test_llm_provider_secrets_store.py \
              tests/scripts/test_llm_secrets_doctor.py -v
# → 31/31 grün

uv run ruff check app/services/workspace_routing_store.py \
                  app/services/llm_provider_secrets_store.py \
                  tests/services/test_workspace_routing_store.py \
                  tests/scripts/test_llm_secrets_doctor.py
# → clean

uv run mypy app/services/workspace_routing_store.py \
            app/services/llm_provider_secrets_store.py
# → Success
```
