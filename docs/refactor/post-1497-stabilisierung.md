# Post-#1497-Stabilisierung — Befundprotokoll

**Datum:** 11.09.2026
**Basis:** `main` @ `36b13ff6` (Stand zum Zeitpunkt der Aufnahme; enthält #1494, #1496, #1497)
**Branch:** `claude/great-fermi-cg97g1`

Dieses Dokument hält den **heutigen** Prüfstand fest. Es schreibt keine früheren Audits um: [`loc-audit.md`](loc-audit.md) und [`loc-inventory.md`](loc-inventory.md) behalten ihren damaligen Stand und ihre damalige Bewertung.

## Arbeitsweise

Jeder Befund wurde gegen den aktuellen `main` verifiziert, der Datenfluss nachvollzogen, ein reproduzierender Regressionstest geschrieben und dessen Rotfärbung vor dem Fix belegt. Erst danach kam der kleinste fachlich korrekte Fix. Kein Befund wurde symptomatisch geschlossen.

## Behobene Verhaltensfehler

| Befund | Datei | Regressionstest |
|---|---|---|
| Prepare meldet nicht persistiertes `ready` | `app/api/simulation_prepare_state.py` | `tests/api/test_simulation_prepare_state_consistency.py` |
| Hartbudget stoppt wartende Persona-Jobs nicht (Thread + gevent) | `app/services/oasis_profile_batch_results.py` | `tests/services/test_oasis_profile_batch_budget_cancellation.py` |
| Runtime-Override ohne Endpoint | `app/services/prepare_llm.py` | `tests/services/test_provider_resolution_store_precedence.py` |
| Persistierte Interview-Profile unvalidiert | `app/services/graph/interview_helpers.py` | `tests/contracts/test_interview_contract.py`, `tests/services/test_interview_helpers_validation.py` |
| LLM-Antworten der Interviewauswahl/-fragen unvalidiert | dito | dito |
| Skeptikerquote gegen Ausgangspopulation | `app/services/simulation_config_agents.py` | `tests/services/test_skeptic_quota.py` |
| `MAX_CONTEXT_LENGTH` nicht eingehalten | `app/services/simulation_config_context.py` | `tests/services/test_simulation_config_context_cap.py` |
| JSON-Reparatur ignoriert Verschachtelung | `app/services/simulation_config_llm.py` | `tests/services/test_simulation_config_json_repair.py` |
| Kollektiv-Eignungsprompt widerspricht dem Schema | `app/services/oasis_profile_context.py` | `tests/services/test_persona_collective_eligibility.py` |
| Offene Persona-Wertemengen | `app/services/oasis_profile_models.py` | `tests/services/test_persona_closed_value_sets.py` |
| Blocked-URL-Exception leakt Secrets | `app/security/outbound_http.py` | `tests/security/test_outbound_http.py` |
| Nebenklausel erbt Kopf-Prädikat | `app/services/evidence_entailment.py` | `tests/regression/test_evidence_local_clause_predicate.py` |

## Architekturblocker

Diese drei waren zunächst nur geprüft und dokumentiert. Auf ausdrückliche Anweisung wurden sie anschließend bearbeitet — der Stand je Blocker steht unten. Der Befund selbst (Nachweis, dass der Blocker zum Prüfzeitpunkt bestand) bleibt unverändert stehen; er ist die Begründung der jeweiligen Änderung.

### Durable Background Jobs — TEILWEISE GESCHLOSSEN

Nachweis am 11.09.2026: `backend/app/jobs/__init__.py` trägt weiterhin

```python
_BACKEND: str = "thread"
thread = threading.Thread(target=_wrapper, daemon=True)
```

Der Migrationsplan auf RQ steht als Kommentar im Modulkopf, ist aber nicht umgesetzt. Der Modulkopf ist damit der einzige Umschaltpunkt — das ist die gute Nachricht.

Folgeempfehlung: eigener PR gegen [#1472](https://github.com/arn0ld87/agora/issues/1472), in dieser Reihenfolge:

1. **Zuerst den ehrlichen Zustand, nicht die Queue.** `RunnerStatus` fehlt ein `INTERRUPTED`; ein per SIGTERM abgeschnittener Prepare-Thread hinterlässt heute gar keinen Status. Ein `worker_exit`/`atexit`-Hook, der laufende Jobs auf diesen Status setzt und Zwischenstände atomar sichert, ist unabhängig von der Queue-Frage wertvoll und klein.
2. **Dann Heartbeat/Lease je Job**, damit ein Neustart hängende Läufe als hängend erkennt statt als laufend.
3. **Erst danach RQ.** Vorher sind die Schritte nicht idempotent genug, um eine Wiederaufnahme zu tragen — eine persistente Queue, die einen nicht-idempotenten Schritt erneut ausführt, verdoppelt Artefakte statt sie zu retten.

Spontan RQ in einen Stabilisierungslauf zu ziehen wäre genau der Fehler, den dieser Lauf vermeiden soll.

**Umgesetzt (Schritt 1 der Empfehlung, ohne Queue):** Der endlos laufende Status ist weg. `app/jobs/identity.py` gibt jedem Webprozess eine PID plus ein einmaliges Token; `enqueue` stempelt beides ins RunRegistry-Manifest, *bevor* der Thread startet. `reconcile_stale_jobs` erkennt daran beim nächsten Start, dass der Eigentümerprozess weg ist, und markiert `failed`/`process_restart` — denselben Endzustand, den `reconcile_stale_runs` für denselben Sachverhalt schreibt. Für `simulation_prepare` kommt zusätzlich der `SimulationState` aus `preparing` heraus.

Bewusst **kein** neuer `interrupted`-Statuswert: `PREPARING → FAILED` ist im FSM bereits erlaubt, und ein eigener Wert hätte Frontend, FSM und jeden Consumer berührt, ohne mehr auszusagen als der Grund es schon tut.

**Offen bleibt die Wiederaufnahme** — Punkte 2 und 3 der Empfehlung. `_BACKEND` ist weiterhin `"thread"`, es gibt keinen Heartbeat und keinen wiederaufnehmbaren Zwischenstand. Ein abgebrochener Lauf ist jetzt ehrlich gescheitert statt ewig laufend; er ist nicht fortsetzbar.

### Embedding-Runtime-SSoT — GESCHLOSSEN

Nachweis am 11.09.2026: `EmbeddingService.__init__` (`app/storage/embedding_service.py`) löst weiterhin gegen `Config.EMBEDDING_MODEL` / `Config.EMBEDDING_BASE_URL` / `Config.EMBEDDING_API_KEY` auf, und beide produktiven Consumer konstruieren argumentlos:

* `app/storage/neo4j_storage.py:69` — `EmbeddingService()`
* `app/services/report_agent/evidence.py:239` — `EmbeddingService()`

Die in der GUI aktivierte Konfiguration steuerte den Laufzeitpfad damit nicht.

**Umgesetzt:** `embedding_configurations/runtime.py` löst Store → Provider-Connection → Secret-Store auf; die Präzedenz in `EmbeddingService` ist ausdrückliche Argumente > aktive Store-Konfiguration > `Config.*`. Beide argumentlosen Consumer folgen damit dem Store, der Migrationslauf übergibt seine Route weiterhin ausdrücklich. Eine aktive, aber unvollständig auflösbare Konfiguration wirft, statt auf die Env zurückzufallen — ein Rückfall wäre genau die Halb-Übergabe, gegen die der Chat-Pfad absichert. Zusätzlich lehnt `activate()` einen Dimensionswechsel ohne passende Indexversion ab.

Der Modellwechsel bei *gleicher* Dimension bleibt strukturell zulässig; davor schützt weiterhin nur der Migrationslauf.

### Backup / Restore / Upgrade / Rollback — OFFEN (Werkzeug steht)

`docs/backup-restore.md` beschreibt das Verfahren und sagt selbst, dass die `neo4j-admin`-Syntax vor einem Drill gegen die laufende Version zu prüfen ist. Ein durchgeführter, reproduzierter Fresh-Host-Restore-, Upgrade- und Rollback-Smoke ist nicht belegt. [#766](https://github.com/arn0ld87/agora/issues/766) bleibt offen.

Dokumentation ersetzt den Betriebsnachweis nicht. Der Drill braucht einen frischen Host, ein echtes Backup aus einem echten Lauf und ein protokolliertes Ergebnis.

**Umgesetzt: das Werkzeug, nicht der Nachweis.** `scripts/restore-drill.sh` fährt die dokumentierte Reihenfolge und protokolliert jeden Befehl; `backend/scripts/restore_verify.py` prüft die bisherige Prosa-Checkliste maschinell, wobei ein übersprungener Punkt nicht als bestanden zählt. In der Testsuite läuft die Verifikationsphase echt, die übrigen vier nur im Dry-Run — dieser Container hat keinen Docker-Daemon (`docker info`: `dial unix /var/run/docker.sock: no such file or directory`).

**#766 bleibt offen.** Ein Dry-Run-Protokoll ist kein Betriebsnachweis; das Skript schreibt diesen Satz selbst hinein, damit ein solches Log nicht versehentlich an das Issue wandert. Durchführung: [`../runbooks/restore-drill.md`](../runbooks/restore-drill.md).

## Qualitäts-Gates

Siehe [`../STATUS.md`](../STATUS.md#qualitäts-gates). Kurz:

* mypy-Schuld hinter `ignore_errors`: **266 Fehler in 55 Dateien**, gemessen und gedeckelt, nicht behoben.
* Coverage: **83,82 % Line**, **71,94 % Branch**; Schwellen 82,8 / 70,9.
* Radon: `radon-allowlist.txt` unverändert, kein Deckel angehoben.
