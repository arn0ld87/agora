# Run-Qualität: Implementierungsplan
> Status: geprüft; Slice 01 in Implementierung, übrige Abnahme offen

## Appendix A: Evidence Ledger
| Feststellung | Quelle und wörtlicher Beleg | Bestätigt durch |
|---|---|---|
| Outline-Planung bricht vor Modellantwort ab | gns3, report_e5f1df6f5f2c/console_log.txt:4: `Outline planning failed: [codex_cli:provider_unavailable]` und `failed to initialize in-process app-server client: Permission denied` | Laufartefakt |
| Leerer Bericht mit Ersatzgliederung | gleicher Report, meta.json: `markdown_content: ""`, `status: "incomplete"`; run_events.json: `fallback_outline_used: true` | Laufartefakte |
| Simulation nutzt konfigurierte Route gpt-6-luna | sim_c56d9430b50a/simulation_config.json: `llm_model: gpt-6-luna`; tatsächliche Stage-Routen müssen gesondert geprüft werden | Konfiguration, keine vollständige Transportbestätigung |
| Keine eigenständigen neuen Posts | Beide actions.jsonl: je 9 CREATE_POST, alle Runde 0; 54 bzw. 65 Kommentare, 1 bzw. 0 parent_comment_id gesetzt | vollständige Aktionszählung |
| Quellenidentität bricht | extracted_text.txt nennt Dr. Frank Oltmann Chefarzt Gynäkologie; reddit_profiles.json user_id=19 beschreibt 20-jährigen Notfallsanitäter-Auszubildenden | Quelle und Profil |
| Weitere Identitätsbrüche | gleiche source_entity_uuid: Kliniken Hollerau gGmbH → Tobias Neumann; Anke Wübbena → Markus Böhnke; Svenja Meyer → Martin Eilers; Lars Peters → Maren Peters | read-only Evidence-Audit |
| Automatische Rollenprüfung erfasst diese Brüche nicht | run_state.json: `role_conflict_count: 0` trotz obiger Quellabweichungen | Laufartefakte |
| Auch erfolgreiche Planung ist ein festes Preset | backend/app/services/report_prompts/planning.py:70: `All listed sections are mandatory: do not omit, merge, or rename them.` | lokale Datei, Explorer |
| Vertrag verhindert freie Gliederung | backend/app/contracts/report_contract.py:1017: `ReportOutlineModel fehlt Pflichtabschnitte` | lokale Datei |
| Zweite Titelprüfung beendet Fallback vor Textgenerierung | backend/app/services/report_agent/workflow.py:2366: `landet der Lauf garantiert hier` | Explorer mit Quellauszug |
| Bestehender Workflow persistiert Planungsfehler | backend/app/services/report_agent/workflow.py:2698–2721 behandelt FAILED und report.error | Explorer; Handler vor Implementierung konkret lesen |
| Report-Route unterscheidet sich von Simulation | gns3 backend/data/workspace_llm_routing.json: report_generation=`codex_cli/gpt-6-astra`, persona_generation/simulation_rounds=`openai/gpt-6-luna` | persistierte Konfiguration |
| CLI kann im Mount nicht schreiben | gns3 Container: UID/GID 1000; /home/agora/.codex UID 0, Mode 0755, leer | read-only Dateimetadaten; OS-Fehlerpfad nicht vollständig bewiesen |
| Bekannte verwandte Issues sind offen | gh issue list: #1766, #1779, #1778, #1304, #1240, #1662 | GitHub-Liste |
| Zufällige Demografie verdrängt Quellenrolle | backend/app/services/oasis_profile_demographics.py:137–142: `age: exakt`, `Diese drei Felder sind vorgegeben`; core.py:231–243 übernimmt display_name | Explorer mit wörtlichem Beleg |
| Domainprüfung prüft keine gleiche-Domäne-Rollenwechsel | backend/app/services/persona_domain_coherence.py:235–240 akzeptiert gleiche Hauptdomäne | Explorer; gezielte Codeprüfung vor Fix |
| Ein Reply-Pfad lässt parent_comment_id weg | backend/scripts/agent_tools.py:1428–1434 (`_create_manual_action`) übernimmt nur post_id/content; betrifft nur den ReAct-Loop des Einzel-Runners mit aktivierten Agent-Tools, nicht den Referenzlauf (nativer Pfad reicht Antworten durch) | belegt (#1835): `04-ANTWORTZIELE.md`, `backend/tests/scripts/test_reply_targets_and_visible_context.py`; bewusst nicht gepatcht (Gate G1 nein) |
| Kontext im Tool-loop stark gekürzt | backend/scripts/agent_tools.py:1124/1128: Bio 300, Timeline 1500 Zeichen; gilt nur im ReAct-Loop, der nativ-Pfad sieht den Feed mit Deckel 5 je Post | belegt (#1835): `04-ANTWORTZIELE.md`, gemessen, Grenzen unverändert |
| Planprüfung bestanden | unabhängiger gsd-plan-checker: `PASS` nach Konkretisierung beider Titelprüfungen und Regressionen | Review, kein Implementierungsnachweis |
| Mountursache betrieblich korrigiert | gns3 .env, ausschließlich AGORA_CODEX_HOME von /home/schneider/... nach /home/alex/...; Container ohne aktive Jobs neu erstellt; Mount verifiziert, codex_cli_readiness: binary_present=True credentials=ok ready=True | Betriebskorrektur; echter Modellcall separat |

## Ansatz und Scope
Single-Team-Epic (Medium), Repository arn0ld87/agora. Gewählt: Ursachen in atomaren Slices beheben, bestehende Contracts und Evidence-Gates erhalten, danach Stage-Evaluation. Alternative reiner Modellwechsel verworfen: kann Rechtefehler und feste Titelpflicht nicht beheben. Alternative freie unvalidierte Prosa verworfen: würde Evidence-/Vollständigkeitsgarantien aufgeben.

Zielpfad: Quellen-/Persona-Vertrag → quellentreue Profile → validierte Simulationsaktionen → dynamische modellgeplante Outline → bestehende Inhalts-/Evidence-Prüfung → ehrlicher Berichtstatus.

## Aufgaben und Abnahme
| Slice | GitHub | Inhalt / Abnahme | Abhängigkeit | Manuell / Agent-gestützt (Eng-Tage) |
|---|---|---|---|---|
| 01 | #1832 | Outline-Contract akzeptiert szenariospezifische eindeutige Titel; Prompt gibt keine Standardtitel vor; Provider-/Parsingfehler scheitern ohne Ersatzschema; Resume/Budget/inhaltliche Gates bleiben erhalten | keine | 1–2 / 0,5–1 |
| 02 | #1834 | tatsächliche Stage-Route, CLI-Mount/Session/UID klären, Preflight und Upgrade-Anleitung; erfolgreicher neuer Report | 01 für neuen Fehlerpfad, Betriebsdiagnose unabhängig | 0,5–1 / 0,25–0,5 |
| 03 | #1833 | Quellenname, belegte Rolle und Kollektivstatus schützen; zufällige Demografie nicht über Quellenfakten setzen; Regressionen Oltmann/Dirks/gGmbH/Umbenennung; Alias-/47-von-50-Frage klären | keine, eigener Datei-Scope | 2–3 / 1–2 |
| 04 | #1835 | aktiven Laufpfad klären, verschachtelte Antwortziele kanonisch validieren/weitergeben, budgetbewusste Kontextsicherung | 03 vor Qualitätsnachweis | 1–2 / 0,5–1 |
| 05 | #1836 | gepaarte Luna-vs-stärkere Stage-Evals, mindestens 3 Wiederholungen, Blindbewertung, Baselines und Kosten/Latenz; Modellurteil erst aus Ergebnissen | 01–04 und betriebsfähige Routen | 2–3 / 1–2 |

Schätzungen sind Bandbreiten für Implementierung/Review, keine Zusage; Slice 03 enthält zwei getrennte Revieweinheiten (Identität und Aliasdiagnose). Gesamt 6,5–11 manuell / 3,25–6,5 Agent-gestützte Eng-Tage; Begründung: mehrere Prompt-/Validatorpfade, Schema-/Resume-Regressionen und reale wiederholte Evals.

## Sequenz und Verifikation
Slice 01 ändert konkret `backend/app/contracts/report_contract.py` (eindeutige freie Titel statt Preset-Pflicht), `backend/app/services/report_prompts/planning.py` (fragestellungs- und datenbezogene Planung), `backend/app/services/report_agent/planning.py` (keine Ersatzgliederung), `backend/app/services/report_agent/workflow.py` (zweite Default-/Preset-Titelprüfung durch strukturelle Contractvalidierung ersetzen; danach Generierung zulassen). `requirement_checker.py` bleibt als titelunabhängige Inhaltsabnahme des fertigen Textes aktiv; die bestehenden Evidence-/Claim-Gates werden nicht geändert. Explizite Nutzertitellisten werden nur bei tatsächlicher Vorgabe separat geprüft.

Regressionen in `backend/tests/contracts/test_report_contract.py`, `backend/tests/services/test_report_agent_outline.py`, `backend/tests/services/test_report_agent_strict_schema.py`, `backend/tests/services/report_agent/test_partial_report_status.py`, `backend/tests/services/test_partial_report.py` sowie gezielte Workflow-/Prompt-Regressionen: freie Titel erreichen Generierung; fehlende notwendige Inhalte/Evidence werden weiterhin degradiert; Provider-/Parsingfehler persistieren FAILED mit ursprünglicher Ursache ohne planning_complete/Sectionaufruf; BudgetExceededError propagiert; historische valide Outline wird wiederverwendet, markierte Ersatz-Outline neu geplant.

Ausführbare Gates aus `backend/`: `uv run pytest tests/contracts/test_report_contract.py tests/services/test_report_agent_outline.py tests/services/test_report_agent_strict_schema.py tests/services/report_agent/test_partial_report_status.py tests/services/test_partial_report.py -x -q`; danach `uv run python -m app.contracts.dump_schemas --check`; aus Repo-Root `bash scripts/pre-push-gate.sh backend`. Interpreter zuerst auf finale Python3.14 prüfen. Changelog-Fragment `changelog.d/1832-model-planned-outline.md` und `docs/STATUS.md` im selben PR; Upgrade-Runbook wegen veränderter Resume-/Persistenzsemantik prüfen und gegebenenfalls ergänzen.

01 zuerst als Ende-zu-Ende-Tracer: freie Outline oder ehrlicher Fehler bis zum persistierten Status. 02 Betriebsnachweis; 03 Quellenidentität; 04 Dialogmechanik; 05 Qualitäts-/Modellnachweis. Keine unabhängigen Live-Routen global überschreiben. Pro Slice dediziertes Log, Regressionen, Contracts-/Schema-Gate, pytest, Pre-Push-Gate, lokaler Commit, unabhängiges Issue-Review, atomarer PR. Kein Merge/Deployment als stiller Abschluss.

## Querschnitt, Risiken und offene Fragen
- Persistierte Alt-Outlines bleiben lesbar; historische Fallbacks werden beim Resume neu geplant. Keine In-place-Reparatur der historischen Runs.
- Inhaltsvollständigkeit und ADR-0002-Evidence-Hartanker bleiben wirksam; freie Titel bedeuten keine beliebige unbelegte Analyse.
- Status/Fehler müssen ursprüngliche Transportursache erhalten; planning_complete erst nach erfolgreicher validierter Planung.
- Keine neue Datenbank, kein neuer Produktbereich, keine Env-Default- oder Auth-Änderung. Upgrade-Runbook bei CLI-Mount-/Persistenzänderung nachziehen.
- Befürchtete Rollenwechsel innerhalb einer Domäne und falsche Graph-Typen getrennt prüfen; Kollektivguard existiert bereits.
- Noch offen: exakter OS-Pfad beim CLI-Fehler; aktiver Tool-loop/native Pfad (geklärt, #1835: Referenzlauf nativ, siehe `04-ANTWORTZIELE.md`); tatsächliche historische Persona-Route/Promptversion; faire verfügbare stärkere Vergleichsroute. Nicht belegte Punkte bleiben so markiert.
- Related #1766/#1779/#1778/#1304/#1240/#1662 nutzen, keine parallele Doppelimplementierung. Größerer Frontend-Umbau #1790 bleibt außerhalb dieses Epics.

## Assumptions & Checkpoint Decisions
Auftrag umfasst Epic, Triage und Beseitigung; reversible Diagnose, Skill/Prompt und Issue-Erstellung sind autorisiert. Gewählter Ansatz wird durch unabhängige Planprüfung vor Code geprüft. Keine Modellumschaltung aus einem einzelnen Lauf. Laufartefakte und aktueller lokaler Commit unterscheiden sich (Deployment 328d2b8d, Worktree-Baseline 749e7921); Beobachtungen nicht unbesehen auf neueren Code übertragen.

## Appendix B: External Research Sources
- https://developers.openai.com/api/docs/guides/evaluation-best-practices — taskbezogene Evals und paarweise Modellbewertung.
- https://developers.openai.com/api/docs/guides/structured-outputs — Schemaeinhaltung ist von semantischer Richtigkeit zu unterscheiden.

## Context Handoff (for downstream skills)
- Repos read from files: arn0ld87/agora @ 749e7921, Branch codex/run-quality-epic; Deployment gns3 @ 328d2b8d.
- Repos confirmed indexed: keine; Graph-/Repository-Intelligence-Tools in dieser Sitzung nicht verfügbar.
- Closest analogues: report_agent/planning.py, workflow.py, report_contract.py; oasis_profile_core.py/demographics.py/context.py; agent_tools.py.
- Service topology: Flask-Webprozess → Report-Thread/LLMClient; separater OASIS-Subprozess; Datei-/SQLite-Artefakte, Neo4j-Graph, Redis-Livezustand.
- Domain glossary: Quelle = fiktive Vorlage, Persona = synthetische Modellkonstruktion, Beleg ≠ Stimme; Outline-Titel ≠ inhaltliche Pflichtabdeckung.
- Open architectural decisions: keine neue Architektur; Rollenschutz-Vertrag und Evaldetails in fokussierten Slices ausarbeiten.
