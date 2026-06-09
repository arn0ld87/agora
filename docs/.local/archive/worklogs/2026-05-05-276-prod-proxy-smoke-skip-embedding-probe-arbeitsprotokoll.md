# Arbeitsprotokoll: Issue #276 — prod-proxy-smoke Embedding-Probe-Skip

Datum: 2026-05-05
Branch: `fix/issue-276-prod-proxy-smoke-skip-embedding-probe`
Subagent: `agora-refactor-worker`

## Symptom

`docker-image.yml::prod-proxy-smoke` crasht im GitHub-Actions-Runner.
Der agora-Container geht in einen Restart-Loop, `/health` ist nie erreichbar,
der Smoke-Job schlägt fehl.

## Root Cause

`backend/app/__init__.py:68` ruft beim App-Start `validate_embedding_configuration()` auf.
Diese Funktion macht einen Live-HTTP-Probe-Call gegen das Embedding-Backend
(Ollama `service.embed("dimension probe")`). Im CI-Runner ist kein Ollama vorhanden —
der Call wirft einen `EmbeddingError`, der zu einem `RuntimeError` wird, und Flask
startet nicht. Der Container restarts endlos.

PR #273 hatte als Workaround `continue-on-error: ${{ github.event_name == 'pull_request' || github.ref_type == 'tag' }}` gesetzt, womit PR-Smokes nur informational waren (M9.6 nicht strict).

## Lösung

**Option (a) aus Issue #276:** Neues env-Flag `AGORA_SKIP_EMBEDDING_PROBE=true`.

### Was geändert wurde

**`backend/app/storage/embedding_service.py`** (Zeilen 20–58):
- `validate_embedding_configuration()` bekommt neuen Parameter `skip_probe: bool = False`
- Return-Typ geändert von `int` auf `Optional[int]`
- Nach der statischen KNOWN_EMBEDDING_DIMS-Validation: `if skip_probe: return None`
- Der `EmbeddingService()`-Konstruktor und `service.embed()`-Call bleiben unberührt,
  werden aber übersprungen wenn `skip_probe=True`

**`backend/app/__init__.py`** (Zeilen 64–83):
- `skip_embedding_probe = os.environ.get('AGORA_SKIP_EMBEDDING_PROBE', 'false').lower() in ('true', '1', 'yes')`
- `validate_embedding_configuration(skip_probe=skip_embedding_probe)`
- Bei aktivem Skip: `logger.warning(...)` auf WARNING-Level (sichtbar in Prod-Log)
- `os` ist bereits importiert (Zeile 5), kein neuer Import nötig

**`.github/workflows/docker-image.yml`**:
- `env:`-Block im `prod-proxy-smoke`-Job: `AGORA_SKIP_EMBEDDING_PROBE: "true"` ergänzt
- `CI-Umgebungsdatei generieren`-Step: `printf`-Format erweitert um `AGORA_SKIP_EMBEDDING_PROBE=%s`,
  damit Compose den Wert in den Container reicht
- `continue-on-error` geändert von
  `${{ github.event_name == 'pull_request' || github.ref_type == 'tag' }}` nach
  `${{ github.ref_type == 'tag' }}` — PR-Smokes sind jetzt strict
- Kommentar-Block aktualisiert: erklärt Skip-Flag, entfernt den alten Workaround-Hinweis

**`docu/STATUS.md`**:
- Layer-9-Zeile: Suffix `als strict PR-Gate dank AGORA_SKIP_EMBEDDING_PROBE`
- Erledigt-Liste M9.6: aktualisiert auf strict + Issue-#276-Referenz
- Aktualisierungs-Protokoll: neuer 2026-05-05-Eintrag

**`CHANGELOG.md`** `[Unreleased] ### Fixed`:
- Neuer Eintrag mit vollständiger Beschreibung der Änderungen

## Was bleibt aktiv

- **Statische KNOWN_EMBEDDING_DIMS-Validation** läuft immer, auch bei `skip_probe=True`.
  Ein Dimension-Mismatch (z.B. VECTOR_DIM=768 mit qwen3-embedding:4b das 2560 erwartet)
  wird als `EmbeddingError` geworfen und blockiert den Start — das ist gewollt.
- Der **EmbeddingError-Pfad** in `__init__.py` bleibt unverändert: jede `EmbeddingError`
  wird zu einem `RuntimeError` und verhindert den App-Start.
- **Default ist `false`** — der Skip ist Opt-in für CI/Smoke, nicht Default.

## Tests

Bestehende 4 Tests in `tests/test_embedding_service.py` bleiben grün (kein `skip_probe`-Argument,
Default `False`, Verhalten unverändert).

3 neue Tests:
1. `test_validate_embedding_configuration_skip_probe_returns_none` — prüft `None`-Return und dass `embed()` nicht aufgerufen wird
2. `test_validate_embedding_configuration_skip_probe_still_rejects_known_dim_mismatch` — Hardstop: statische Dim-Validation läuft auch bei `skip_probe=True`
3. `test_validate_embedding_configuration_default_still_probes` — Regression: ohne `skip_probe` wird `embed()` aufgerufen

Gesamt: 7 Tests in der Datei, alle grün.

## CI-Auswirkung

- **PR-Smokes:** strict (kein `continue-on-error` mehr für `pull_request`)
- **Tag-Smokes:** lenient (`continue-on-error: github.ref_type == 'tag'`) — externe Image-Pulls
  (Neo4j, Ollama) können den Smoke instabil machen, das soll keinen Release blockieren
- **`publish`-Job:** unverändert (`success() || github.ref_type == 'tag'`) — greift jetzt
  auch für PR-merge-Pushes auf main, weil PR-Smokes strict sind

## Folge

M9.6 von informational auf strict: jeder nicht-Doku-PR auf main smoket den vollständigen
Compose-Stack inkl. nginx-Sidecar. Der PR #273-Workaround ist entfernt.
