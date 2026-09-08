# Graph-/Ingestion-Performance

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Scope:** Laufzeit der Graph-Build-/NER-/RE-Phase diagnostizieren und kontrolliert tunen.

Diese Datei ist **keine Patch-Anleitung mehr**. Die früher hier beschriebenen Codeänderungen (Chunking, Parallelisierung, Provider-Hacks) sind längst in die Produktarchitektur eingeflossen oder überholt. Produktcode per Copy/Paste aus einer Doku zu überschreiben war ohnehin eine bemerkenswert kreative Form von Paketmanagement.

---

## 1. Aktuelle relevante Einstellungen

Die führenden Defaults stehen im Code (`backend/app/config.py` / `backend/app/settings.py`). Baseline 08.09.2026:

| Variable | Default | Bedeutung |
|---|---:|---|
| `GRAPH_CHUNK_SIZE` | `1500` | Zielgröße für Textchunks |
| `GRAPH_CHUNK_OVERLAP` | `150` | Überlappung zwischen Chunks |
| `GRAPH_PARALLEL_CHUNKS` | `4` | Parallelität der per-Chunk NER/RE-Verarbeitung |
| `GRAPH_MIN_ENTITIES` | code/config | Qualitätswarnschwelle |
| `GRAPH_MIN_RELATIONS` | code/config | blockierende Mindestrelationsschwelle |
| `GRAPH_MIN_CHUNK_SUCCESS_RATIO` | code/config | Mindestanteil verwertbarer Chunks |

Bei Abweichungen ist der aktuelle Code führend; [`configuration.md`](configuration.md) erklärt die Variablen.

---

## 2. Wo Zeit entsteht

Ein Graph-Build umfasst typischerweise:

```text
Parsing
→ Chunking
→ Embedding
→ NER/Relationsextraktion per LLM
→ Neo4j-Persistenz
→ Qualitäts-/Statusprüfung
```

Die teuersten Teile sind je nach Setup:

- Provider-Latenz pro NER/RE-Call,
- Anzahl Chunks,
- effektive Parallelität,
- Embedding-Latenz,
- Neo4j-Netzwerk/Transaktionslatenz,
- Provider-Retries/Rate-Limits.

Erst messen, dann drehen. Ein langsamer Lauf mit zehn Retries wird durch acht zusätzliche Worker oft nur schneller dabei, den Provider zu verärgern.

---

## 3. Chunking

### Größere Chunks

Vorteile:

- weniger LLM-Aufrufe,
- weniger Provider-Roundtrips.

Nachteile:

- mehr Inhalt pro Extraktionscall,
- höhere Gefahr, dass kleine Entitäten/Relationen im langen Kontext untergehen,
- größere Prompt-/Outputlast.

### Kleinere Chunks

Vorteile:

- lokalere Extraktion,
- kleinere Einzelcalls.

Nachteile:

- mehr Requests,
- mehr Overlap-Duplikate,
- höhere Gesamtlatenz bei Cloud-Providern.

`1500/150` ist ein aktueller Default, **kein universeller Benchmark-Sweet-Spot** für jedes Modell und jedes Dokument.

---

## 4. Parallelität

`GraphBuildService.add_text_batches()` verarbeitet Chunks parallel. `GRAPH_PARALLEL_CHUNKS` begrenzt diese Parallelität.

Tuning-Regel:

1. mit Default `4` messen,
2. Provider-429/Timeout/Connection-Fehler beobachten,
3. CPU/RAM und Neo4j-Pool beobachten,
4. nur dann kontrolliert erhöhen oder senken.

Eine höhere Zahl kann schaden, wenn:

- Provider Rate Limits greift,
- Neo4j-Verbindungen knapp werden,
- der Host CPU-/Memory-bound ist,
- mehrere Graph-Builds gleichzeitig laufen.

---

## 5. Retry- und Neo4j-Semantik

Ein Netzwerkfehler bedeutet nicht automatisch, dass Neo4j die letzte Transaktion nicht committed hat.

Seit #1460 sind Episode- und Relationswrites auf stabiler UUID retry-idempotent. Der Produktionsbefund war: Neo4j konnte eine Transaktion committen, die Antwortverbindung brach danach ab, und ein Retry führte früher zu Constraint-Fehlern bzw. doppelten Relationen.

Folge für Diagnose:

- Connection-Reset separat untersuchen,
- nicht als erste Reaktion Retry abschalten,
- keine manuelle Dublettenbereinigung durchführen, bevor geprüft wurde, ob der aktuelle Code die idempotenten MERGE-Pfade nutzt.

---

## 6. Provider- und Modellwahl

Die Graph-Stage verwendet das kanonische LLM-Routing. Eine `.env`-Modell-ID ist nicht automatisch die produktive Route, sobald Workspace-/Run-Routing greift.

Prüfreihenfolge:

1. aktive Graph-/NER-Stage-Route,
2. `provider_id`/`provider_type`,
3. ProviderConnection,
4. Modell-ID,
5. effektive Context-/Output-Limits,
6. Retry-/Rate-Limit-Telemetrie.

Keine harte Empfehlung wie „immer Modell X verwenden“ in dieser Datei. Modellkataloge, Preise und Providerverhalten ändern sich schneller als dieses Dokument sinnvoll gepflegt werden kann.

---

## 7. JSON-/Reasoning-Einstellungen

`LLMClient.chat_json` besitzt heute einen eigenen Schema-/Repair-Pfad. Die historischen Flags und Providerquirks gehören in [`provider-runtime-settings.md`](provider-runtime-settings.md) bzw. den Client-Code.

Insbesondere nicht pauschal `LLM_DISABLE_JSON_MODE=true` als Performance-Tipp setzen. Der Legacy-Alias ist veraltet; strukturierte Calls sollen nach Möglichkeit ihren Vertragsmodus behalten.

Wenn ein Provider mit JSON-Schema inkompatibel ist, gezielt den vorgesehenen Runtime-Schalter für genau diesen Fall verwenden und Contract-Tests ausführen.

---

## 8. Embeddings separat betrachten

Embedding-Latenz ist ein eigener Teil des Graph-Builds. Ein Wechsel des Embedding-Modells ist aber keine harmlose Performance-Option.

Vor einem Wechsel: [`embedding-provider-switch.md`](embedding-provider-switch.md).

Bekannte Grenze #1417: aktive UI-/Store-Konfiguration ist noch nicht für jeden Runtime-Consumer die alleinige SSoT.

---

## 9. Messen

### Build-Logs

Relevante Laufzeiten und Fehler nach Graph-/Chunk-Markern filtern:

```bash
docker compose logs agora --since 30m | grep -E "graph_build|Chunk|Neo4j|retry|429|timeout"
```

### Run-/Statussicht

Über Run-/Graph-Status prüfen:

- Anzahl Chunks,
- Erfolg/Fehler,
- Progress,
- Laufzeit,
- Degradation/Qualitätsschwellen.

### Provider-Latenz

Wenn möglich Provider-/LLM-Telemetrie gegen echte physische Calls auswerten. Retried Calls zählen zur realen Laufzeit und bei kostenpflichtigen Providern zur realen Nutzung.

---

## 10. Kontrollierte Experimente

Für ein Tuning-Experiment immer dieselbe Eingabe verwenden und nur **eine** relevante Variable gleichzeitig ändern, z. B.:

```text
A: chunk=1500, workers=4
B: chunk=1500, workers=2
C: chunk=1000, workers=4
```

Messen:

- Gesamtlaufzeit,
- physische LLM-Calls,
- Retry-/Fehlerrate,
- Entitäten/Relationen,
- Chunk-Success-Ratio,
- nachgelagerte Retrieval-Qualität.

Nur Laufzeit zu messen kann eine schnellere, aber fachlich schlechtere Extraktion belohnen.

---

## 11. Docker-/Env-Änderungen

Eine geänderte `.env` wird nicht zuverlässig durch einen simplen Container-`restart` neu eingelesen. Für Compose-Konfigurationsänderungen den Service recreaten:

```bash
docker compose up -d --force-recreate agora
```

Nach Code-/Dependency-Änderung neu bauen:

```bash
docker compose build agora
docker compose up -d --force-recreate --no-deps agora
```

Vorher laufende Prepare-/Report-/Graph-Jobs beachten: Diese sind noch nicht vollständig restart-sicher (#1472).

---

## 12. Was nicht tun

Nicht als Performance-Tuning:

- laufende OASIS-/Backend-Prozesse blind mit `kill -9` beenden,
- `run_state.json` manuell von `failed` auf `ready` umschreiben,
- `simulation_config.json` eines laufenden Jobs per Einzeiler patchen,
- Provider-/Routing-SSoT durch zusätzliche `.env`-Heuristiken umgehen,
- Evidence-/Qualitätsgates abschalten, um einen Lauf schneller „grün“ zu bekommen.

Solche Schritte sind Debug-/Recovery-Eingriffe und brauchen einen konkreten Fehlerfall, keine Performance-Seite.

---

## 13. Aktuelle Priorität

Vor weiterem Mikro-Tuning sind für 0.10 strukturell wichtiger:

- restart-sichere Langläufer (#1472),
- Embedding Runtime SSoT (#1417),
- vollständiges Run-Manifest/Replay (#763/#1274),
- reproduzierbare Simulationstreue (#1236/#1323).

Eine um 20 Sekunden schnellere Graphphase ist nett. Ein reproduzierbar falscher Zustands- oder Evidence-Pfad ist trotzdem das wichtigere Problem.
