# Troubleshooting — bekannte Fehlerbilder

**Status:** Referenz zu `0.8.0`. Symptom → Ursache → Behebung → Referenz. Für Fehlercodes und HTTP-Status siehe [`api-contracts.md`](api-contracts.md); für Konfiguration [`configuration.md`](configuration.md).

---

## Datenbank & Infrastruktur

### Neo4j nicht erreichbar (`503 neo4j_unavailable`)
- **Symptom:** `neo4j_unavailable`, Verbindungs-Timeouts, Graph-Operationen schlagen fehl.
- **Ursache:** `NEO4J_URI`/`NEO4J_USER`/`NEO4J_PASSWORD` falsch, Neo4j nicht gestartet, Netzwerk/Tailscale nicht verbunden.
- **Behebung:** Neo4j-Container/Service prüfen, Credentials verifizieren, Pool-Timeouts (`NEO4J_ACQ_TIMEOUT`) ggf. erhöhen.
- **Referenz:** [`api-contracts.md`](api-contracts.md), [`deployment-dev.md`](deployment-dev.md).

### Redis nicht erreichbar (`503 service_unavailable`)
- **Symptom:** Event-Bus-/Status-/IPC-Ausfälle, Simulation blockiert.
- **Ursache:** `REDIS_URL` falsch, Redis nicht gestartet.
- **Behebung:** Redis-Verbindung prüfen, `EVENT_BUS_BACKEND` und `TEST_REDIS_URL` für Tests.
- **Referenz:** [`configuration.md`](configuration.md).

## Provider & LLM

### LLM `401 auth_invalid` / unautorisierte Calls
- **Symptom:** LLM-Calls schlagen mit 401 fehl, obwohl ein Provider konfiguriert ist.
- **Ursache:** Legacy-`llm_profile_id`-Vorrang — der Ingest-Pfad umgeht die Connection-Route über einen Legacy-Profil-Key und greift auf veraltete/fehlende Secrets zu.
- **Behebung:** Provider über `ProviderConnection` und kanonische Routing-Werte konfigurieren, Legacy-Profile nicht bevorzugt nutzen. PR #755 fixt einen Nebenbefund, der Hauptpfad ist noch offen.
- **Referenz:** [`provider-runtime-settings.md`](provider-runtime-settings.md), [`../backend/app/llm/providers/registry.py`](../backend/app/llm/providers/registry.py)::`detect_provider`, Issue #803.

### Embedding-Dim-Drift
- **Symptom:** Vektor-Index-Fehler nach Embedding-Modell-Wechsel, Dimensions-Mismatch.
- **Ursache:** `VECTOR_DIM` passt nicht zum neuen Modell; bestehende Indexe werden nicht automatisch migriert (`IF NOT EXISTS`-Falle).
- **Behebung:** über den Migrations-Lifecycle (`EmbeddingMigrationService`: `pending → running → validating → completed | failed | rolled_back`) wechseln — der alte Index bleibt bis zur erfolgreichen Validierung erhalten und sichert den Rollback-Pfad. Dimensions-Mismatch und `IF NOT EXISTS`-Falle werden *innerhalb* dieses Pfads gelöst, nicht durch ein vorabiges manuelles `DROP INDEX` (ADR-0007 verbietet das, bis Backup, Validierung und Rollback gesichert sind). Gemini-Re-Embedding wird derzeit *nicht* unterstützt.
- **Referenz:** [`embedding-provider-switch.md`](embedding-provider-switch.md), [ADR-0007](decisions/0007-embedding-configuration-and-index-migration.md), Issue #263.

## Simulation & Report (Workflow-Konflikte 409)

### `simulation_not_prepared` (409, teils 404)
- **Behebung:** `POST /api/simulation/prepare` ausführen, dann `prepare/status` abwarten.

### `persona_review_required` (409)
- **Behebung:** Persona-Review abschließen (`PERSONA_REVIEW_ENABLED`), bevor die Simulation startet.

### `simulation_already_running` / `graph_build_in_progress` (409)
- **Behebung:** laufenden Run abwarten oder stoppen; keinen parallelen Start erzwingen.

### OASIS-Agenten reagieren nicht / bleiben stumm
- **Symptom:** Simulation läuft, aber Agenten erzeugen keine nutzbaren Beiträge.
- **Ursache:** Provider-/Modell-/Prompt-Konfiguration, zu kleine Modelle, `OLLAMA_THINKING`/`num_ctx`-Gate.
- **Behebung:** leistungsfähigeres Modell wählen, Provider-Detection via Registry verifizieren, Lessons-Learned-Protokoll beachten.
- **Referenz:** [`2026-07-18-sim-agenten-stumm-arbeitsprotokoll.md`](2026-07-18-sim-agenten-stumm-arbeitsprotokoll.md), [`2026-07-18-lessons-learned-provider-key-routing.md`](2026-07-18-lessons-learned-provider-key-routing.md).

## Betrieb & Sicherheit

### Fork-Safety / `gunicorn --preload` schlägt fehl
- **Symptom:** Worker-Crashes nach Fork, Neo4j-/Redis-Pool-Korruption.
- **Ursache:** DB-Pools nicht fork-safe.
- **Behebung:** `os.register_at_fork` an den Pools (MAI-12) aktiviert `--preload` für schnelleren Startup.
- **Referenz:** [`operations.md`](operations.md), [`deployment.md`](deployment.md).

### Secret-Key / Fernet-Key Rotation
- **Symptom:** entschlüsselte Secrets ungültig nach Key-Wechsel.
- **Behebung:** `AGORA_FERNET_KEY`/`SECRET_KEY` nach Lebenszyklus rotieren, alte Werte bis zur Migration behalten.
- **Referenz:** [`secret-key-lifecycle.md`](secret-key-lifecycle.md).

### CVE-Hardstops
- **Symptom:** Dependency-Scan schlägt fehl, Build blockiert.
- **Ursache:** offene CVE-Ausnahmen mit abgelaufener Frist.
- **Behebung:** Hardstops beachten — NLTK 28.09.2026, Trivy 30.08.2026; neue Ausnahmen brauchen Issue, Owner, Deadline und Hardstop.
- **Referenz:** [`dependency-risk-register.md`](dependency-risk-register.md).

### `ImportError: Blocked import of regex from current working directory`
- **Symptom:** Ingestion bzw. Dokument-Parsing bricht mit `ImportError: Blocked import of regex …` oder `… of defusedxml …`. Tritt zur Laufzeit auf, nicht beim Build.
- **Ursache:** nltk ≥ 3.10 installiert einen Import-Hook, der von nltk ausgelöste Imports unterhalb des Arbeitsverzeichnisses blockiert. Liegt die venv unter dem CWD (`cd backend && …`, im Container `WORKDIR /app` mit `/app/backend/.venv`), gilt jedes venv-Paket als „aus dem CWD".
- **Behebung:** `NLTK_DISABLE_IMPORT_SECURITY=1` setzen. `backend/app/__init__.py` tut das bereits für jeden Einstieg, der `app` importiert (`run.py`, gunicorn, Skripte), das Dockerfile zusätzlich als ENV, `conftest.py` für die Testsuite. Selbst setzen muss man es nur, wenn nltk ohne `app`-Import angefasst wird — etwa in einem nackten `python -c`. `PYTHONSAFEPATH=1` hilft **nicht**, obwohl die Fehlermeldung es vorschlägt.
- **Referenz:** [`dependency-risk-register.md`](dependency-risk-register.md), Abschnitt „nltk-Baseline".

## Upload & E2E

### `upload_too_large` (413) / `unsupported_format` (400)
- **Behebung:** `AGORA_MAX_UPLOAD_SIZE_MB` erhöhen bzw. unterstütztes Format verwenden.

### E2E-LLM-Calls in CI fake/skip
- **Behebung:** `AGORA_E2E_LLM_MODE` (z. B. `stub`, `compact`) korrekt setzen; `AGORA_SKIP_PREFLIGHT` nur gezielt.
- **Referenz:** [`testing/`](testing/), [`runbooks/pre-push-gate.md`](runbooks/pre-push-gate.md).