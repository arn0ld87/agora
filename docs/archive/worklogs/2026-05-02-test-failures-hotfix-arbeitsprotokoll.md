# Hotfix · Pre-existing Test-Failures bereinigen

**Datum:** 2026-05-02
**Branch:** `fix/test-failures-hotfix` (Basis: `origin/main` HEAD `512bd9c`)
**Refs:** Repo-Schulden notiert vom parallelen Slice-13-Lauf (Sub-Slice 13, Commit `512bd9c`)
**Auto-Close:** kein Issue (rote Tests waren noch nicht in einem Issue erfasst)

## Ausgangslage

Nach dem Merge von Sub-Slice 13 standen zwei Test-Cluster pre-existing rot. Der parallele Workflow hatte beide als „Repo-Schulden, sollten bald gefixt werden" markiert:

1. `tests/test_report_manager.py::test_report_claim_model_keeps_legacy_fields_and_numeric_score`
2. `tests/test_ontology_generator.py::*` (4 Tests)

Beide reproduzieren auf `origin/main` (`512bd9c`) lokal.

## Root-Cause-Analyse

### Failure 1 — `test_report_claim_model_keeps_legacy_fields_and_numeric_score`

**Symptom:** `assert 'low' == 'medium'` in Zeile 205.

**Ursache:** Test instanziert `ReportAgent.__new__(ReportAgent)` ohne `__init__`. Damit ist `_embed_cache` nicht gesetzt. `_try_get_embedder()` (Z.206 in `report_agent.py`) initialisiert dann `EmbeddingService()` lazy. In Umgebungen mit erreichbarem Ollama gelingt der Init und liefert eine echte Embed-Funktion.

In der nachgelagerten `bind_evidence_to_claim`-Pipeline (Threshold `0.55`) findet der Embedder für die Test-Strings keine Match → `bound = []` → `evidence_items = []` → Anti-Dekorations-Guard greift (Z.640 in `report_agent.py`) → `confidence_score=0.15, label="low"`. Damit kollidiert das mit dem Test-Komment in Z.196, der explizit den **Embedder-Fehler-Pfad** prüfen will (`direct_items` als Fallback).

Der Test verlässt sich also implizit darauf, dass `EmbeddingService()` im Test-Setup scheitert. Auf CI mit Ollama-Stub fliegt das nicht auf, lokal mit lebendem Ollama bricht es.

**Fix (test-only):** `agent._embed_cache = None` setzen. Damit kurzschliesst `_try_get_embedder` den Lazy-Init und liefert `None` → der Test prüft tatsächlich den dokumentierten Fallback-Pfad. Production-Code unverändert.

### Failure 2 — `test_ontology_generator.py::*` (4 Tests)

**Symptom:** `ValueError: LLM_API_KEY not configured` in Zeile 33 (und Folge).

**Ursache:** Tests rufen `OntologyGenerator()` ohne `llm_client`. `__init__` (Z.166 in `ontology_generator.py`) instanziert `LLMClient()`, das in Z.91 hart `LLM_API_KEY` aus `.env` fordert. Die getesteten Methoden — `_validate_and_process` und `_build_user_message` — rühren den LLM-Client nicht an. Der gesamte Init-Pfad ist also Test-Setup-Schaden.

**Fix (test-only):** Lokaler `_DummyLLMClient`-Stub in der Test-Datei, der die Aufruf-API erfüllt aber `AssertionError` bei tatsächlichem Aufruf wirft (defense-in-depth: macht es laut, falls jemand den Test später um echte LLM-Calls erweitert). Production-Code unverändert.

## Scope dieses Sub-Slice

Genau **ein Commit**:

1. `backend/tests/test_report_manager.py` — Embedder-Reset (eine Zeile + Kommentar) im Test 1.
2. `backend/tests/test_ontology_generator.py` — `_DummyLLMClient`-Stub + Injection in 4 Tests.
3. Dieses Arbeitsprotokoll.

**Bewusst NICHT angefasst:**

- `report_agent.py` — Production-Logik korrekt (Anti-Dekorations-Guard ist gewollt).
- `ontology_generator.py` — Eager-LLM-Init wäre eine separate Layer-1-Diskussion. Test-Setup zu fixen ist der ehrlichere Schritt.
- `confidence_calculator.py` — die Formel ist exakt was der Test-Komment beschreibt (Z.193–195: `0.40*0.5 + 0.25*1.0 + 0.20*0.5 + 0.15*0.6 = 0.64`).

## Verifikation

```bash
cd backend && uv run pytest tests/test_report_manager.py::test_report_claim_model_keeps_legacy_fields_and_numeric_score tests/test_ontology_generator.py -q
```

Tatsächlich gemessen: **5 passed**.

```bash
cd backend && uv run pytest tests/ -q
```

Tatsächlich gemessen: **1008 passed, 9 skipped** (Skips: Redis nicht erreichbar — Phase-B-Integration; docker-compose-Snapshot ohne `NEO4J_PASSWORD` in `.env`).

## Geänderte Dateien

- `backend/tests/test_report_manager.py` — Embedder-Reset im Test 1.
- `backend/tests/test_ontology_generator.py` — `_DummyLLMClient`-Stub + 4 Test-Injections.
- `docs/2026-05-02-test-failures-hotfix-arbeitsprotokoll.md` — dieses Protokoll.
