# Contributing — Agora

Agora ist ein experimentelles Open-Source-Projekt unter AGPL-3.0. Diese Datei erklärt Repository-Struktur, Branch-Hygiene und Qualitäts-Gates.

## Dokumentationsrollen

| Quelle | Zweck |
|---|---|
| [`README.md`](README.md) | Produkt, Installation, Grenzen und Release-Linie |
| [`docs/STATUS.md`](docs/STATUS.md) | verifizierter Istzustand, Tests, Gates und bekannte Schuld |
| [`ROADMAP.md`](ROADMAP.md) | strategische Release-Ziele von `0.8.0` bis `1.0.0` |
| [GitHub Issues](https://github.com/arn0ld87/agora/issues) | konkrete Tasks, Akzeptanzkriterien, Owner und Abhängigkeiten |
| [`CHANGELOG.md`](CHANGELOG.md) | ausgelieferte Änderungen |
| [`docs/decisions/`](docs/decisions/) | Architekturentscheidungen |
| [`docs/runbooks/`](docs/runbooks/) | operative Abläufe |
| [`docs/archive/planning/`](docs/archive/planning/) | historische, nicht mehr aktive Planung |

Neue parallele Planungsdateien sind nicht erwünscht. Ein Task ohne GitHub Issue ist keine verbindliche Roadmap-Arbeit.

## Release-Scope prüfen

Vor Beginn einer Änderung prüfen:

1. Gehört sie zum aktuellen Release-Ziel in `ROADMAP.md`?
2. Existiert ein Issue mit Scope und Akzeptanzkriterien?
3. Berührt sie Verträge, Migrationen, Security oder Evidence-Gating?
4. Welche Tests müssen vor der Implementierung fehlschlagen?

Größere neue Produktbereiche, Multi-User-Funktionen, ein React-Rewrite, Helm/Federation oder ein allgemeines Plugin-System liegen vor `1.0.0` außerhalb des Scopes.

## Branch- und PR-Hygiene

1. Nie direkt auf `main` arbeiten.
2. Branch-Namen beschreiben Typ und Scope, zum Beispiel:
   - `fix/e2e-upload-graph`
   - `refactor/provider-routing-ssot`
   - `docs/release-line-and-status`
3. Ein Pull Request behandelt einen atomaren fachlichen Slice.
4. Der PR beschreibt Scope, Out-of-Scope, Tests, Migration und Rollback, sofern relevant.
5. Keine Skips, abgeschwächten Assertions oder pauschalen Retries als Ersatz für Fehlerbehebung.
6. Kein `--no-verify` ohne ausdrückliche Freigabe.

## Pflicht-Gates auf Pull Requests

| Job | Inhalt |
|---|---|
| Backend PR Gate | Ruff, Mypy und Contract-Tests |
| Frontend PR Gate | ESLint, Typecheck, Unit-Tests und Build |

Die E2E-Kernpipeline ist aktuell noch kein Required Check. Ihre Aktivierung ist Teil des `0.9.0`-Release-Gates.

## Heavy-Gates

| Job | Trigger |
|---|---|
| Backend Full Tests + Coverage | `push:main` oder Label `needs-backend-ci` |
| Frontend Full Tests + Coverage | `push:main` oder Label `needs-frontend-ci` |
| Security Scans | `push:main` und manuell |
| E2E-Smokes | `push:main`, manuell und geplant |

## Lokale Prüfung

```bash
# vollständiges Gate
bash scripts/pre-push-gate.sh

# gezielte Gates
bash scripts/pre-push-gate.sh backend
bash scripts/pre-push-gate.sh frontend
bash scripts/pre-push-gate.sh schemas
```

Direkte Einzelbefehle:

```bash
# Backend
(cd backend && uv sync --group dev)
(cd backend && uv run ruff check app/)
(cd backend && uv run mypy app)
(cd backend && uv run pytest tests/contracts/ -q)
(cd backend && uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=60)

# Frontend
(cd frontend && bun install --frozen-lockfile)
(cd frontend && bun run lint)
(cd frontend && bun run typecheck)
(cd frontend && bun run test)
(cd frontend && bun run build)

# Verträge und Status
(cd backend && uv run python -m app.contracts.dump_schemas)
bash scripts/sync-status.sh
bash scripts/sync-status.sh --check
```

## Entwicklungsreihenfolge

Architekturänderungen erfolgen layer-aufwärts:

```text
Pydantic-Verträge
  ↓
JSON-Schemas und Zod-Spiegel
  ↓
Backend-Services und Persistenz
  ↓
API-Grenzen
  ↓
Frontend-Stores und Komponenten
  ↓
E2E- und Betriebsnachweis
```

Verträge und persistierte Daten dürfen nicht still verändert werden. Erforderlich sind Tests, Migration, Rollback und Dokumentation.

## Dokumentation im selben PR

Eine Änderung aktualisiert nur die passende Quelle:

- tatsächlicher Istzustand → `docs/STATUS.md`
- strategische Release-Auswirkung → `ROADMAP.md`
- konkrete Folgearbeit → GitHub Issue
- ausgeliefertes Verhalten → `CHANGELOG.md`
- Architekturentscheidung → ADR
- operativer Ablauf → Runbook

Historische Implementierungsprotokolle gehören nicht in README, STATUS oder ROADMAP.

## Sprache und Produktgrenzen

Agora-Dokumentation bleibt sachlich und kennzeichnet Simulationen klar als Simulationen. Vermeiden:

- Vorhersage- oder Zukunftssicherheitsversprechen
- „high-fidelity digital world“ oder ähnliche unbelegte Marketingaussagen
- Gleichsetzung simulierter Personas mit echten Zielgruppen
- Confidence als objektive Wahrheit

Verbindliches Vokabular: [`docs/glossary.md`](docs/glossary.md)

## Agenten

- Allgemeine Regeln: [`AGENTS.md`](AGENTS.md)
- Claude-spezifische Regeln: [`CLAUDE.md`](CLAUDE.md)
- Runbooks: [`docs/runbooks/`](docs/runbooks/)

Bei Unklarheit zuerst `docs/STATUS.md` und das zugehörige GitHub Issue prüfen. Wenn beides widersprüchlich ist, nicht raten: Drift als eigenes Issue dokumentieren.
