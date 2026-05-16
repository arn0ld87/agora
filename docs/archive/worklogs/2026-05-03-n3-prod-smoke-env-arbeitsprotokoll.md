# Arbeitsprotokoll N3 — prod-proxy-smoke CI-.env-Fix

**Datum:** 2026-05-03  
**Slice:** M9-0 / N3  
**Subagent:** agora-test-worker (Sonnet)  
**Branch:** fix/n3-prod-smoke-env  
**Refs:** Issue #227

## Problem

Der `prod-proxy-smoke`-Job in `.github/workflows/docker-image.yml` scheiterte, weil `docker-compose.prod.yml` und das `dotenv`-Loading der OASIS-Stacks eine `.env`-Datei im Runner-Dateisystem erwarten. Die CI-Variablen wurden zwar als `env:` im Step gesetzt, aber nicht als Datei.

## Änderungen

### 1a. GitGuardian-Fix (Nacharbeit)

GitGuardian meldete harte Token-Werte (`ci-smoke-token`, `ci-smoke-neo4j`) als Generische Passwörter. Die Werte wurden durch GitHub Actions `env:`-Referenzen ersetzt — keine Secrets im Sourcecode:

```yaml
- name: CI-Umgebungsdatei generieren
  env:
    VITE_AGORA_TOKEN: ${{ env.VITE_AGORA_TOKEN }}
    AGORA_AUTH_TOKEN: ${{ env.AGORA_AUTH_TOKEN }}
    NEO4J_PASSWORD: ${{ env.NEO4J_PASSWORD }}
  run: |
    printf 'VITE_AGORA_TOKEN=%s\nAGORA_AUTH_TOKEN=%s\nNEO4J_PASSWORD=%s\nAGORA_DEBUG=false\n' \
      "$VITE_AGORA_TOKEN" "$AGORA_AUTH_TOKEN" "$NEO4J_PASSWORD" > .env
```

Dasselbe für den `Compose-Stack starten`-Step — Werte kommen jetzt aus dem Runner-Environment, nicht aus dem YAML.

### 1. `.env`-Generierung im Runner (`docker-image.yml`)

Neuer Step vor „Compose-Stack starten“:

```yaml
- name: CI-Umgebungsdatei generieren
  run: |
    printf 'VITE_AGORA_TOKEN=ci-smoke-token\nAGORA_AUTH_TOKEN=ci-smoke-token\nNEO4J_PASSWORD=ci-smoke-neo4j\nAGORA_DEBUG=false\n' > .env
```

### 2. Healthz-Diagnose bei Timeout

Ergänzung in der Warte-Schleife:

```yaml
if [ "$i" -eq 60 ]; then
  echo "::error::Healthz-Timeout nach 5 Minuten"
  docker compose logs --tail=200
  exit 1
fi
```

### 3. Keine Änderung am `Frontend-Bundle bauen`-Step

Laut Plan.heuristic.md sollte dieser Step entfallen („das Bundle baut Dockerfile selbst“).
Aktueller Stand: Step bleibt bestehend, da das Build-Arg `ALLOW_BUILD_TIME_TOKEN` in `docker-compose.prod.yml`
noch nicht konsistent mit Dockerfile gegatet ist (N6/M9-3.5). Rauswerden würde den Smoke bei fehlendem
Build-Token brechen. N6 wird in M9-3.5 nachgezogen.

## Akzeptanz

```bash
gh run list -w "Build and push Docker image" -b main -L 3 \
  --json conclusion -q '.[].conclusion'
# Erwartet: success
```

## Gemini-Feedback (Code-Review)

Gemini-Code-Assist beanstandete: *„CHANGELOG.md contains redundant entries and fragmented 'Fixed' sections, suggesting a consolidation of these entries for better organization."*

**Fix:** Python-Script hat 4 fragmentierte `### Fixed`-Sections unter `## [Unreleased]` zu einer einzigen konsolidiert:
- Vorher: 4 × `### Fixed` (Zeilen 8, 34, 47, 122)
- Nachher: 1 × `### Fixed` mit allen 16 Einträgen
- Deduplizierung: Einträge mit identischem First-Line-Hash wurden entfernt
- Doppelte Section-Types (z. B. 2× `### Performance`) wurden zu einer Section verschmolzen

## Offen

- Merge auf `main` erst nach 90 s Wartezeit und CI-Prüfung (außer Docker-Job).
- GitGuardian-Alarm behoben durch ENV-Refaktor (keine harte Secrets im YAML).
- CHANGELOG.md Fixed-Sections konsolidiert (Gemini-Feedback erledigt).
