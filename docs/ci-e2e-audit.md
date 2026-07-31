# CI- und E2E-Audit

Datei: `docs/ci-e2e-audit.md` · Stand: 2026-07-31 · Grundlage: Repository-Stand `7deee285` auf `fix/pr975-coderabbit-findings`

Dieses Dokument hält den geprüften Istzustand der GitHub-Actions-CI und der Playwright-E2E-Suite fest, die daraus abgeleiteten Änderungen und die verbleibenden Empfehlungen. Alle Aussagen sind durch lokal ausgeführte Befehle belegt; nicht verifizierte Punkte sind ausdrücklich als solche markiert.

---

## 1. Zusammenfassung des bisherigen Zustands

Die CI war deutlich besser als der Ausgangsverdacht. Elf Workflows, durchgängig `permissions: contents: read` auf Top-Level, `step-security/harden-runner` mit `egress-policy: block` in jedem Job, Actions fast vollständig auf Commit-SHAs gepinnt, eine dokumentierte Egress-Allowlist (`docs/ci-egress-allowlist.md`) und eine bewusste Trennung zwischen schnellen PR-Gates und schweren `push:main`-Jobs.

Auch die E2E-Suite ist überdurchschnittlich: kein einziges `waitForTimeout`, durchgängig `expect.poll` statt fester Wartezeiten, keine `test.skip`/`test.fixme`-Leichen, und Kommentare, die echte Root-Cause-Analysen dokumentieren statt Vermutungen. Mehrere Helper enthalten ausformulierte Begründungen, warum eine frühere, strengere Fassung falsch-negativ war.

Die Probleme lagen nicht in der Testqualität, sondern in der **Verdrahtung**: Tests, die nirgends laufen; fehlende Abbruchsteuerung; fehlende Zeitgrenzen.

---

## 2. Erkannte Probleme

| # | Befund | Schwere | Beleg |
|---|--------|---------|-------|
| P1 | **Kein einziger** der 11 Workflows hatte einen `concurrency`-Block. Bei schneller Push-Folge liefen mehrere komplette Generationen weiter — beim E2E-Workflow sind das je 6 parallele Docker-Stack-Jobs (gemessen ~3,2–3,8 min pro Job, also ≈ 21 Runner-Minuten pro überflüssiger Generation). | hoch | Skriptanalyse aller `.github/workflows/*.yml`; Laufzeiten aus `gh run view 30599684435` |
| P2 | **Zwei Spec-Dateien liefen in keinem Workflow**: `run-budget.spec.ts` (3 Tests, eingeführt mit PR #975) und `drawer-focus-trap.spec.ts` (7 Test-Definitionen, eingeführt mit PR #723). Zusammen toter Testcode. | hoch | Abgleich aller `playwright test`-Aufrufe gegen `frontend/tests/e2e/*.spec.ts` |
| P3 | **20 von 27 Jobs ohne `timeout-minutes`.** Ein hängender Job lief bis zum GitHub-Default von 360 min. Betroffen waren u. a. alle 5 Jobs in `ci.yml` und alle 3 in `docker-image.yml` (inkl. des self-hosted arm64-Runners). | mittel | YAML-Parse aller Jobs |
| P4 | **26 von 27 `actions/checkout`-Schritten ohne `persist-credentials: false`** — der GitHub-Token blieb im Git-Credential-Helper des Runners liegen. Entspricht dem offenen Issue #805. | mittel | `grep` über alle Workflows |
| P5 | **4 Actions nicht SHA-gepinnt** (`oven-sh/setup-bun@v2` ×2, `actions/upload-artifact@v7` ×2) — ausschließlich in `e2e-smokes.yml`, inkonsistent zur Repo-Policy aus PR #719. | mittel | `grep -v '@[0-9a-f]{40}'` |
| P6 | `forbidOnly` fehlte in `playwright.config.ts`. Ein versehentlich committetes `test.only` hätte in CI still den Rest der Datei übersprungen und trotzdem grün gemeldet. | mittel | `frontend/playwright.config.ts` |
| P7 | `retries: 0` in CI. Alle sechs Smokes sind Required Checks; ein einzelner Infrastruktur-Hickser blockierte den PR und kostete einen vollständigen 25-min-Rerun — ohne jede Spur im Report. | niedrig | Branch-Protection-Abfrage + Config |
| P8 | **`assertStubModeActive()` assertet nie.** Der Helper loggt nur und fängt jeden Fehler mit `try/catch` ab. Der Name verspricht eine Garantie, die die Funktion nicht gibt. Im Baseline-Lauf hat er einen HTTP 401 verschluckt, ohne dass ein Test rot wurde. | mittel | `frontend/tests/e2e/helpers/diagnostics.ts` + Baseline-Log |
| P9 | An zwei von fünf Aufrufstellen (`golden-gate-accessibility.spec.ts:180`, `report-modes.spec.ts:148`) wird der `APIRequestContext` **ohne** `extraHTTPHeaders` erzeugt. Die Stub-Diagnose läuft dort systematisch in einen 401 und ist wirkungslos. | niedrig | Baseline-Log + Quellenabgleich |
| P10 | Kein Dependency-Caching für `uv` oder `bun`. Jeder Job installiert von Grund auf neu. | niedrig | `grep 'cache'` — nur Docker-Layer-Cache in `docker-image.yml` |
| P11 | `docs/runbooks/e2e-required-check.md` behauptet „Required-Erzwingung noch nicht freigegeben". Die Branch-Protection auf `main` erzwingt die sechs Smokes tatsächlich bereits. Dokumentations-Drift. | niedrig | `gh api repos/arn0ld87/agora/branches/main/protection` |
| P12 | `scripts/e2e-up.sh` **hängt** Credentials an `.env` an (`>>`). Bei wiederholten lokalen Läufen wächst die Datei mit Duplikaten. Funktional unkritisch (Compose: letzte Definition gewinnt), aber unsauber. | niedrig | `scripts/e2e-up.sh:56-71` |

### Nicht als Problem gewertet

- Die Aufteilung `backend` / `backend-pr-gate` (bzw. `frontend` / `frontend-pr-gate`) sieht nach Duplizierung aus, ist aber die bewusste und sinnvolle Trennung „schnelles Pflicht-Gate auf PR" vs. „volle Suite mit Coverage auf `main`". Beibehalten.
- Die Label-Steuerung (`needs-backend-ci`, `needs-frontend-ci`) über `pull_request: types: [..., labeled, unlabeled]` ist erklärungsbedürftig, aber funktional korrekt und dokumentiert. Beibehalten.
- Die drei `continue-on-error: true` in `docker-image.yml` betreffen optionale Docker-Hub-Mirror-Schritte, nicht die Sicherheitsprüfungen. Beibehalten.

---

## 3. Baseline-Ergebnisse

Alle Läufe am 2026-07-31 auf macOS (darwin 27.0.0, arm64), Python 3.14.6, bun 1.3.14, uv 0.11.17, Docker 29.6.2.

| Befehl | Ergebnis | Laufzeit |
|--------|----------|----------|
| `bun run lint` (frontend) | grün | 2,0 s |
| `bun run typecheck` (frontend) | grün | 5,0 s |
| `bun run test` (frontend) | grün — 176 Dateien, **1644 Tests** | 23,2 s |
| `uv run pytest tests/contracts/ -q` | grün — **464 Tests** | 5,5 s |
| `uv run ruff check app/ tests/` | grün | 0,1 s |
| `uv run mypy app` | grün — 246 Dateien | 1,1 s |
| `uv run python -m app.contracts.dump_schemas --check` | grün — 51 Schemas | 1,4 s |
| `actionlint` (via `rhysd/actionlint`-Image) | **0 Findings**, Exit 0 | < 5 s |

Das schnelle PR-Gate ist damit lokal in unter 40 Sekunden vollständig reproduzierbar. Das ist ein sehr guter Wert und erklärt, warum die PR-Gates in CI nicht als Bremse auffallen.

### Beobachtete Warnungen

`pytest` erzeugt **24 980 Warnungen** in den Contract-Tests, ganz überwiegend `DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated` aus `pytest_asyncio` und `neo4j._meta`. Das ist Upstream-Rauschen ohne Aussagewert, verdeckt aber echte Warnungen. Empfehlung siehe §9.

### E2E-Baseline

Der lokale E2E-Lauf erforderte, den laufenden Dev-Stack abzuräumen, weil die Compose-Dateien feste `container_name` setzen (`agora`, `agora-neo4j`, `agora-redis`, `agora-nginx`). `COMPOSE_PROJECT_NAME` isoliert dadurch **nicht**, und `scripts/e2e-down.sh` löscht mit `down -v` die Volumes. Das wurde vor der Ausführung ausdrücklich freigegeben.

> **Nachtrag (Issue #989, 2026-07-31):** dieser Befund ist behoben. Das E2E-Override vergibt eigene `container_name`-Werte (`agora-e2e*`), der Stack läuft unter dem festen Projektnamen `agora-e2e` und `scripts/e2e-compose.sh` hält die Compose-Invocation für Up, Down und Log-Dump an einer Stelle. Ein lokaler E2E-Lauf neben dem laufenden Dev-Stack ist damit möglich; `down -v` trifft ausschließlich die Volumes des E2E-Projekts. Anleitung: [`docs/runbooks/e2e-local.md`](runbooks/e2e-local.md).

Ein erster Lauf schlug vollständig fehl, weil der Playwright-Chromium-Build lokal nicht installiert war (`browserType.launch: Executable doesn't exist`). Die reinen API-Tests (health 1/2/4, report-modes 4/4) liefen dabei bereits grün durch — der Stack selbst war also gesund. Nach `npx playwright install chromium` wurde der Lauf wiederholt.

**Ergebnis des vollständigen Laufs: siehe §5.**

---

## 4. Bewertung der bestehenden E2E-Tests

Bewertet wurde jede Spec-Datei und jede Test-Case-Definition gegen das tatsächlich implementierte Verhalten, nicht gegen Testnamen.

| Datei | Tests | Entscheidung | Begründung |
|-------|-------|--------------|------------|
| `health.spec.ts` | 4 | **beibehalten** | Deckt Reverse-Proxy-Health, App-Health, SPA-Mount und `/api/status` mit `auth_mode`-Assertion ab. Test 3 ist bewusst auf Smoke-Niveau begrenzt und dokumentiert das; Test 4 prüft einen echten Vertragswert statt nur HTTP 200. Kein reiner „Seite lädt"-Test. |
| `upload-graph.spec.ts` | 1 (7 Schritte) | **beibehalten** | Vollständiger Ablauf Upload → Ontologie → Graph-Build → Polling → API-Assertion → UI. Nutzt `expect.poll`, keine festen Wartezeiten. Dokumentiert ausdrücklich, dass `node_count=0` im Stub-Modus valide ist — die UI-Assertion prüft den Completed-Zustand, nicht bloß Existenz. |
| `minimal-report.spec.ts` | 1 (mehrstufig) | **beibehalten** | Der teuerste, aber auch aussagekräftigste Test: Graph + 50 Personas + Report-Generierung + 11 Sections + Persona-Tabelle. Assertions sind inhaltlich (`toBeGreaterThanOrEqual(MIN_PERSONA_TABLE_ROWS)`), nicht bloß Sichtbarkeit. |
| `report-modes.spec.ts` | 4 | **beibehalten** | Prüft `strict`/`balanced`/`explorative` plus Default-Drift als eigenständigen Test. Der Kommentar begründet nachvollziehbar, warum der Markdown-Banner der korrekte Anker ist und ein JSON-Assert nicht funktioniert (v2-Envelope kennt `report_mode` nicht). Vorbildliche Vertragsverankerung. |
| `golden-gate-accessibility.spec.ts` | 28 | **beibehalten** | Fünf echte Gates pro Route (axe-core, 320 px, Tastatur, Focus-visible, Reduced-Motion) über 28 Routen. Enthält eine ausdrücklich **dokumentierte** Ausnahme für `/v4/report` und `/v4/interaction` statt eines stillen Weglassens — genau die Transparenz, die man sehen will. |
| `ai-model-picker.spec.ts` | 7 | **beibehalten** | Selektoren ausschließlich über `data-testid`. Prüft Tastaturnavigation, Suchfilter, Offline-Connection (Negativfall) und dass der Stage-Override tatsächlich als `source=stage_override` im `ai_route` landet — eine API-Wirkungs-Assertion, nicht nur UI-Zustand. |
| `drawer-focus-trap.spec.ts` | 7 | **beibehalten + in CI verdrahten** | Inhaltlich gut (Focus-Trap zyklisch vorwärts/rückwärts, `inert`, Escape-Rückfokus). Lief seit PR #723 in **keinem** Workflow. Lokal verifiziert: 5/5 grün in 11 s. |
| `run-budget.spec.ts` | 3 | **überarbeiten — noch nicht in CI** | Zielt auf einen Kostenkontroll-Pfad, dessen Regression echtes Geld kostet — inhaltlich wertvoll und deshalb ausdrücklich **nicht** gelöscht. Lief seit PR #975 in **keinem** Workflow und ist derzeit defekt (§5). Ein Defekt behoben, der zweite offen und tracking-bedürftig. |

**Kein Test wurde entfernt.** Kein Test erwies sich als reiner „Seite lädt"-Test, keiner als reine Implementierungsdetail-Prüfung, keiner als reihenfolgeabhängig im schädlichen Sinne (die `beforeAll`-Fixtures in `report-modes` und `golden-gate` sind dateiintern und dokumentiert).

### Schwächste Stelle

`checkKeyboardNavigation()` in `helpers/accessibility.ts` endet auf `expect(focusStepCount > 0).toBe(true)` — es genügt, dass **irgendeiner** von bis zu zehn Tab-Anschlägen den Fokus irgendwo in die Seite legt. Das ist eine schwache Assertion, die grün bleiben kann, während die Tab-Reihenfolge für Nutzer unbrauchbar ist.

Sie wurde jedoch **absichtlich** so abgeschwächt: der Kommentar dokumentiert, dass die frühere, strengere Fassung auf Seiten mit wenigen Tab-Stops systematisch falsch-negativ war (Issues #838, #921). Eine Verschärfung ohne neues Konzept würde die damals behobene Flakiness zurückholen. **Nicht geändert**, als Empfehlung in §9 aufgenommen.

---

## 5. Ergebnis des vollständigen E2E-Laufs

Vollständiger Lauf über alle 8 Spec-Dateien (39 Tests) gegen den Compose-Stack auf Port 8080, `AGORA_E2E_LLM_MODE=stub`:

**36 passed, 3 failed, 3,5 min Gesamtlaufzeit.**

| Spec | Ergebnis | Zeit |
|------|----------|------|
| `health.spec.ts` | 4/4 grün | 1,4 s |
| `upload-graph.spec.ts` | 1/1 grün | 2,2 s |
| `minimal-report.spec.ts` | 1/1 grün | 7,5 s |
| `report-modes.spec.ts` | 4/4 grün | 8,5 s |
| `drawer-focus-trap.spec.ts` | **5/5 grün** | 10,7 s |
| `golden-gate-accessibility.spec.ts` | 17/18 | 37,5 s |
| `ai-model-picker.spec.ts` | 4/5 | 22,2 s |
| `run-budget.spec.ts` | **0/1** | 1,5 s |

### Abgleich mit GitHub Actions

Zur Einordnung der drei Fehlschläge wurden die letzten CI-Läufe geprüft (`gh run list --workflow=e2e-smokes.yml`). Auf **genau diesem Branch** (Run `30599486935`) und auf `main` (Run `30599684435`) sind **alle sechs Jobs grün**. Gemessene Job-Laufzeiten dort: **3,2–3,8 min** inklusive Stack-Boot.

Damit lassen sich die Fehlschläge sauber zuordnen:

| Fehlschlag | Bewertung | Begründung |
|------------|-----------|------------|
| `golden-gate` → „Settings LLM Providers" · `[serious] color-contrast` auf 3 `div[data-provider-id=…]`-Knoten | **lokales, nicht-deterministisches Umgebungsartefakt** | In CI grün. Entscheidender Beleg: in einem zweiten lokalen Lauf derselben Datei fiel **zusätzlich** „Runs" durch, das im ersten Lauf grün war — die Menge der Fehlschläge variiert also zwischen lokalen Läufen. axe-core-Kontrastmessung hängt von Schriftrasterung, Farbprofil und Paint-Timing ab; macOS verhält sich hier anders als der Ubuntu-Runner. **Kein belegter Produktdefekt** — für diese Behauptung fehlt jeder CI-Beleg. |
| `ai-model-picker` → Test 1 (`↓↓↑Enter`), Abbruch im `beforeEach` an `getStagePicker(...).toBeVisible()` | **lokales Reihenfolge-/Warmlauf-Artefakt** | Die übrigen 4 Tests derselben Datei mit identischem `beforeEach` sind grün. In CI läuft die Datei allein nach vollständigem Stack-Health-Wait; lokal lief sie als erste Spec einer Gesamtsuite. Genau der Fall, für den `retries: 1` einen Trace beider Versuche und den „flaky"-Ausweis liefert. Der Lauf bleibt dank `failOnFlakyTests` trotzdem rot — der Retry verbessert die Diagnose, er senkt die Messlatte nicht. |
| `run-budget` → Abbruch nach 1,5 s | **echter Defekt in der Spec — zwei Stück** | Siehe unten. |

### `run-budget.spec.ts` — zwei Defekte, seit PR #975 unentdeckt

Die Datei lief seit ihrer Einführung in **keinem** Workflow. Der erste lokale Lauf überhaupt legt zwei Fehler frei:

**Defekt 1 — falscher Request an `preflight-estimate` (behoben).**
Die Spec schickte nur `{ simulation_id }`. Der Endpunkt leitet `num_agents`/`max_rounds` aus dem Artefakt `simulation_config` ab; das entsteht aber erst bei der Simulations-**Vorbereitung**, nicht durch `POST /api/simulation/create` + Profil-Seeding. Ergebnis: deterministisch HTTP 400 (`backend/app/api/simulation_budget.py:140-148`).

Korrigiert, indem `num_agents` und `max_rounds` — vom Endpunkt ausdrücklich unterstützt — mitgegeben werden. `simulation_id` bleibt im Body, damit der Config-Lookup-Zweig weiterhin durchlaufen wird, statt still einen anderen Codepfad zu testen.

**Defekt 2 — Budget greift nicht (offen, NICHT behoben).**
Nach der Korrektur läuft die Spec weiter und scheitert an der eigentlichen Kernaussage:

```
Error: Budgetabbruch muss status=stopped liefern, nicht failed. message=Task completed
Expected: "stopped"
Received: "completed"
```

Der Report läuft trotz `budget: { max_llm_calls: 2, enforcement: "hard" }` vollständig durch. Der Budgetabbruch tritt nicht ein.

Befundlage, so weit im Rahmen dieses Audits belegbar:

- `POST /api/report/generate` nimmt `budget` entgegen und reicht es weiter (`backend/app/api/report.py:159-183`).
- Der Stub-Pfad in `LLMClient.chat` ruft `_budget_check()` und `_budget_record()` auf (`backend/app/llm/client.py:597-609`) — die Verdrahtung ist also grundsätzlich vorhanden.
- `_budget_check()` ist jedoch ein **No-op, wenn `self._budget_enforcer()` `None` liefert** (`client.py:414-416`), und `self.run_id = run_id or os.environ.get("AGORA_RUN_ID")` (`client.py:132`). `AGORA_RUN_ID` wird nur im OASIS-Subprozess gesetzt (`llm_routing_seed.py:474`), nicht im In-Process-Report-Pfad.

Die naheliegende Hypothese ist damit, dass der Report-Pfad den `LLMClient` ohne Run-Bindung erzeugt und das harte Limit deshalb nie ausgewertet wird. **Das ist eine Hypothese, keine verifizierte Ursache** — sie abschließend zu klären erfordert eine Untersuchung im Produktivcode, die über einen CI-/Test-Audit hinausgeht.

**Bewusst nicht getan:** die Assertion abgeschwächt oder der Test „grün gemacht". Wäre die Kernaussage entfernt worden, hätte der Test genau das nicht mehr geprüft, wofür er existiert — Kostenkontrolle. Ebenso wenig wurde Produktivcode geändert, um den Test passieren zu lassen.

**Konsequenz:** `run-budget.spec.ts` wird in dieser Änderung **nicht** in CI verdrahtet. Ein Job, der garantiert rot ist, hilft niemandem. Empfohlenes Vorgehen in §9 (E9).

### Verifikation der tatsächlich ausgelieferten Änderung

Der geänderte Golden-Gate-Aufruf wurde in exakt der Form ausgeführt, in der er künftig in CI steht:

```
npx playwright test golden-gate-accessibility.spec.ts drawer-focus-trap.spec.ts
```

Ergebnis: **21 passed, 2 failed, 1,3 min** — `drawer-focus-trap` darin **5/5 grün**. Die beiden Fehlschläge sind die oben eingeordneten, lokal nicht-deterministischen a11y-Kontrastprüfungen. Der kombinierte Aufruf greift beide Dateien korrekt und kostet nur ~11 s Zusatzlaufzeit gegenüber dem bisherigen Job.

---

## 6. Neue Teststrategie

Die Ebenen sind bereits sinnvoll besetzt; die Strategie schreibt den Istzustand fest, statt ihn umzubauen.

| Ebene | Umfang | Trigger | Bewertung |
|-------|--------|---------|-----------|
| **Unit / Komponente** | 1644 Frontend-Tests (Vitest), 324 Backend-Testdateien | jeder PR | Trägt die Hauptlast. Richtig so. |
| **Contract** | 464 Pydantic-Contract-Tests + Schema-Drift + Zod-Spiegel | jeder PR | Der eigentliche Sicherheitsgurt des Projekts. Läuft in 5,5 s. |
| **Integrationsnah (Backend)** | `tests/api/`, `tests/services/`, `tests/regression/`, `tests/eval/` | `push:main` | Deckt Neo4j-, LLM- und Persistenz-Adapter günstiger ab als Browser-E2E. Richtige Ebene. |
| **PR-Smoke (E2E)** | die sechs Playwright-Jobs, alle Required Checks | jeder PR | Bleibt unverändert. Siehe unten. |
| **Produktionsnah** | `docker-image.yml::prod-proxy-smoke` | nur Release-Pfade + `workflow_dispatch` | Korrekt eingegrenzt — teuer, aber nur dort, wo er zusätzliche Aussage bringt. |

### Warum die E2E-Ebene *nicht* umgeschichtet wurde

Naheliegend wäre gewesen, die vier teuren Smokes von `pull_request` auf `push:main` zu verschieben und nur `health` + `upload-graph` als PR-Gate zu behalten. Das wurde geprüft und **verworfen**:

Die Branch-Protection auf `main` führt alle sechs Playwright-Jobs als Required Checks — referenziert über ihren exakten `name:`-String:

```
Playwright Health-Smoke
Playwright Upload+Graph-Smoke
Playwright Minimalreport-Smoke
Playwright Report-Modes-Smoke (P4.4)
Playwright Golden-Gate-Accessibility-Smoke (Slice 7.3.1)
Playwright AiModelPicker-Smoke (Slice 5.6 / 7.3.1)
```

Ein als required konfigurierter Check, der auf einem PR **gar nicht startet**, bleibt dauerhaft auf „Expected — Waiting for status to be reported" stehen und blockiert den PR unbefristet. Genau diese Falle ist im Repo bereits dokumentiert (Kommentar in `docker-image.yml`, CHANGELOG-Eintrag 2026-07-28). Deshalb gilt:

> **Die `name:`-Strings dieser sechs Jobs und ihr `pull_request`-Trigger sind eingefroren.** Änderungen daran erfordern eine gleichzeitige Anpassung der Branch-Protection und gehören nicht in ein Test-Refactoring.

Die Laufzeit wurde stattdessen über `concurrency` gesenkt (§7) — das spart bei aktiver Entwicklung mehr als eine Umschichtung, ohne Schutz aufzugeben.

### Wo der Zusatzbedarf hinging

- `drawer-focus-trap.spec.ts` → **in den bestehenden** Golden-Gate-Job aufgenommen, nicht in einen eigenen. Es ist inhaltlich ein Accessibility-Gate und braucht denselben Stack. Kosten: ~11 s statt eines kompletten Stack-Boots.
- `run-budget.spec.ts` → **bleibt vorerst unverdrahtet.** Der erste Lauf überhaupt legte offen, dass die Spec defekt ist (§5). Sie in CI aufzunehmen hätte einen dauerhaft roten Job erzeugt. Sobald Defekt 2 geklärt ist, gehört sie in einen eigenen Job (sie braucht `AGORA_E2E_LLM_MODE=stub` und ein eigenes Zeitbudget) — mit einem Job-`name:`, der bewusst **kein** Required Check wird, bis er sich als stabil erwiesen hat.

### Was bewusst *nicht* neu gebaut wurde

Für Neo4j-Ausfall, LLM-/Embedding-Dienstfehler, ungültige Zugangsdaten, beschädigte Uploads und Dateiformat-Grenzen existieren bereits Backend-Tests (`test_neo4j_resilience.py`, `test_auth.py`, `test_upload_limits.py`, `test_ssrf_blocker.py`, `test_llm_client.py` u. a.). Dieselbe Logik zusätzlich als Browser-E2E zu prüfen, hätte Laufzeit gekostet ohne neue Aussage. Der Auftrag verlangt ausdrücklich, solche Mehrfachprüfung zu vermeiden.

---

## 7. Änderungen an GitHub Actions

### `concurrency` in allen 11 Workflows — der größte Hebel

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

Nur PR-Läufe werden abgebrochen. `push:main`, `schedule` und `workflow_dispatch` laufen zu Ende — dort ist jeder Lauf ein eigenständiger Nachweis für genau einen Stand.

Zwei bewusste Abweichungen:

- `cve-monitor.yml` und `scorecard.yml` haben keinen PR-Trigger und verwenden `cancel-in-progress: false`. Sie sollen sich nur nicht selbst überlappen; ein abgebrochener Audit- oder SARIF-Lauf wäre kein verwertbares Ergebnis.
- `dependency-review.yml` läuft ausschließlich auf PRs und verwendet daher unbedingt `cancel-in-progress: true`.
- `docker-image.yml` bricht ausdrücklich **keine** push/tag-Läufe ab: der `publish`-Job schiebt nach GHCR, ein Abbruch mitten im Push hinterließe eine halb hochgeladene Tag-Referenz.

### `timeout-minutes` auf allen 27 Jobs

Vorher hatten 7 Jobs eine Zeitgrenze, jetzt alle 27. Werte an den gemessenen Laufzeiten orientiert, mit Reserve: 10 min für Lint-/Drift-Gates, 15–20 min für Test-Gates, 30 min für CodeQL und den Proxy-Smoke, 45 min für `publish`, 60 min für `build-only` (läuft teilweise auf dem langsameren self-hosted arm64-Runner).

### Sicherheit

- **`persist-credentials: false`** auf allen 27 `actions/checkout`-Schritten (vorher 1). Vorab geprüft: kein Workflow führt `git push`, `git commit`, `git tag` aus oder nutzt eine PR-erstellende Action — die Option ist überall unkritisch. Beim Gitleaks-Checkout mit `fetch-depth: 0` ist im Kommentar festgehalten, dass sich die Action über `GITHUB_TOKEN` im `env` authentifiziert, nicht über den Credential-Helper. **Schließt Issue #805.**
- **4 fehlende SHA-Pins ergänzt** — `oven-sh/setup-bun` und `actions/upload-artifact` in `e2e-smokes.yml` auf dieselben SHAs wie im übrigen Repo.

### Was ausdrücklich *nicht* geändert wurde

- **Kein Job umbenannt** (Required-Check-Bindung, siehe §6).
- **Keine Sicherheitsprüfung entfernt oder abgeschwächt.** Gitleaks, CodeQL, Dependency Review, Scorecard, pip-audit, `bun audit` und die Trivy-Scans bleiben unverändert.
- **Kein Dependency-Caching eingeführt.** Begründung in §9.
- **Keine Egress-Allowlist verändert.** Jede Änderung dort ist lokal nicht testbar; ein falscher Eintrag bricht Jobs im `block`-Modus.

---

## 8. Vorher / Nachher

| Bereich | Vorher | Nachher | Begründung |
|---------|--------|---------|------------|
| `concurrency` | 0 von 11 Workflows | 11 von 11 | Veraltete PR-Läufe wurden nie abgebrochen; bei 6 Docker-Stack-Jobs pro Lauf der mit Abstand größte Kostenposten. |
| `timeout-minutes` | 7 von 27 Jobs | 27 von 27 | Ein hängender Job lief bis zum GitHub-Default von 360 min. |
| `persist-credentials: false` | 1 von 27 Checkouts | 27 von 27 | Token blieb im Credential-Helper des Runners. Schließt Issue #805. |
| SHA-Pinning | 4 Actions ungepinnt | 0 ungepinnt | Konsistenz zur Repo-Policy aus PR #719; Schutz gegen Tag-Verschiebung. |
| E2E-Specs in CI | 6 von 8 Dateien | 7 von 8 | `drawer-focus-trap` (5 Tests, lokal grün) verdrahtet. `run-budget` bleibt draußen, weil der erste Lauf überhaupt einen echten Defekt offenlegte (§5) — ein garantiert roter Job hilft niemandem. |
| `forbidOnly` | nicht gesetzt | in CI aktiv | Ein committetes `test.only` hätte den Rest der Datei still übersprungen. |
| Playwright-`retries` | 0 (auch in CI) | 1 in CI + `failOnFlakyTests` in CI, lokal 0 | Der Retry liefert Trace und „flaky"-Ausweis; `failOnFlakyTests` hält den Lauf trotzdem rot. **Beides gehört zwingend zusammen** — ohne die zweite Zeile beendet Playwright einen Lauf mit flaky-Tests mit Exit-Code 0, und das Required-Check-Gate wäre schwächer als vorher (Codex-Finding P1 zu PR #977, nachgezogen). |
| Required-Check-Namen | 6 E2E-Jobs gebunden | unverändert | Umbenennen hätte PRs dauerhaft blockiert. |
| actionlint | 0 Findings | 0 Findings | Regressionsfrei. |

---

## 9. Bekannte Einschränkungen und offene Empfehlungen

### Nicht verifizierbar in dieser Sitzung

1. **Das Verhalten der Änderungen auf GitHub-Runnern.** `concurrency`, `timeout-minutes` und `persist-credentials` sind lokal nur statisch prüfbar (actionlint + YAML-Parse, beide grün). Der erste CI-Lauf ist der eigentliche Nachweis. Besonderes Augenmerk: dass `persist-credentials: false` keinen der Checkout-Schritte bricht — vorab geprüft, aber nicht ausgeführt.
2. **Der Budgetabbruch aus `run-budget.spec.ts`.** Die Spec ist **nicht** in CI verdrahtet und es gibt keinen `run-budget`-Job — der Pfad hat damit **keinerlei CI-Abdeckung**. Lokal ist sie nicht grün, sondern deckt einen offenen Defekt auf (§5, Issue #978).

### Empfehlungen (bewusst nicht umgesetzt)

> **Nachgetragen 2026-07-31 (Codex-Finding P1 zu PR #977):** Dieses Dokument ist ein Auditbefund, **keine Planungsquelle** — AGENTS.md verbietet neue Planungsdateien neben README, STATUS, ROADMAP und Issues. Die Nachverfolgung läuft daher über GitHub Issues; die Tabelle bleibt nur als Begründungs- und Belegkontext stehen:
>
> - **[#978](https://github.com/arn0ld87/agora/issues/978)** — Budget-Defekt (ehem. E9), höchste Priorität
> - **[#979](https://github.com/arn0ld87/agora/issues/979)** — Sammel-Issue E1–E8
>
> Bei Abweichungen gilt der Issue-Stand, nicht diese Tabelle.

| # | Empfehlung | Warum nicht jetzt |
|---|-----------|-------------------|
| E1 | **Dependency-Caching** für `uv` (via `astral-sh/setup-uv` mit `enable-cache: true`, im Repo bereits in `cve-monitor.yml` gepinnt vorhanden) und `bun`. | Der GitHub-Cache-Dienst braucht `results-receiver.actions.githubusercontent.com:443` und `*.blob.core.windows.net:443` in der Egress-Allowlist. Diese Endpunkte fehlen in den `ci.yml`-Jobs. Ob `harden-runner` sie im `block`-Modus implizit durchlässt, ist lokal nicht feststellbar — ein Fehlgriff bricht die CI. Gehört in einen eigenen Slice mit einem CI-Lauf als Nachweis. |
| E2 | **`assertStubModeActive` umbenennen** zu `logStubModeDiagnostics` und die Stub-Aktivierung über ein Feld in `/api/status` **wirklich** assertierbar machen. | Die Umbenennung allein ist kosmetisch; der Nutzen entsteht erst mit dem Backend-Feld. Das ist eine Produktivcode-Änderung und lag außerhalb des CI-/Test-Auftrags. Bis dahin bleibt P8 als dokumentierte Schwäche bestehen. |
| E3 | **Fehlende Auth-Header** an den zwei Aufrufstellen aus P9 ergänzen. | Hängt an E2 — solange der Helper ohnehin nichts assertet, ändert der Header nur die Log-Zeile. Gemeinsam erledigen. |
| E4 | **`checkKeyboardNavigation` verschärfen**: statt „irgendein Tab setzt Fokus" die tatsächliche Tab-Reihenfolge gegen die DOM-Reihenfolge prüfen. | Die aktuelle Abschwächung war die dokumentierte Lösung für falsch-negative Läufe (#838, #921). Eine Verschärfung ohne neues Konzept holt die Flakiness zurück. Braucht einen eigenen Entwurf. |
| ~~E5~~ **erledigt** | **PR-Gates als Required Checks aufnehmen.** `Backend PR smoke gate` und `Frontend PR smoke gate` liefen auf jedem PR, waren aber **nicht** required — ein PR mit rotem Lint, Typecheck oder Unit-Test war mergebar. | Am 2026-07-31 nach Freigabe umgesetzt: Branch-Protection von 15 auf 17 Required Checks erweitert, `strict: true` unverändert. Die „Check startet nie"-Falle ist ausgeschlossen — `ci.yml` hat keinen `paths`-Filter, und beide Jobs stehen auf `if: github.event_name == 'pull_request'`. |
| E6 | **`docs/runbooks/e2e-required-check.md` korrigieren** (P11) — es behauptet, die Erzwingung sei noch nicht freigegeben, obwohl sie aktiv ist. | Reine Doku-Korrektur, gehört in denselben Slice wie die Runbook-Pflege. |
| E7 | **`scripts/e2e-up.sh`**: `.env`-Anhängen idempotent machen (P12), statt bei jedem Lauf Duplikate zu erzeugen. | Betrifft das Skript, nicht die CI-Definition; ohne Funktionsfehler. |
| ~~**E9**~~ **erledigt** | ~~**Issue für `run-budget`-Defekt 2 anlegen** (§5): klären, ob das harte Budget im In-Process-Report-Pfad überhaupt ausgewertet wird, oder ob dem `LLMClient` dort die Run-Bindung fehlt. **Höchste Priorität dieser Liste** — es geht um Kostenkontrolle. Danach `run-budget.spec.ts` als eigenen Job verdrahten.~~ → Als [#978](https://github.com/arn0ld87/agora/issues/978) aufgenommen und behoben. Die hier vermutete fehlende Run-Bindung war **nicht** die Ursache — sie ist korrekt verdrahtet und der Enforcer feuert. Der `BudgetExceededError` wurde stattdessen von neun `except Exception`-Fallback-Handlern im Report-Agent-Pfad verschluckt. `run-budget.spec.ts` läuft seitdem als eigener Job `run-budget-smoke`. | Erfordert eine Untersuchung im Produktivcode und ggf. eine Produktänderung. Beides liegt außerhalb eines CI-/Test-Audits, und ein Test darf nicht dadurch grün werden, dass man Produktivcode passend macht. |
| E8 | **pytest-Warnungsrauschen eindämmen** — 24 980 `DeprecationWarning` aus `pytest_asyncio`/`neo4j` verdecken echte Warnungen. Ein gezielter `filterwarnings`-Eintrag in `pyproject.toml` für genau diese Upstream-Quellen. | Nicht Teil des CI-/E2E-Auftrags; als Beobachtung festgehalten. |

---

## 10. Siehe auch

- [`docs/runbooks/e2e-required-check.md`](runbooks/e2e-required-check.md) — Required-Check-Konfiguration (korrekturbedürftig, siehe E6)
- [`docs/ci-egress-allowlist.md`](ci-egress-allowlist.md) — Egress-Ziele je Workflow
- [`docs/runbooks/pre-push-gate.md`](runbooks/pre-push-gate.md) — lokaler CI-Spiegel
- [`docs/runbooks/pr-workflow.md`](runbooks/pr-workflow.md)
