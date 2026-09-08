# Embedding-Provider wechseln

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Scope:** Sicherer Wechsel von Embedding-Konfiguration und Vektorindex.

> [!WARNING]
> Ein Embedding-Wechsel ist **keine reine `.env`-Änderung** und ein manueller `DROP INDEX` ist nicht der empfohlene Migrationspfad. Embedding-Modell, Dimension, Indexinhalt und Runtime-Konfiguration bilden gemeinsam einen semantischen Vertrag.

Kanonische Referenzen:

- `backend/app/services/embedding_configuration_store.py`
- `backend/app/services/embedding_migration.py`
- `backend/app/storage/embedding_service.py`
- [ADR-0007](decisions/0007-embedding-configuration-and-index-migration.md)
- [`provider-runtime-settings.md`](provider-runtime-settings.md)
- [`configuration.md`](configuration.md)

---

## 1. Warum ein Modellwechsel eine Migration ist

Ein Vektorindex enthält Zahlen, deren Bedeutung vom konkreten Embedding-Modell abhängt.

Zwei Modelle können:

- unterschiedliche Dimensionen besitzen, **oder**
- dieselbe Dimension besitzen und trotzdem inkompatible semantische Räume erzeugen.

Deshalb reicht diese Prüfung nicht:

```text
alte Dimension == neue Dimension
```

Sie beweist nur Formkompatibilität, nicht semantische Kompatibilität.

Ein Index mit gemischten Embeddings verschiedener Modelle kann technisch gültige Vektoren enthalten und fachlich trotzdem unbrauchbare Similarity-Ergebnisse liefern. Das ist die unangenehmste Fehlerklasse: kein Crash, nur falsche Antworten.

---

## 2. Aktuelle Architektur

Embedding-Konfiguration ist **vom Chat-/LLM-Routing getrennt**.

Persistente Konfiguration:

```text
EmbeddingConfigurationStore
```

Migration:

```text
EmbeddingMigrationService
```

Runtime-Verarbeitung:

```text
EmbeddingService
```

Die UI/API verwaltet Embedding-Konfigurationen und deren Aktivierung über eigene Endpunkte; siehe [`api.md`](api.md).

---

## 3. Bekannte Runtime-SSoT-Lücke (#1417)

Der aktuelle Code besitzt noch eine wichtige Grenze:

> Einige produktive Runtime-Consumer können weiterhin `Config.EMBEDDING_*` aus der Umgebung lesen, obwohl im `EmbeddingConfigurationStore` eine andere Konfiguration als aktiv markiert ist.

Das bedeutet:

```text
UI zeigt Konfiguration B aktiv
        ≠ garantiert
Runtime verwendet überall Konfiguration B
```

Bis #1417 geschlossen ist, muss ein Operator bei einem Wechsel **beide Ebenen kontrollieren**:

1. aktive Store-/Connection-Konfiguration,
2. effektive Runtime-/Env-Konfiguration der betroffenen Consumer.

Die UI allein ist derzeit kein vollständiger Beweis für den produktiven Embedding-Pfad.

---

## 4. Unterstützter Wechselpfad

### Schritt 1 — Istzustand erfassen

Vor der Änderung dokumentieren:

- aktives Embedding-Modell,
- Provider/Endpoint,
- Vektordimension,
- betroffene Indexe,
- aktueller Graph-/Projektbestand,
- Backup-Stand.

### Schritt 2 — Backup

Vor einer Re-Embedding-/Indexmigration mindestens Neo4j und relevante Konfigurationsdaten sichern.

Siehe [`backup-restore.md`](backup-restore.md).

### Schritt 3 — neue Embedding-Konfiguration anlegen/testen

Die neue Konfiguration über den `EmbeddingConfigurationStore`/die vorgesehenen API-/UI-Pfade anlegen und deren Verbindung testen.

Nicht einen Chat-Provider auswählen und annehmen, dass daraus automatisch das Embedding-Modell folgt.

### Schritt 4 — Migration erzeugen

Den vorgesehenen Embedding-Migrations-Lifecycle verwenden. Die API besitzt dafür eigene Migration-Endpunkte; siehe [`api.md`](api.md).

Der Lifecycle schützt den alten Index, bis der neue Zustand validiert ist, und soll einen definierten Fehler-/Rollback-Pfad bieten.

### Schritt 5 — Re-Embedding

Alle betroffenen Objekte müssen mit dem neuen Modell konsistent neu eingebettet werden. Mischzustände alter und neuer Embeddings sind zu vermeiden.

### Schritt 6 — Validierung

Mindestens prüfen:

- erwartete Dimension,
- vollständige Abdeckung der zu migrierenden Objekte,
- Retrieval-Smoke mit bekannten Beispielen,
- keine Query-/Insert-Dimensionsfehler,
- aktiver Runtime-Consumer verwendet tatsächlich die neue Konfiguration.

### Schritt 7 — Aktivierung/Freigabe

Erst nach erfolgreicher Validierung den neuen Zustand als kanonisch verwenden bzw. den Migrationsjob abschließen.

---

## 5. Kein manueller `DROP INDEX` als Standardrezept

Die alte Doku empfahl:

```cypher
DROP INDEX ...
```

als normalen Providerwechsel. Das ist nicht mehr der freigegebene Standardpfad.

Warum:

- zerstört den alten funktionierenden Index vor erfolgreicher Validierung,
- erschwert Rollback,
- kann bei einem Fehler mitten im Re-Embedding einen unbrauchbaren Zwischenzustand hinterlassen,
- umgeht den vorgesehenen Migrations-/Audit-Lifecycle.

Manuelle Cypher-Eingriffe sind Recovery-/Engineering-Maßnahmen und benötigen einen konkreten Grund sowie ein Backup, nicht bloß eine neue Modell-ID.

---

## 6. Dimensionen

`VECTOR_DIM` muss zur effektiven Modellantwort passen. Bekannte Modell-/Dimensionswerte können im Code validiert werden; der Runtime-Probe ist aber entscheidend.

Beispiel eines Diagnose-Checks im Backend-Environment:

```bash
cd backend
uv run python - <<'PY'
from app.storage.embedding_service import EmbeddingService

svc = EmbeddingService()
vector = svc.embed("Agora Embedding Probe")
print("model:", svc.model)
print("dimension:", len(vector))
PY
```

Dieser Test zeigt den **effektiv konstruierten Runtime-Service**. Wegen #1417 sollte das Ergebnis mit der in UI/Store aktivierten Konfiguration verglichen werden.

---

## 7. Provider-Wechsel: Beispiele

### Lokal → Cloud

Vorher beispielsweise ein lokaler Ollama-Embeddingdienst, danach ein OpenAI-kompatibler Cloud-Endpunkt.

Zu prüfen:

- API-Key/Secret-Store,
- HTTPS/Transport-Security,
- Modell-ID,
- Dimension,
- Datenschutz/Datenfluss,
- Kosten/Budget,
- vollständiges Re-Embedding.

### Cloud → lokal

Zusätzlich prüfen:

- Modell lokal vorhanden,
- Endpoint aus Backend/Container erreichbar,
- Dimension/Modellversion korrekt,
- Ressourcenbedarf auf Host,
- kein alter Cloud-API-Key bleibt versehentlich als Runtime-Fallback aktiv.

### Modellwechsel mit gleicher Dimension

Trotz gleicher Dimension: vollständige Migration/Re-Embedding erforderlich, sofern es ein anderes semantisches Modell ist.

---

## 8. API-/UI-Migrationspfad

Die aktuellen Embedding-Endpunkte umfassen unter anderem:

```text
/api/llm/embedding/configurations
/api/llm/embedding/configurations/active
/api/llm/embedding/migrations
/api/llm/embedding/migrations/<job_id>
```

Die konkrete Request-/Response-Form kommt aus Pydantic-Verträgen und [`api.md`](api.md), nicht aus kopierten JSON-Beispielen in diesem Dokument.

---

## 9. Rollback

Ein sicherer Rollback bedeutet:

1. alter Index/alte Daten sind noch vorhanden oder aus Backup wiederherstellbar,
2. vorherige Embedding-Konfiguration kann wieder aktiviert werden,
3. Runtime verwendet nachweislich wieder diese Konfiguration,
4. Retrieval-Smoke gegen den alten Zustand ist grün.

Nur die `.env` zurückzusetzen reicht nicht, wenn Indexdaten bereits mit dem neuen Modell überschrieben wurden.

---

## 10. Abnahmecheckliste

Vor Abschluss eines Provider-/Modellwechsels:

- [ ] Backup vorhanden.
- [ ] neue Connection/Config erfolgreich getestet.
- [ ] effektive Runtime-Konfiguration ermittelt.
- [ ] Dimension stimmt mit Modellantwort überein.
- [ ] betroffene Daten vollständig re-embedded.
- [ ] kein gemischter semantischer Index.
- [ ] Retrieval-Smoke mit bekannten Beispielen grün.
- [ ] alter Zustand für Rollback noch verfügbar.
- [ ] #1417 berücksichtigt: Store/UI und Runtime stimmen tatsächlich überein.

Ein grüner Dimensionscheck allein ist ausdrücklich **keine** vollständige Abnahme.
