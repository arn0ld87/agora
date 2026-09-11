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

## Verifizierte, weiterhin offene Architekturblocker

Diese drei wurden in diesem Lauf **nur geprüft und dokumentiert**, nicht angefasst. Sie gehören jeweils in einen eigenen PR — halb reparierte Architektur ist schlechter als klar benannte offene Architektur.

### Durable Background Jobs — OPEN

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

### Embedding-Runtime-SSoT — OPEN

Nachweis am 11.09.2026: `EmbeddingService.__init__` (`app/storage/embedding_service.py`) löst weiterhin gegen `Config.EMBEDDING_MODEL` / `Config.EMBEDDING_BASE_URL` / `Config.EMBEDDING_API_KEY` auf, und beide produktiven Consumer konstruieren argumentlos:

* `app/storage/neo4j_storage.py:69` — `EmbeddingService()`
* `app/services/report_agent/evidence.py:239` — `EmbeddingService()`

Die in der GUI aktivierte Konfiguration steuert damit den Laufzeitpfad nicht. [#1417](https://github.com/arn0ld87/agora/issues/1417) bleibt offen; der dort beschriebene Vorschlag (Store → Provider-Connection → Secret-Store, dann erst `Config.*`) ist ein Architektur-PR, kein Nebenprodukt einer Bugfix-Serie. Halb repariert wäre er schlimmer als offen: ein Consumer aus dem Store, einer aus der Env, und Vektoren zweier Modelle im selben Index.

### Backup / Restore / Upgrade / Rollback — OPEN

`docs/backup-restore.md` beschreibt das Verfahren und sagt selbst, dass die `neo4j-admin`-Syntax vor einem Drill gegen die laufende Version zu prüfen ist. Ein durchgeführter, reproduzierter Fresh-Host-Restore-, Upgrade- und Rollback-Smoke ist nicht belegt. [#766](https://github.com/arn0ld87/agora/issues/766) bleibt offen.

Dokumentation ersetzt den Betriebsnachweis nicht. Der Drill braucht einen frischen Host, ein echtes Backup aus einem echten Lauf und ein protokolliertes Ergebnis — und gehört deshalb in einen eigenen Vorgang mit Umgebung, nicht in einen Code-PR.

## Qualitäts-Gates

Siehe [`../STATUS.md`](../STATUS.md#qualitäts-gates). Kurz:

* mypy-Schuld hinter `ignore_errors`: **266 Fehler in 55 Dateien**, gemessen und gedeckelt, nicht behoben.
* Coverage: **83,82 % Line**, **71,94 % Branch**; Schwellen 82,8 / 70,9.
* Radon: `radon-allowlist.txt` unverändert, kein Deckel angehoben.
