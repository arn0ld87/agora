# Sub-Slice 41 — Python 3.14-Bump verworfen (PR #192 → Issue #199)

**Datum:** 2026-05-03
**Layer:** 9 (Production Deployment, Dockerfile)
**Vorgänger:** Sub-Slice 39 (Dependabot aktiviert)

## Was

PR #192 (\`chore(deps)(deps): bump python from 3.11 to 3.14\`) lokal
verifiziert via \`docker compose -f docker-compose.yml build agora\` auf
dem PR-Branch. Build schlägt fehl. PR geschlossen, Followup-Issue #199
angelegt.

## Warum die Verifikation überhaupt nötig

GitHub-CI (\`Backend tests + lint\`) lief auf #192 grün — aber CI nutzt
ein hostedtoolcache-Python 3.11.15, das per \`requires-python = ">=3.11"\`
in pyproject.toml selektiert wird. Die Image-Base-Änderung (3.11 → 3.14)
wird in der CI-Pipeline gar nicht getriggert; der Dockerfile-Build hat
keinen eigenen Workflow-Job. Lokaler Smoke war also Pflicht.

## Was schiefgegangen ist

\`\`\`
help: \`tiktoken\` (v0.7.0) was included because \`agora-backend\` (v0.9.0)
      depends on \`camel-ai\` (v0.2.78) which depends on \`tiktoken\`
error: can't find Rust compiler
\`\`\`

Build-Failure-Stelle: \`Dockerfile:39\` (\`RUN npm ci && uv sync ...\`),
in Stage \`dev 4/5\`.

Root Cause:

- \`tiktoken 0.7.0\` veröffentlicht aktuell keine cp314-wheels auf PyPI.
- pip fällt zurück auf Source-Build → benötigt \`cargo\` / \`rustc\`.
- Docker-Base \`python:3.14\` (debian-trixie) hat keinen Rust-Compiler.
- → \`uv sync\` bricht ab → Image-Layer 4/5 schlägt fehl.

## Optionen (im Followup-Issue dokumentiert)

| Option | Trade-Off | Bewertung |
|---|---|---|
| Warten auf \`tiktoken\` cp314-Wheel | Null Aufwand, time-blocking | präferiert |
| Warten auf \`camel-ai\`-Bump (mit neuer tiktoken-Version) | Hängt zusätzlich an #196 (camel-oasis-Pin) | parallel |
| \`apt install rustc cargo\` ins Dockerfile | Image +~300 MB, Build +5–10 min | letzte Wahl |

## Verifikation

```bash
git fetch origin pull/192/head:pr-192 && git checkout pr-192
docker compose -f docker-compose.yml build agora
# → exit code 1 nach 27.64s in stage [dev 4/5]
# → "error: can't find Rust compiler" für tiktoken-Build
git checkout main && git branch -D pr-192
```

PR #192 geschlossen mit Begründungs-Comment, Issue #199 mit
Re-Evaluation-Bedingungen erstellt.

## Out of Scope

- **Image-Größen-Diff** zwischen 3.11 und 3.14 nicht gemessen — Build
  abgebrochen, bevor erfolgreicher Vergleich möglich war.
- **Rust ins Dockerfile aufnehmen** als Workaround — bewusst nicht
  umgesetzt. Disproportionaler Aufwand für reine Major-Version-Modernisierung,
  die nicht durch ein konkretes Feature getrieben ist.
- **3.12 oder 3.13 als Zwischenschritt** — würde gleich wieder neu
  triggert werden müssen, sobald 3.14 endgültig durchgeht. Aktuell kein
  Vorteil gegenüber 3.11.
