# Agora — Status

**Stand:** 14.08.2026  
**Geprüfte Main-Baseline:** `39b65297`  
**Produktversion:** `0.9.5` Stability Beta

Diese Datei beschreibt ausschließlich den verifizierten Istzustand. Strategische Release-Ziele stehen in [`ROADMAP.md`](../ROADMAP.md), konkrete Arbeitspakete in [GitHub Issues](https://github.com/arn0ld87/agora/issues), ausgelieferte Änderungen in [`CHANGELOG.md`](../CHANGELOG.md).

Historische Pläne sind keine aktiven Steuerungsquellen: [`docs/archive/planning/`](archive/planning/)

## Versionsstatus

Die Produktreife wird ab diesem Dokumentationsumbau über [`VERSION`](../VERSION) geführt.

<!-- BEGIN_AUTOGEN_VERSIONS -->
| Komponente | Pfad | Version |
|---|---|---|
| Backend | `backend/pyproject.toml` | 0.9.5 |
| Frontend | `frontend/package.json` | 0.9.5 |
| Root | `package.json` | 0.9.5 |
<!-- END_AUTOGEN_VERSIONS -->

`VERSION` ist die Produkt-SSoT. Alle Komponentenmanifeste (`backend/pyproject.toml`, `package.json`, `frontend/package.json`) und der README-Badge sind auf `VERSION=0.9.5` synchronisiert; ein Drift-Check läuft in CI (`version-drift.yml`) und lokal (`pre-push-gate.sh schemas`). Der Version-Cut-Ablauf ist in [`docs/runbooks/release-versioning.md`](runbooks/release-versioning.md) beschrieben.

## Tests

<!-- BEGIN_AUTOGEN_TESTS -->
| Kategorie | Anzahl | Methode |
|---|---|---|
| Backend Tests (collected) | 5302 | `cd backend && uv run pytest --collect-only -q` |
| Frontend Test-Files | 196 | `find frontend/src \( -name '*.spec.ts' -o -name '*.spec.js' -o -name '*.test.ts' -o -name '*.test.js' \)` |
<!-- END_AUTOGEN_TESTS -->

Hinweise:

- Zwei Redis-Integrationstests skippen ohne `TEST_REDIS_URL` kontrolliert.
- Die Backend-Zahl ist der Gesamtwert aus `pytest --collect-only`; im Messlauf vom 14.08.2026 waren davon 8 deselektiert (5294 ausgeführt).
- Die Frontend-Zahl zählt Testdateien, nicht einzelne Testfälle. Die acht Playwright-E2E-Specs unter `frontend/tests/e2e/` sind darin nicht enthalten.
- Die Zahlen stammen aus dem letzten synchronisierten Status und müssen nach größeren Merges erneut erzeugt werden.
- `scripts/sync-status.sh` legt seinen Zähler-Cache unter `backend/.cache/sync-status/` an. Gehört `backend/.cache` einem anderen Benutzer — etwa nach einem Container-Lauf als root —, bricht das Skript mit „Keine Berechtigung" ab; dann `sudo chown -R "$USER" backend/.cache` oder das Verzeichnis löschen.

## Produktreife

Agora besitzt eine vollständige fachliche Grundpipeline:

- resumierbares Onboarding und lokales Benutzerprofil
- Provider-Verbindungen, Secret Store und Modell-Discovery
- getrennte Chat- und Embedding-Konfiguration
- Dokument-/Webseitenaufnahme und Knowledge-Graph-Build
- Persona-Erzeugung, Review und Simulation
- Run-Dashboard, Status, Stop/Pause/Resume und Live-Ereignisse
- Evidence-orientierte Reports und Exporte; ein einzelner ADR-0002-Verstoß beendet den Report nicht mehr als `failed`, sondern wird lokal abgestuft und maschinenlesbar protokolliert ([#1006](https://github.com/arn0ld87/agora/issues/1006)). Der JSON-Export normalisiert Evidence über dieselbe kanonische Kette wie der Lese-Pfad und weist eine nicht auslieferbare Evidence-Map im Envelope aus, statt sie stumm zu verwerfen ([#987](https://github.com/arn0ld87/agora/issues/987)); ZIP-, CSV- und Streaming-ZIP-Export lesen dieselbe normalisierte Sicht ([#1036](https://github.com/arn0ld87/agora/issues/1036)) und **validieren sie seit [#1160](https://github.com/arn0ld87/agora/issues/1160) G auch** — vertragswidrige Evidenz verlässt das System in keinem Format mehr als scheinbar geprüfte Datei: das ZIP trägt `evidence-omitted.json` statt `evidence-map.json`/`claims.csv`, der Claims-CSV-Abruf und `GET /api/report/<id>/evidence` antworten mit 422 und demselben `reason=contract_violation` wie der JSON-Envelope. Die Evidence-Sub-Routen (Section und Claim) normalisieren seit [#967](https://github.com/arn0ld87/agora/issues/967) über dieselbe kanonische Kette; damit gibt es keinen Consumer mehr mit eigener Evidence-Sicht
- Compare-, Graph-Diff- und Observability-Grundlagen
- fortsetzbare Embedding-Migration für Entity- und Fact-Vektoren
- Kosten-, Token- und Zeitbudgets für Runs ([#764](https://github.com/arn0ld87/agora/issues/764), ADR-0012): Preflight-Schätzung mit ehrlichen Bereichen, weiche/harte Limits pro Run, Live-Verbrauchsmonitor, Abschlussanalyse nach Stage/Provider/Modell, Budgetabbruch über `termination_reason` von Fehler/Nutzerabbruch unterscheidbar, Verbrauch im Report-Export. Die harte Durchsetzung im Report-Pfad ist seit [#978](https://github.com/arn0ld87/agora/issues/978) (31.07.2026) korrekt — ein Budgetabbruch endet auf `stopped`, nicht mehr auf `completed`

Nach dem `0.9.4`-Schnitt (09.08.2026) bis zum `0.9.5`-Schnitt (11.08.2026) kam hinzu:

- **Dokumentbelege mit auflösbarem Anker** ([#1154](https://github.com/arn0ld87/agora/issues/1154)): ein Graph-Fakt mit Dokument-/Chunk-Herkunft aus der Aufnahme wird als `seed_corpus`-Evidence mit Anker auf die konkrete Dokumentstelle geführt. Erst dadurch kann eine zusätzlich agentengestützte Aussage überhaupt `medium` erreichen. Fakten ohne belegte Herkunft bleiben Graph-Relation; Bestandsberichte verlieren beim Laden unbelegte Dokumentbezüge und werden entsprechend abgestuft
- **Der Report weist seinen Simulationsstand aus** ([#1192](https://github.com/arn0ld87/agora/issues/1192)): abgeschlossene Runden, geplante Gesamtzahl und ob die Simulation beim Start der Generierung noch lief. Erfasst wird beim Start, nicht beim Abschluss. Nicht ermittelbar → „unbekannt", keine erfundene Null
- **Nachträglich abgestufte Aussagen weisen ihren Wortlaut aus** ([#1012](https://github.com/arn0ld87/agora/issues/1012)): die Aussagentabelle nennt die Stufe, unter der formuliert wurde; die Übersicht vor dem Fließtext zählt die betroffenen Aussagen. Der generierte Text bleibt bewusst unangetastet
- **Markdown-Export löst seine Belegkennungen auf** (#1181) und **operative Zahlen weisen ihre Herkunft aus** (#1182)
- **Das ReportV3-Artefakt hängt nicht mehr am Status** ([#1315](https://github.com/arn0ld87/agora/issues/1315)): `save_report` schreibt `report-v3.json` auch bei `incomplete`, sofern `build_report_v3` valide durchläuft — vorher fiel der `.md`-Export dieser Reports auf die annotierte Narrative zurück. Der Statuswert selbst bleibt vom #1299-Gating bestimmt. Scheitert der v3-Bau selbst (etwa weil leere `structured_metadata` die Validierung brechen, #1321), bleibt die Narrative der Fallback; sie wird dann als unvollständige Fassung gekennzeichnet und ihre HTML-Konfidenz-Badges werden zu Markdown-Fettung umgesetzt, damit kein unrendertes `<span>` im Download steht. Der Unbelegt-Marker aus #1232 steht seither einmal je Hypothese statt an jeder Fundstelle
- **Die Nachbearbeitungsphase meldet Fortschritt und Phasenzeiten** ([#1187](https://github.com/arn0ld87/agora/issues/1187)) statt stumm zu laufen; der Evidence-Export bleibt sichtbar, solange die Evidenzkarte fehlt ([#1188](https://github.com/arn0ld87/agora/issues/1188))
- **Unbelegte Aussagen bleiben im Reporttext als Hypothesen erkennbar** ([#1232](https://github.com/arn0ld87/agora/issues/1232)): Trifft eine Section-Hypothese denselben Satz im narrativen Markdown, erhält er dort einen sichtbaren Unbelegt-Marker. Die ersten fünf Section-Datenlücken stehen direkt darunter; bei weiteren nennt der Report die Restzahl und verweist auf den Evidence-Export
- **Die Claim-Bindung bewertet alle Section-Belege vor dem Kürzen** ([#1217](https://github.com/arn0ld87/agora/issues/1217)); ein einzelner stützender Beleg bleibt gemäß ADR-0002 als sichtbarer `low` Claim erhalten, während Aussagen ohne stützende Evidence weiter als Hypothese und Data-Gap geführt werden ([#1233](https://github.com/arn0ld87/agora/issues/1233))
- **Kein Run bleibt nach gescheitertem Start auf `pending`** ([#1176](https://github.com/arn0ld87/agora/issues/1176)); Persona-Capping dedupliziert und verteilt über Stakeholdergruppen ([#1177](https://github.com/arn0ld87/agora/issues/1177)); das finale Speichern eines Persona-Profils verliert keine Felder mehr ([#1186](https://github.com/arn0ld87/agora/issues/1186))
- **Zentraler `max_tokens`-Boden von 32k** für generative Calls ([#1168](https://github.com/arn0ld87/agora/issues/1168), `LLM_MAX_TOKENS_FLOOR`)
- **Rundenzahl und Run-Budget überleben den Dashboard-Start bis zur Simulation** ([#1234](https://github.com/arn0ld87/agora/issues/1234)) über den Query-Vertrag `runParamsQuery.ts`, auch bei einem Reload auf der Simulationsroute
- **Prepare und Gemini-Tool-Turns sind kollisionsfest** ([#1271](https://github.com/arn0ld87/agora/issues/1271)): Ein zweiter Prepare-Start wird vor Run- und Task-Erzeugung mit HTTP 409 abgelehnt; der CAMEL-Adapter übernimmt Gemini-3-Thought-Signaturen in die rekonstruierte Tool-Historie
- **Interviewzitate verankern nicht mehr auf erfundene Dokumentstellen** ([#1300](https://github.com/arn0ld87/agora/issues/1300)): `source_kind=agent_quote`-Evidence (Interview-Aussagen) darf keinen `seed_doc:`-Anker mehr tragen — der Contract-Validator `agent_quote_rejects_seed_doc_anchor` lehnt die Kombination ab, die Producer-Boundary entfernt fabrizierte Anker beim Schreiben, und bereits persistierte `schema_version=3`-Reports mit der alten Kombination werden beim Laden migriert statt mit HTTP 422 abgewiesen. Der `interview_agents`-Tool-Ergebnistext zeigt die vergebene `ev_`-ID direkt unter jeder Antwort, damit das Modell sie zitieren kann, statt eine zu erfinden

Der Stand ist `0.9.5` Stability Beta; die innerhalb der `0.9.x`-Linie noch offenen Freigabekriterien stehen unter `0.9.0` in [`ROADMAP.md`](../ROADMAP.md). Die E2E-Kernpipeline wird seit 31.07.2026 als verpflichtender Pull-Request-Check erzwungen. Die Migration der v3-Inhaltskomponenten (`Step2EnvSetup`/`Step3Simulation`/`Step4Report`) in v4-Wrapper ist abgeschlossen ([#922](https://github.com/arn0ld87/agora/issues/922), PR #938); der credential-basierte Runtime-Provider-Override (`useRuntimeLlmOptions`) ist entfernt. Der `/home`-Redirect auf `/dashboard` ist umgesetzt ([#915](https://github.com/arn0ld87/agora/issues/915), ADR-0010); `Home.vue` bleibt bis `1.0.0` physisch erhalten.

## E2E-Smokes

[Issue #739](https://github.com/arn0ld87/agora/issues/739) (sechs rote E2E-Smokes reparieren) ist **geschlossen** (19.07.2026). Seither laufen die sechs Kern-Smokes (Health, Upload + Graph, Minimalreport, Report-Modi, Golden-Gate Accessibility, AiModelPicker) im `e2e-smokes`-Workflow durchgehend grün: **20 von 20 aufeinanderfolgenden Läufen** über `push` und `pull_request` zwischen 21.07.2026 und 22.07.2026 (letzter Lauf auf Commit `37320dbf`) sind erfolgreich, kein einzelner Flake in dieser Serie.

Die Erzwingung ist umgesetzt (Stand 31.07.2026): `main` ist branch-protected und führt **17 Required Status Checks**, darunter alle sechs E2E-Kern-Smokes sowie die beiden PR-Smoke-Gates. `strict: true` (Branch muss vor dem Merge aktuell sein), `enforce_admins: true`, Force-Pushes und Löschung deaktiviert, `required_approving_review_count: 0` (Single-User-Betrieb).

Verifikation: `gh api repos/arn0ld87/agora/branches/main/protection`. Konfiguration und Rollback in [`docs/runbooks/e2e-required-check.md`](runbooks/e2e-required-check.md).

> Der frühere Text an dieser Stelle behauptete, `main` habe keine Branch-Protection (mit einem 404 als Beleg). Das war zum Zeitpunkt des CI-/E2E-Audits am 31.07.2026 nachweislich überholt — es bestanden bereits 15 Required Checks.

## Quality Gates

| Gate | Status |
|---|---|
| Backend PR Smoke: Ruff + Mypy + Contract-Tests | verpflichtend |
| Frontend PR Smoke: Lint + Typecheck + Unit-Tests + Build | verpflichtend |
| Backend Full Tests + Coverage | `push:main` oder Label |
| Frontend Full Tests + Coverage | `push:main` oder Label |
| Schemas und Contract-Spiegel | vorhanden |
| E2E-Kernpipeline | `pull_request`-Trigger aktiv; **als Required Check erzwungen** (alle sechs Smokes, Stand 31.07.2026) |
| Branch-Protection `main` | aktiv — 17 Required Status Checks, `strict: true`, `enforce_admins: true`, keine Force-Pushes, keine Löschung |

Lokale Befehle:

```bash
bash scripts/pre-push-gate.sh
bash scripts/pre-push-gate.sh backend
bash scripts/pre-push-gate.sh frontend
bash scripts/pre-push-gate.sh schemas
```

## Coverage-Baseline

Neu gemessen am 11.08.2026 auf `b72a443b`.

| Bereich | letzte Messung | Ergebnis | vorher | CI-Schwelle |
|---|---|---:|---:|---:|
| Backend gesamt | 11.08.2026 | 79,00 % | 66,00 % (10.06.) | 60 % |
| Frontend Statements | 11.08.2026 | 71,03 % | 50,46 % (10.05.) | 28 % |
| Frontend Branches | 11.08.2026 | 58,44 % | 39,56 % (10.05.) | 28 % |
| Frontend Functions | 11.08.2026 | 64,19 % | 38,59 % (10.05.) | 28 % |
| Frontend Lines | 11.08.2026 | 73,32 % | 52,50 % (10.05.) | 28 % |

Backend: 26993 Statements, 5542 nicht abgedeckt (`uv run pytest --cov=app`).
Frontend: `bun run test:coverage`; Schwellen stehen in `frontend/vite.config.js`.

**Die CI-Schwellen sind damit wirkungslos geworden.** Die Frontend-Schwelle von
28 % liegt 30 bis 45 Punkte unter dem Istwert, die Backend-Schwelle von 60 %
19 Punkte darunter — ein Rückfall müsste erst einen großen Teil der Suite
zerstören, bevor ein Gate anschlägt. Das Anheben ist eine Code-Änderung und
gehört in ein eigenes Issue, nicht in einen Doku-Sync.

Strukturelle Lücken liegen vor allem in OASIS-/Neo4j-Integrationspfaden, Canvas-/WebGL-Komponenten und großen Wizard-/View-Komponenten.

Im Messlauf schlugen 7 Tests fehl, keiner davon im Produktivcode:

- 5 × `tests/test_sync_status_cache.py` — scheitern am root-eigenen
  `backend/.cache` (siehe Hinweis unter „Tests"), nicht an der Logik.
- 1 × `tests/scripts/test_check_pip_audit_hardstop.py::test_on_hardcutoff_day_list_must_already_be_empty`
  — der Test bildet „heute" mit `datetime.date.today()` (lokal),
  `scripts/check-pip-audit-hardstop.sh` mit `date -u`. Zwischen 00:00 und
  02:00 Europe/Berlin sind das zwei verschiedene Tage, und der Test schlägt
  in diesem Fenster deterministisch fehl. In CI (UTC) fällt das nie auf
  ([#1203](https://github.com/arn0ld87/agora/issues/1203)).

## Kanonische technische Pfade

- API-Verträge: `backend/app/contracts/`
- Frontend-Spiegel: `frontend/src/contracts/` und `schemas/`
- Provider-Erkennung: `backend/app/llm/providers/registry.py::detect_provider`
- Provider-Verbindungen: `ProviderConnection`
- kanonische Route: `AiRoute` / `LlmRoute`
- kanonische Modellauswahl: `frontend/src/components/v4/forms/AiModelPicker.vue`; seit Issue #890 auch im Step-2-Environment-Setup. Eine Auswahl ist eine `AiModelRef` und wird als `ai_model_ref` an `/prepare` gesendet; ohne Auswahl entscheidet die Backend-Präzedenz (Projektprofil vor Workspace-Default). Modellauswahl wird im Frontend nicht mehr persistiert
- aktive Embedding-Konfiguration: `embedding_service.py` und `embedding_migration.py`
- Normalisierung persistierter Evidence-Maps: `evidence_migrations.py::normalize_persisted_evidence_map` — bindende Migrationsreihenfolge, Aufrufer sind der Lese-Pfad `GET /api/report/<id>/evidence` und der JSON-Export. Migrationsschritte nicht einzeln aus neuen Consumern aufrufen ([#987](https://github.com/arn0ld87/agora/issues/987))
- strukturierte LLM-JSON-Outputs: `LLMClient.chat_json` mit Pydantic-Schema (strict-json_schema-Pfad); rohe OpenAI-Clients für strukturierte Outputs vermeiden
- Subagent-Dispatch: Routing-Matrix in [`docs/runbooks/subagent-routing.md`](runbooks/subagent-routing.md) und [`CLAUDE.md`](../CLAUDE.md); Agentdefinitionen unter `.claude/agents/*-m3.md`. Der `-m3`-Suffix ist seit dem 31.07.2026 nur noch ein historischer Name: die Definitionen trugen `model: MiniMax-M3` (ab 20.07.2026) und waren damit nicht dispatchfähig — sie laufen jetzt auf Anthropic-Modellen (`opus` für den Reviewer, sonst `sonnet`). Die historischen Subagenten ohne Suffix (z. B. `agora-doc-worker.md`) wurden am 27.07.2026 auf denselben Härtungsgrad gehoben.
- Evidence-Gating: ADR-0002-Hartanker. Anker 4 ist zweifach verschärft ([#1160](https://github.com/arn0ld87/agora/issues/1160) B/C, Sign-off 2026-08-09): `verified` verlangt neben `match_score >= 0.85` ein `entailment=SUPPORTED` am selben Evidence-Item (Bestand ohne `entailment` wird beim Laden auf `high` abgestuft), und `persona_stakeholder_group` wird für den Cross-Stakeholder-Vergleich normalisiert (casefold + Whitespace, keine kontrollierte Taxonomie). Additiv daneben: `ReportV3.Claim.confidence_scope` trennt Simulationskonsens von Quellenbindung und wird in der Claim-Tabelle gerendert (#1160 A)
- Entailment-Verdikte: `evidence_entailment.py::classify_evidence`. Eine gemessene Deckung unter `PREDICATE_COVERAGE_THRESHOLD` (0.75) ergibt `CONTRADICTED`; eine *nicht messbare* Deckung dagegen `INSUFFICIENT` mit `predicate_not_measurable` ([#1317](https://github.com/arn0ld87/agora/issues/1317)) — `coverage_ratio` liefert für beide Fälle 0.0, entscheidend ist, ob `_content_tokens` überhaupt ein Inhaltswort übrig lässt. Am Gating ändert das nichts: `verify_prose` behält einen numerischen Satz weiterhin nur bei `SUPPORTED`, die Unterscheidung wirkt auf Begründung, Hypothesen-Rationale und das `contradicts_claim`-Flag

Chat-Routing und Embedding-Konfiguration bleiben getrennte Vertragswelten.

## Bekannte Konsolidierungsschuld

- die fünf klassischen Prozess-Wrapper-Views sind entfernt; ihre benannten Deep-Links bleiben als v4-Redirects kompatibel. `/agora-2026` ist als Designreferenz unter `docs/design-reference/agora-2026/` archiviert und nicht produktiv geroutet; v4-Ballast-Views sind entfernt ([PR #877](https://github.com/arn0ld87/agora/pull/877)). Die Migration der v3-Inhaltskomponenten `Step2EnvSetup.vue`/`Step3Simulation.vue`/`Step4Report.vue` in v4-Wrapper ist abgeschlossen ([#922](https://github.com/arn0ld87/agora/issues/922), PR #938). Der `/home`-Redirect auf `/dashboard` ([#915](https://github.com/arn0ld87/agora/issues/915)) ist umgesetzt
- ein React-/Lovable-Neubau ist als Prototyp umgesetzt, aber nicht als Zielentscheidung freigegeben (Details im nächsten Abschnitt)
- Legacy-LLM-Profile und Provider-Connections besitzen noch Übergangspfade
- der credential-basierte Runtime-Provider-Override (`useRuntimeLlmOptions`) ist entfernt (PR #938); `useEnvForm` führt `modelOption`/`customModel` ohne Persistenz weiter, bis [Issue #903](https://github.com/arn0ld87/agora/issues/903) die Ablösung abschließt
- die Browser-Keys `agora.lastModel` und `agora.lastCustomModel` haben seit Issue #890 keinen produktiven Reader oder Writer mehr; vorhandene Werte werden bewusst nicht gelöscht und bleiben wirkungslose Altlast
- einzelne Provider-Erkennungen beruhen weiterhin auf URL-/Modell-Heuristiken
- Frontend- und Backend-Provider-Vokabular sind nicht an jeder SSE-Grenze synchron

## Frontend-Next-Stand (React/Lovable)

- **Produktiv:** Vue ist die einzige ausgelieferte Frontend-Technologie. `/home` leitet seit [#915](https://github.com/arn0ld87/agora/issues/915) per ADR-0010 auf `/dashboard` um; die klassische Editorial-View `Home.vue` bleibt bis `1.0.0` physisch erhalten. Die Konsolidierung auf genau eine v4-Route je fachlicher Hauptfunktion ist mit [Issue #760](https://github.com/arn0ld87/agora/issues/760) verifiziert abgeschlossen (siehe [#839](https://github.com/arn0ld87/agora/issues/839)). Die v3-Inhaltskomponenten `Step2EnvSetup.vue`/`Step3Simulation.vue`/`Step4Report.vue` sind nach v4 migriert und werden nicht mehr über v4-Wrapper geroutet ([#922](https://github.com/arn0ld87/agora/issues/922), PR #938).
- **Prototyp:** Ein Lovable-Projekt („Agora Runs Dashboard", angelegt 2026-07-16) existiert und wurde substanziell umgesetzt (23 Edits, TanStack-Router-SPA, 12 Routen, shadcn/ui). Es ist derzeit **nicht veröffentlicht** (`is_published: false`, keine URL) und **nicht** produktiv verdrahtet — weder Docker-Compose, GitHub-Workflows noch das Root-`package.json` referenzieren es. Der React-Code liegt vollständig außerhalb dieses Repositories. Die tatsächliche Funktionsvollständigkeit des Prototyps ist nicht codegeprüft belegt, sondern nur durch Commit-Aussagen behauptet.
- **Release-Status:** Kein Teil des freigegebenen Produktpfads vor `1.0.0`.
- **Zukunft:** Über eine spätere Migration ist keine Entscheidung getroffen.
- Beleg: [`docs/epics/frontend-next/2026-STATUS.md`](epics/frontend-next/2026-STATUS.md).

## Security und Betrieb

- Betriebsmodell: experimentelles Single-User-System, kein öffentliches SaaS
- Zugriff bevorzugt über Tailscale, VPN oder Reverse Proxy
- API-Auth über `AGORA_AUTH_TOKEN`
- SSE und Downloads über signierte Tickets
- Secrets werden nicht in Report-/Simulation-Artefakte serialisiert
- Credential-behaftete LLM-Requests erzwingen HTTPS; `http://` ist nur für lokale/private Hosts zulässig, dokumentierte Ausnahme über `AGORA_LLM_ALLOW_INSECURE_HTTP` (Issue #1103)
- Readiness prüft Neo4j, Redis, Upload-Verzeichnis und Embedding-Konfiguration
- Dependency-Ausnahmen werden im [`dependency-risk-register.md`](dependency-risk-register.md) geführt
- Ontology-Upload (`/ontology/generate`) räumt bei Datei-I/O-Fehlern zwischen Projektanlage und Service-Übergabe das halb angelegte Projekt zuverlässig auf (Issue #899); ein scheiterndes Aufräumen wird protokolliert, ohne die Fehlerantwort zu verfälschen
- Dokument-Upload schreibt zusätzlich ein Offset-Manifest (`extracted_documents.json`) neben `extracted_text.txt`; der Textblob bleibt unverändert, Projekte ohne Manifest laden weiterhin fehlerfrei ([ADR-0013](decisions/0013-seed-corpus-document-anchor.md), Issue #1152)
- Die Dokumentherkunft läuft durch bis ins Retrieval: der Graph-Build schreibt `document_id`/`chunk_id` auf den Episode-Knoten, und `SearchResult`, `InsightForgeResult` sowie `PanoramaResult` transportieren sie positionsparallel zur jeweiligen Fakt-Liste (Issue #1152). Ein Fakt ohne eindeutig verifizierbare Herkunft bekommt keinen Anker statt eines geratenen; Bestandsgraphen ohne Dokumentbezug liefern durchgängig `None` und denselben Payload wie zuvor. Das Evidence-Mapping darauf (`EvidenceSourceKind.seed_corpus`, Ankererzeugung) ist mit [#1154](https://github.com/arn0ld87/agora/issues/1154) umgesetzt (09.08.2026); die Identität eines Dokumentbelegs hängt an der Dokumentstelle, nicht am Wortlaut des Fakts

Aktuelle Hardstops:

- NLTK-Advisories: 28.09.2026 gemäß ADR-0004/Risk Register
- ~~Trivy OS-Layer: 30.08.2026~~ — entfällt, aufgelöst am 31.07.2026 ([#772](https://github.com/arn0ld87/agora/issues/772)). CVE-2026-24049 und CVE-2026-23949 kamen nicht aus dem OS-Layer, sondern aus `setuptools/_vendor/` in der Backend-`.venv`, und sind mit `setuptools 83.0.0` behoben.

## Nächste Prioritäten

Die `0.10.0`-Arbeit ist auf vier offene Issues zugeschnitten; `0.9.x` hat keine eigenen Blocker mehr im Tracker.

1. **Reproduzierbare Runs, Manifest und Replay** ([#763](https://github.com/arn0ld87/agora/issues/763)) — Teilstand siehe unten.
2. **Kalibrierungs- und Baseline-Suite für den Produktnutzen** ([#765](https://github.com/arn0ld87/agora/issues/765)), inklusive ehrlicher Hardware-Tiers aus Benchmarks statt Schätzwerten.
3. **Backup, Restore, Upgrade und Release-Artefakte verifizieren** ([#766](https://github.com/arn0ld87/agora/issues/766)).
4. **Stable Single-User Release Gate** ([#767](https://github.com/arn0ld87/agora/issues/767)) als Sammelpunkt für `1.0.0`.

Die Kosten- und Ressourcenbudgets selbst stehen via [#764](https://github.com/arn0ld87/agora/issues/764) — siehe ROADMAP „Kosten und Ressourcen".

Stand Issue-Tracker am 11.08.2026: 12 offene Issues. Ein bekannter, noch nicht triagierter Performance-Befund ist [#1190](https://github.com/arn0ld87/agora/issues/1190) — die Nachbearbeitung pro Abschnitt wächst mit der Evidenzkarte, statt konstant zu bleiben.

Teilstand Reproduzierbarkeit ([#1160](https://github.com/arn0ld87/agora/issues/1160) F): der **stochastische Anteil** eines Simulationslaufs ist seit dem 10.08.2026 wiederholbar — `_sim_common.seed_simulation_rng` seedt den globalen RNG des Subprozesses aus `simulation_config.json::random_seed` oder deterministisch (SHA-256) aus der `simulation_id`; der verwendete Seed steht im Simulationslog. **Nicht** reproduzierbar ist der Report: die LLM-Antworten bleiben nichtdeterministisch. Same-Seed-Same-Report braucht zusätzlich eine Aufzeichnung der Modellantworten ([#763](https://github.com/arn0ld87/agora/issues/763)). Die Profilerzeugung (`oasis_profile_generator.py`) ist bewusst nicht geseedet — Profile werden einmal erzeugt und persistiert, ein Re-Run liest dieselben Dateien.

Die vollständigen Release-Gates stehen in [`ROADMAP.md`](../ROADMAP.md).
