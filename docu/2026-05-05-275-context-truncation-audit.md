# Slice F · Audit Issue #275 — Context-Truncation 8192 trotz PR #270

**Datum:** 2026-05-05
**Audit-Subagent:** `agora-evidence-auditor` (read-only)
**Issue:** [#275](https://github.com/arn0ld87/agora/issues/275) (`bug(camel): Context-Truncation auf 8192 trotz PR #270 — Container-Rebuild verifizieren`)
**Vorgeschichte:** PR #270 (commit `acb6fef`, gemerged 2026-05-04 13:56 CEST) hat `apply_camel_context_floor()` und `enforce_memory_token_limit()` eingeführt.

## Ergebnis

**Verdachtsfall A bestätigt** — laufendes Container-Image stammt von **vor** dem Merge von PR #270. Kein Code-Patch nötig. Rebuild reicht.

## Belege

### A — Container-Image-Stand (BESTÄTIGT)

| Signal | Wert |
|---|---|
| Image-SHA | `sha256:9d0a748a` |
| Image-Erstellzeit | 2026-05-04 12:33 CEST |
| Commit `acb6fef` (PR #270) gemerged | 2026-05-04 13:56 CEST |
| Δ Image-Build vs. Patch-Merge | **−83 Minuten** (Image älter) |
| `docker exec agora python -c "from scripts._sim_common import …"` | `ModuleNotFoundError: No module named 'scripts._sim_common'` |
| `grep -c apply_camel_context_floor` in `run_twitter_simulation.py` (im Container) | `0` |
| `grep -c apply_camel_context_floor` in `run_reddit_simulation.py` (im Container) | `0` |
| `grep -c enforce_memory_token_limit` in `agent_tools.py` (im Container) | `0` |

`_sim_common.py` ist **neu** in PR #270 (existierte vorher nicht). Der `ModuleNotFoundError` ist ein eindeutiges Indiz für den Pre-Patch-Image-Stand — kein Versionskonflikt, keine Umbenennung.

### B — env-Overrides (WIDERLEGT)

```
OLLAMA_NUM_CTX=262144
LLM_CONTEXT_LIMIT=262144
```

`LLM_MODEL_CONTEXT_LIMITS_JSON` nicht gesetzt. Werte würden den Floor-Patch korrekt auslösen, sobald er im Image vorhanden ist.

### C — andere ContextCreator-Typen (NICHT RELEVANT)

`apply_camel_context_floor()` patcht ausschließlich `ScoreBasedContextCreator.__init__`. Im laufenden Container existiert dieser Patch ohnehin nicht — selbst der `ScoreBasedContextCreator`-Pfad läuft ungepatcht. Eine erweiterte Patch-Strategie auf andere ContextCreator-Klassen ist erst ein Folge-Slice, falls nach Rebuild noch Truncation auftritt.

### D — Nicht-OASIS-Pfad (WIDERLEGT)

`backend/app/utils/llm_client.py:102` liest `OLLAMA_NUM_CTX` aus der Umgebung und setzt `num_ctx` korrekt auf `262144`. Die Truncation-Warnung `limit=8192` stammt aus CAMELs internem `ScoreBasedContextCreator`, nicht aus dem Ollama-HTTP-Client.

### Live-Beweise

- `docker logs --tail 500 agora | grep -E "context-patch|enforce_memory_token_limit|Context truncation"` → **keine Treffer**.
- Patch-Marker `[context-patch] token_limit floor = 262144` und `[enforce_memory_token_limit] agent N: 8192 -> …` fehlen → konsistent mit Verdachtsfall A.
- Truncation-Warnung im aktuellen 500-Zeilen-Fenster nicht reproduziert (kein laufender Sim im Audit-Fenster); User-Reproduktion stammt aus früherem Run vor diesem Audit.

## Empfehlung

1. **Rebuild & Recreate:**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   docker exec agora python -c "from scripts._sim_common import apply_camel_context_floor; print('OK')"
   ```
   Erwartung: `OK`, kein `ModuleNotFoundError`.

2. **Re-Test:** Eine Persona-Generation oder Sim starten, dann
   ```bash
   docker logs --tail 500 agora | grep -E "context-patch|enforce_memory_token_limit"
   ```
   Erwartete Marker:
   - `[context-patch] token_limit floor = 262144`
   - `[enforce_memory_token_limit] agent N: 8192 -> <limit> (model=…)`

3. **Issue schließen,** sobald Rebuild + Re-Test grün. Kein Code-Change nötig.

## Folge-Slices (out of scope hier)

- Falls nach Rebuild andere ContextCreator-Typen oder ein neuer Pfad Truncation produzieren → eigener Slice mit erweitertem Patch (Verdachtsfall C als Eskalation).
- CI-Schutz: Smoke-Test, der nach Build die Marker `[context-patch]` und `[enforce_memory_token_limit]` im Log verifiziert (verhindert Regression nach Image-Skew).
