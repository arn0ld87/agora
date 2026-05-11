# Agora — aktueller Report der offenen Stellen

**Stand:** 2026-05-07  
**Repo:** `arn0ld87/agora`  
**Basis:** GitHub-Connector-Auswertung von Issues, PRs, Workflow-Runs, `docs/status.md`, `docs/dependency-risk-register.md`, CI-Workflows, Dockerfile und Compose-Dateien.

---

## 1. Kurzfazit

Agora ist inzwischen deutlich näher an einem sauberen v1.0-Kandidaten als an einem Bastelprojekt mit hübschem README, was bei Software leider schon fast verdächtig ist.

**Aktuell offen sind nicht mehr die großen Layer-9-Basics**, sondern vor allem:

1. **Dependency-Blocker rund um `camel-oasis` / `camel-ai` / `pillow` / `unstructured` / `transformers`**
2. **ein roter Dependabot-PR für `camel-ai` (#315)**
3. **Live-Settings im Frontend statt `.env`-Edit (#212)**
4. **M11-Qualitätssicherung: Playwright-Smokes, Coverage-Anhebung, Komplexitäts-Gates**
5. **kleine Doku-/Code-Drift-Stellen rund um SSE-Retry und Settings-Layer**
6. **Python-3.14-Docker-Upgrade blockiert durch `tiktoken`/Rust/Wheel-Lag (#199)**

Die beste nächste Codex-Session ist **nicht** ein weiterer kosmetischer Refactor, sondern eine harte Triage des Dependency-Knotens. Der blockiert CVE-Abbau, Python-3.14 und Dependabot-Automation gleichzeitig. Klassisches Software-Nest aus transitive pins, weil irgendwer irgendwo ein Paket festgenagelt hat und jetzt alle im Kreis laufen.

---

## 2. Priorisierte offene Stellen

| Prio | Bereich | Offene Stelle | Warum wichtig | Empfehlung |
|---:|---|---|---|---|
| P0 | Dependencies / CI | PR #315 `camel-ai 0.2.78 → 0.2.90` ist offen, nicht mergefähig, CI rot | `camel-oasis==0.2.5` pinnt `camel-ai==0.2.78`; `uv sync` bricht ab | Nicht blind mergen. Erst Resolver-/Upstream-Strategie klären. |
| P0 | Security | 9 ignorierte Python-CVEs bis Hardstop 2026-07-30 | `pip-audit` ignoriert aktuell bewusst CVEs wegen Upstream-Pins | Eskalationspfad vorbereiten: Upstream, Soft-Fork, Replacement oder Risikoakzeptanz. |
| P1 | Feature / UX / Architektur | #212 Live-Settings statt `.env` | Viele Runtime-Parameter sind nur via Restart/Env steuerbar | Settings-Layer mit Pydantic, redacted GET, validated PUT, Event-Bus-Broadcast. |
| P1 | Release-Qualität | M11.4 Playwright-Smokes fehlen | Kein echter E2E-Test für Health/Login, Upload+Graph, Minimalreport | Playwright einführen, 3 Smoke-Flows als Release-Gate. |
| P1 | Coverage | Coverage-Schwellen niedrig, strukturelle Lücken | Backend 53%-Gate, Frontend 24%-Gate; echte Werte höher, aber noch schwach | Schrittweise Gate-Anhebung laut Roadmap, aber erst E2E ergänzen. |
| P2 | Runtime Config | `_SSE_RETRY_MS=5000` in `logs.py` und `simulation_stream.py` hartkodiert | Sollte später über Settings-Layer laufen | Mit #212 zusammenziehen, nicht separat anfassen. |
| P2 | Docker / Python | #199 Python 3.14 blockiert | `tiktoken` ohne cp314-wheel; Source-Build braucht Rust | Auf Python 3.11 bleiben, Issue offen lassen, nicht Rust ins Image kippen. |
| P2 | Dependabot Hygiene | #323 `mistune`, #326 `pygments` grün, aber offen | CI/contract-gates grün, Docker-PR-Smoke bewusst skipped | Rebase/Merge nach normaler Review möglich. |

---

## 3. P0: Dependency-Knoten `camel-oasis` / `camel-ai`

### Befund

Offener PR:

- **#315:** `camel-ai` von `0.2.78` auf `0.2.90`
- Status: **open**, **not mergeable**, **CI rot**, **contract-gates rot**
- Ursache aus CI-Log:

```text
Because camel-oasis==0.2.5 depends on camel-ai==0.2.78
and your project depends on camel-ai==0.2.90,
requirements are unsatisfiable.
```

### Bewertung

Das ist kein Testproblem, sondern ein Resolver-Problem. `uv` macht hier genau das, was es soll: es verhindert einen inkonsistenten Dependency-Graph. Nervig, aber korrekt. Softwarepakete mit harten Pins sind eben kleine Geiselnahmen mit Versionsnummer.

### Konkrete Checks lokal

```bash
cd backend

# Aktuellen Lock-Graph prüfen
uv sync --group dev

# Prüfen, ob camel-oasis inzwischen eine kompatible Version erlaubt
uv lock --dry-run \
  --upgrade-package camel-oasis \
  --upgrade-package camel-ai

# Falls das scheitert: Pin-Ursache sichtbar machen
uv tree | grep -E "camel-oasis|camel-ai|pillow|unstructured|pytest|transformers" -A3 -B2
```

### Entscheidungsmatrix

| Option | Vorteil | Nachteil | Empfehlung |
|---|---|---|---|
| PR #315 schließen | Sofort sauber, keine rote CI-Leiche | CVE-Blocker bleibt | Kurzfristig sinnvoll, wenn kein kompatibles `camel-oasis` existiert |
| `camel-oasis` mit upgraden | Sauberster Pfad | Kann API-Brüche bringen | P0 prüfen |
| `camel-oasis` soft-forken | Blocker auflösbar | Wartungsaufwand | Nur wenn Hardstop näher rückt |
| `camel-oasis` ersetzen | Langfristig sauber | Großer Umbau | ADR-Pfad, nicht Mini-Slice |
| Rust ins Dockerfile für Python 3.14 | Python 3.14-Build möglich | Image größer/langsamer, löst CVEs nicht | Nicht empfohlen |

---

## 4. P0: Security-Baseline / CVE-Hardstop

### Aktive CVE-Baseline

Hardstop laut Risk Register: **2026-07-30**

| CVE | Paket | Version | Blocker | Issue |
|---|---|---:|---|---:|
| CVE-2026-25990 | `pillow` | 10.3.0 | `camel-ai` / `camel-oasis` | #121 |
| CVE-2026-40192 | `pillow` | 10.3.0 | `camel-ai` / `camel-oasis` | #122 |
| CVE-2026-42308 | `pillow` | 10.3.0 | `camel-ai` / `camel-oasis` | #296 |
| CVE-2026-42310 | `pillow` | 10.3.0 | `camel-ai` / `camel-oasis` | #297 |
| CVE-2026-42311 | `pillow` | 10.3.0 | `camel-ai` / `camel-oasis` | #298 |
| CVE-2025-71176 | `pytest` | 8.2.0 | `camel-oasis` | #123 |
| CVE-2026-1839 | `transformers` | 4.57.6 | `sentence-transformers` | #124 |
| CVE-2024-46455 | `unstructured` | 0.13.7 | `camel-oasis` | #125 |
| CVE-2025-64712 | `unstructured` | 0.13.7 | `camel-oasis` | #126 |

### Bewertung

Der Watchlist-Prozess ist gut: Issue, Owner, Frist, Hardstop, wöchentlicher Monitor. Offen ist nicht die Dokumentation, sondern die technische Exit-Strategie.

### Nächste technische Schritte

```bash
cd backend

# Aktuelle Security-Lage ohne Ignore-Liste anzeigen
uv export \
  --frozen \
  --no-dev \
  --no-hashes \
  --no-emit-project \
  --format requirements.txt \
  --output-file /tmp/agora-backend-requirements.txt

uvx pip-audit --strict -r /tmp/agora-backend-requirements.txt
```

Danach gezielt prüfen:

```bash
# Pillow-Blocker
uv lock --dry-run --upgrade-package pillow

# unstructured-Blocker
uv lock --dry-run --upgrade-package unstructured

# pytest-Blocker
uv lock --dry-run --upgrade-package pytest

# transformers-Blocker
uv lock --dry-run --upgrade-package transformers --upgrade-package sentence-transformers
```

---

## 5. P1: Live-Settings im Frontend (#212)

### Zielbild

Aktuell sind viele Einstellungen `.env`-zentriert. Ziel ist ein Runtime-Settings-Layer:

- `GET /api/settings` liefert effektive Settings, Secrets redacted
- `PUT /api/settings` validiert über Pydantic
- Persistenz in `var/runtime-settings.json` oder Redis
- Broadcast über `event_bus`: `settings.changed`
- Services lesen über `settings_layer.get_*()` statt direkt `os.getenv`
- Frontend-Drawer mit Pinia Store, Zod Validation und i18n `de/en`

### Empfehlung

Nicht alles auf einmal umbauen. Sonst entsteht wieder ein “ein PR, fünf Layer, sieben Nebeneffekte”-Monster, und das mag nicht mal GitHub Actions.

Sinnvolle Slice-Reihenfolge:

1. **Backend Settings Contract**
   - Pydantic-Modelle
   - redacted GET
   - validated PUT
   - File-Persistenz

2. **Settings-Layer minimal nutzen**
   - zuerst harmlose Runtime-Settings: SSE retry, Polling-Intervall, Persona Detail Level
   - keine Secrets setzbar machen

3. **Frontend Drawer**
   - Pinia Store
   - Zod Mirror
   - i18n
   - Live-Test: Polling-Intervall ändern ohne Restart

### Passende lokale Checks

```bash
cd backend
uv run pytest tests/contracts/ -v
uv run pytest tests/api/ -k settings -v
uv run python -m app.contracts.dump_schemas

git diff --exit-code schemas/

cd ../frontend
npm run typecheck
npm run test:coverage
npm run build
```

---

## 6. P1: M11.4 Playwright-Smokes

### Offener Stand

`docs/status.md` nennt als nächste offene Phase:

1. v1.0-Hotspot-Refactors Phase 5
2. Contract-Generation + Status-Sync Phase 6
3. **M11.4 Playwright-Smokes Phase 7**

### Minimal sinnvolle E2E-Smokes

| Test | Zweck |
|---|---|
| Health/Login | App lädt, Token/Auth funktioniert, Backend erreichbar |
| Upload+Graph | Dokument hochladen, Graph-Build anstoßen, Ergebnis sichtbar |
| Minimalreport | Minimalen Report erzeugen, keine leere/kaputte Ausgabe |

### Empfehlung

Playwright nicht als riesige E2E-Suite starten. Drei stabile Smoke-Flows reichen als Release-Gate. Der Rest bleibt Vitest/pytest. Menschen nennen das “Testpyramide”, als hätten sie nicht einfach nur gemerkt, dass Browsertests langsam sind.

---

## 7. P2: Kleine Code-/Doku-Drift

### SSE Retry hartkodiert

In `backend/app/api/logs.py` und `backend/app/api/simulation_stream.py` steht:

```python
_SSE_RETRY_MS = 5000
# TODO: über settings_layer konfigurierbar machen sobald Sub-Slice D durch ist.
```

Bewertung: sinnvoller Follow-up zu #212, kein eigener P0-Fix.

### `simulation_stream.py` Docstring prüfen

Der Docstring spricht noch von `?token=...` als Query Override. Der aktuelle Auth-Pfad ist `@allow_ticket_auth(... ?ticket=...)`, und `?token=` ist im Non-Debug-Modus laut Status/Hardening blockiert.

Empfehlung: im Settings-/SSE-Slice nebenbei korrigieren, damit Doku und Code nicht wieder getrennte Realitäten führen, diese alte Lieblingsbeschäftigung von Repos.

---

## 8. P2: Offene grüne Dependabot-PRs

### #323 `mistune 3.1.4 → 3.2.1`

- CI: grün
- contract-gates: grün
- CodeQL: grün
- dependency-review: grün
- Docker-Image: skipped, weil normale PRs aus Laufzeitgründen keinen Prod-Smoke fahren

Empfehlung: rebase/merge nach kurzer Sichtprüfung.

### #326 `pygments 2.19.2 → 2.20.0`

- CI: grün
- contract-gates: grün
- CodeQL: grün
- dependency-review: grün
- Docker-Image: skipped

Empfehlung: rebase/merge nach kurzer Sichtprüfung.

---

## 9. Aktueller Qualitätsstand

| Bereich | Stand |
|---|---|
| Version | `0.9.1-dev` |
| Backend Tests | 1567 collected |
| Frontend Tests | 43 Spec-Files |
| Backend Coverage | 55% app gesamt, CI-Gate 53% |
| Frontend Coverage | 49.29% Statements, 38.01% Branches, CI-Gate 24% |
| Static Analysis | Backend mypy + ruff, Frontend lint + typecheck |
| Supply Chain | dependency-review, CodeQL, GHCR Attestation, SPDX SBOM |
| Prod Docker | Multi-stage, final `python:3.11-slim`, kein Node/npm/curl im Runtime-Image |
| Compose Prod | `read_only: true`, tmpfs, Loopback-Default |
| Release Gate | GHCR publish smoke-gated, DockerHub optional mirror |

---

## 10. Empfohlene nächste Codex-Session

### Ziel

**P0 Dependency-Triage und Entscheidungsgrundlage für `camel-oasis`/`camel-ai`/CVE-Abbau erstellen.**

Nicht direkt wild patchen. Erst sauber beweisen:

- Warum PR #315 scheitert
- Ob es eine kompatible `camel-oasis`-Version gibt
- Ob `pillow`, `unstructured`, `pytest`, `transformers` einzeln lösbar sind
- Ob ein Soft-Fork oder Replacement nötig wird
- Welche PRs sicher mergebar sind (#323/#326)

---

## 11. Passender Befehl für eine Codex `/goal`-Sitzung

```text
/goal Ziel: Führe eine P0-Dependency-Triage für arn0ld87/agora durch und erstelle eine konkrete, umsetzbare Entscheidungsvorlage für den blockierten Dependency-Knoten rund um camel-oasis, camel-ai, pillow, unstructured, pytest, transformers und Python 3.14.

Kontext:
- Repo: arn0ld87/agora
- Branch: neuer Arbeitsbranch von main, nicht direkt auf main arbeiten.
- Aktueller kritischer PR: #315 bump camel-ai 0.2.78 -> 0.2.90 ist offen, nicht mergefähig und CI/contract-gates rot.
- Bekannter CI-Fehler: uv sync scheitert, weil camel-oasis==0.2.5 hart camel-ai==0.2.78 pinnt, während PR #315 camel-ai==0.2.90 setzt.
- Aktive CVE-Baseline mit Hardstop 2026-07-30: #121, #122, #123, #124, #125, #126, #296, #297, #298.
- Python 3.14 ist durch #199 blockiert, weil tiktoken 0.7.0 keine cp314-Wheels liefert und Source-Build Rust braucht.

Aufgaben:
1. Lies AGENTS.md, docs/status.md, docs/dependency-risk-register.md, .github/workflows/ci.yml, backend/pyproject.toml und backend/uv.lock.
2. Reproduziere lokal den Resolver-Fehler von PR #315 mit uv, ohne produktive Dateien unnötig zu ändern.
3. Prüfe per uv dry-run, ob ein gemeinsames Upgrade von camel-oasis und camel-ai möglich ist.
4. Prüfe getrennt die Upgrade-Pfade für pillow, unstructured, pytest, transformers und sentence-transformers.
5. Bewerte, welche CVEs durch reine Dependency-Upgrades lösbar sind und welche weiterhin upstream-blockiert bleiben.
6. Prüfe die offenen Dependabot-PRs #323 mistune und #326 pygments: wenn CI grün und keine Konflikte, als separat mergebare Low-Risk-Updates dokumentieren; nicht mit dem camel-ai-Problem vermischen.
7. Erstelle oder aktualisiere eine Markdown-Datei unter docs/ mit dem Namen docs/2026-05-07-dependency-triage-camel-oasis-camel-ai.md.
8. Die Datei muss enthalten: Ausgangslage, exakte Reproduktionsbefehle, Resolver-Ergebnisse, Entscheidungsmatrix, empfohlene Option, Risiken, Follow-up-Issues/PRs, DoD.
9. Falls ein kleiner sicherer Fix möglich ist, erst Tests schreiben/aktualisieren, dann Code ändern. Falls kein sicherer Fix möglich ist, keine Scheinlösung bauen, sondern die Entscheidungsvorlage committen.
10. Keine neuen --ignore-vuln-Einträge ohne Issue, Owner, Deadline und Hardstop. Keine Secrets. Keine direkten Pushes auf main.

Pflicht-Checks vor Abschluss:
cd backend && uv sync --group dev
cd backend && uv run pytest tests/contracts/ -v
cd backend && uv run ruff check .
cd backend && uv run mypy app
cd backend && uv export --frozen --no-dev --no-hashes --no-emit-project --format requirements.txt --output-file /tmp/agora-backend-requirements.txt
uvx pip-audit --strict -r /tmp/agora-backend-requirements.txt || true

git diff --stat
git status --short

Erwartetes Ergebnis:
- Entweder ein kleiner, getesteter Dependency-Fix mit grünem uv sync,
- oder eine saubere technische Entscheidungsvorlage, warum #315 geschlossen, zurückgestellt, mit camel-oasis gemeinsam aktualisiert, per Soft-Fork gelöst oder durch Replacement eskaliert werden muss.
```

---

## 12. Empfohlene Reihenfolge nach dieser Codex-Session

1. **P0 Dependency-Triage abschließen** und Entscheidung zu #315 treffen.
2. **#323 und #326 separat mergen**, falls nach Rebase weiter grün.
3. **#212 Settings-Layer beginnen**, aber nur als schmaler Layer-0/Layer-1-Slice mit Tests.
4. **M11.4 Playwright-Smokes implementieren** als Release-Gate.
5. **Coverage-Gates schrittweise anheben**, sobald die E2E-Basis steht.

---

## 13. Klare Empfehlung

Die nächste Codex-Session sollte **P0 Dependency-Triage** sein.

Begründung:

- Sie adressiert den roten PR #315.
- Sie hängt direkt an den 9 offenen CVE-Issues.
- Sie beeinflusst Python-3.14-Fähigkeit.
- Sie verhindert, dass Dependabot weiter PRs erzeugt, die am selben Pin-Knoten zerschellen.
- Sie erzeugt eine belastbare Entscheidung: Upgrade, Close, Fork, Replacement oder Risikoakzeptanz.

Alles andere ist gerade weniger wichtig. Auch wenn ein neuer UI-Drawer mehr Dopamin liefert. Leider zahlt Dopamin keine Security-Debt ab.
