# Arbeitsprotokoll — Sub-Slice N1: Docker-Push hinter Smoke-Test gaten

**Datum:** 2026-05-04
**Branch:** `fix/n1-docker-publish-order`
**Scope:** `.github/workflows/docker-image.yml`, `docu/deployment-prod-like.md`, `CHANGELOG.md`
**Bearbeiter:** agora-refactor-worker (Claude Sonnet 4.6)

---

## Symptom / Root-Cause

### Symptom

Der Workflow `.github/workflows/docker-image.yml` führte:

1. `build-and-push` — Image mit `push: true` nach Docker Hub + GHCR
2. `prod-proxy-smoke` — End-to-End-Smoke `needs: [build-and-push]`

Jeder fehlgeschlagene Smoke-Test bedeutete: das kaputte Image war bereits
öffentlich unter `latest` und `sha-…` in beiden Registries. Image-Konsumenten
(Self-Hosting, Multi-Contributor) konnten `latest` ziehen, ohne zu wissen,
dass der End-to-End-Smoke rot war.

### Root-Cause

Falscher Job-Abhängigkeitsgraph. `push: true` stand im selben Job wie der
Build, ohne dass eine Smoke-Gate-Bedingung existierte. Das Workflow-Design
behandelte Registry-Push und Smoke-Verifikation als unabhängige Schritte.

---

## Fix

### Drei-Job-Pipeline

`build-and-push` wurde in drei separate Jobs aufgeteilt:

**`build-only`**
- Buildx-Build mit `push: false`
- Image-Tag: `agora-agora:ci-${{ github.sha }}` (deterministisch, kein
  `latest`-Override in dieser Phase)
- Export: `outputs: type=docker,dest=/tmp/image.tar`
- Upload: `actions/upload-artifact@v4`, `retention-days: 1`
- GHA-Cache: `cache-to: type=gha,mode=max` für schnellen Publish-Rebuild

**`prod-proxy-smoke`**
- `needs: [build-only]`
- `continue-on-error: ${{ github.ref_type == 'tag' }}`
- Download: `actions/download-artifact@v4`
- Image laden: docker load -i image.tar
- Umtaggen: docker tag agora-agora:ci-${{ github.sha }} agora-agora:latest
  (Compose erwartet `agora-agora:latest`, weil Projektname `agora` +
  Service `agora` → Default-Image-Name ohne `--build`)
- `docker compose ... up -d` ohne `--build`
- Rest des Smoke-Jobs bleibt unverändert

**`publish`**
- `needs: [prod-proxy-smoke]`
- `if: github.event_name != 'pull_request' && (success() || github.ref_type == 'tag')`
- Erneuter Buildx-Build mit `cache-from: type=gha` (praktisch instant)
- `push: true` — einziger Ort im Workflow mit Push-Berechtigung
- Tags: `${{ steps.meta.outputs.tags }}` (identisch zu vorher)

### Artefakt vs. Cache-only

`actions/upload-artifact` wurde gegenüber dem reinen Buildx-GHA-Cache-
Ansatz bevorzugt:

- **Deterministisch:** Das Artefakt ist explizit benannt und referenzierbar.
  Cache-Keys können bei parallelen Workflow-Runs auf demselben SHA
  kollidieren oder sich gegenseitig überschreiben.
- **Auditierbar:** `docker load` ist ein expliziter, sichtbarer Schritt.
  Cache-only-Ansätze laden das Image implizit beim Build-Step — schwerer
  zu debuggen bei Fehlern.
- **Unabhängig von Cache-Verfügbarkeit:** Ein Cache-Evict (z. B. nach
  10 Tagen Inaktivität oder bei Cache-Overflow) würde den Smoke-Job zum
  Rebuild zwingen — mit falschen Tags. Das Artefakt ist für den
  Workflow-Run garantiert verfügbar.

Der GHA-Cache bleibt trotzdem aktiv (`cache-from`/`cache-to`) für den
Publish-Rebuild — dort ist der Cache-miss-Fallback akzeptabel (voller
Build, selbes Ergebnis).

### Tag-Push-Override

Bei `tag`-Pushes (Releases) kann der Smoke durch externe Abhängigkeiten
instabil werden (Neo4j-Image-Pull-Rate-Limits, Ollama-Verfügbarkeit auf
GitHub-Hosted-Runnern). `continue-on-error: ${{ github.ref_type == 'tag' }}`
verhindert, dass ein instabiler Infrastructure-Smoke einen Release blockiert.

`main`-Pushes haben keinen `continue-on-error` — sie sind strikt
smoke-gated. Das ist die kritische Invariante: was unter `latest` geht,
hat einen grünen End-to-End-Smoke bestanden.

---

## Betroffene Dateien

| Datei | Art | Änderung |
|---|---|---|
| `.github/workflows/docker-image.yml` | geändert | `build-and-push` → 3 Jobs (`build-only`, `prod-proxy-smoke`, `publish`) |
| `docu/deployment-prod-like.md` | geändert | Neuer Abschnitt "Release-Pipeline (CI/CD)" |
| `CHANGELOG.md` | geändert | `[Unreleased] ### Fixed` Eintrag |
| `docu/2026-05-04-n1-docker-publish-order-arbeitsprotokoll.md` | neu | dieses Protokoll |

---

## Akzeptanz-Checks

```
# needs: [build-only] im prod-proxy-smoke-Job
grep -A2 "prod-proxy-smoke:" .github/workflows/docker-image.yml | head -5
→ needs: [build-only]

# needs: [prod-proxy-smoke] im publish-Job
grep -A2 "publish:" .github/workflows/docker-image.yml | head -5
→ needs: [prod-proxy-smoke]

# Exakt ein push: true im gesamten Workflow
grep -c "push: true" .github/workflows/docker-image.yml
→ 1

# YAML-Syntax valide
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/docker-image.yml'))"
→ kein Fehler
```

---

## Verify

- Keine Backend-/Frontend-Dateien angefasst.
- `cd backend && uv run python -m app.contracts.dump_schemas && cd ..`
  → keine Schema-Drift (`git diff --exit-code schemas/`)
- `cd backend && uv run pytest -x -q` → alle Tests weiterhin grün

---

## Gemini-Findings (Pflicht-Tracking nach PR)

Nach `gh pr create` → 90 s warten → Findings sichten gemäß CLAUDE.md PR-Workflow.
