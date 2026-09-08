# API Contracts — Agora Backend ↔ Frontend

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Produktversion:** `0.9.5`

Agora arbeitet **contracts-first**: öffentliche JSON-Grenzen werden im Backend als Pydantic-v2-Modelle definiert, im Frontend als Zod-Schemas gespiegelt und für relevante Verträge als JSON-Schema unter `schemas/` eingecheckt.

Kanonische Quellen:

- Backend-Verträge: [`backend/app/contracts/`](../backend/app/contracts/)
- JSON-Schema-Generator: [`backend/app/contracts/dump_schemas.py`](../backend/app/contracts/dump_schemas.py)
- Frontend-Spiegel: [`frontend/src/contracts/`](../frontend/src/contracts/)
- eingecheckte Schemas: [`schemas/`](../schemas/)
- API-Fehlercodes: [`backend/app/utils/api_errors.py`](../backend/app/utils/api_errors.py)
- Envelope-Helfer: [`backend/app/utils/api_responses.py`](../backend/app/utils/api_responses.py)
- Frontend-Envelope/API-Fehler: [`frontend/src/api/`](../frontend/src/api/)

---

## Contract-Regel

Bei einer Änderung an einer JSON-Grenze gehören in **denselben Slice**:

1. Pydantic-Vertrag,
2. API-Serialisierung/Validierung,
3. Zod-Spiegel,
4. generiertes JSON-Schema, soweit der Vertrag exportiert wird,
5. Backend-/Frontend-Regressionstests,
6. `dump_schemas --check`.

Dataclasses oder handgeschriebene Inline-Dicts sind für neue öffentliche API-Verträge keine Ersatzlösung.

---

## Response-Envelopes

### Regulärer Erfolg

Typischer Shape:

```json
{
  "success": true,
  "data": {},
  "meta": {}
}
```

Je Endpunkt können zusätzliche vertraglich definierte Felder wie `count`, `message` oder Cursor-Metadaten existieren. Nicht jede erfolgreiche Response muss denselben generischen `data`-Typ besitzen; der **konkrete Contract** ist führend.

### Regulärer Fehler

Typischer Shape:

```json
{
  "success": false,
  "code": "validation_failed",
  "error": "Eingabe ungültig",
  "details": {}
}
```

Regeln:

- UI-Logik soll auf stabile Codes/strukturierte Details reagieren, nicht auf String-Matching der Fehlermeldung.
- rohe Exception-Texte, Hostnamen, Treiberdetails oder Dateipfade gehören ins Log und nicht ungefiltert in die API-Antwort.
- Streaming- und Datei-Download-Endpunkte dürfen bewusst vom JSON-Envelope abweichen.

---

## ApiErrorCode-Katalog

Der aktuelle `ApiErrorCode`-Katalog enthält **24** Werte. Die Liste im Code ist die SSoT:

### Anfrage/Validierung

- `invalid_id`
- `not_found`
- `validation_failed`
- `bad_request`
- `method_not_allowed`

### Auth

- `auth_required`
- `auth_invalid`
- `auth_forbidden`

### Rate-Limit/Timeout

- `rate_limited`
- `timeout`

### Infrastruktur

- `service_unavailable`
- `neo4j_unavailable`
- `llm_unavailable`

### Ontologie/Workflow

- `ontology_missing`
- `ontology_generation_failed`
- `simulation_not_prepared`
- `simulation_already_running`
- `simulation_prepare_in_progress`
- `persona_review_required`
- `graph_build_in_progress`

### Upload

- `upload_too_large`
- `unsupported_format`

### Generisch

- `internal_error`
- `not_implemented`

HTTP-Status und zusätzliche `details` hängen vom Endpunkt ab. Diese Datei erfindet deshalb keine „Konventions-Statuscodes“ für Codes, die ein konkreter Call anders verwenden kann.

---

## Pydantic ↔ Zod ↔ JSON Schema

Contract-Parität bedeutet mehr als gleiche Feldnamen.

Beispiel aus #1477: `success: Literal[True] = True` war in Pydantic semantisch bequem, machte das Feld im generierten JSON-Schema aber **optional**, während Zod `success: z.literal(true)` verlangte. Der Contract akzeptierte dadurch Backend-seitig ein Objekt, das das Frontend ablehnte.

Die Korrektur lautet heute:

- discriminierende Pflichtfelder ohne Default, wenn sie im Wire-Format tatsächlich Pflicht sind,
- JSON-Schema aus Pydantic regenerieren,
- Zod-Spiegel mit demselben Required-/Literal-Verhalten,
- Regressionstest auf beiden Seiten.

Ein zweites Beispiel ist Python-`casefold` vs. JavaScript-Lowercasing (#1482). Semantische Normalisierung muss bei Cross-Layer-Contracts mit Testvektoren gespiegelt werden, nicht nur ungefähr ähnlich aussehen.

---

## Evidence-Map-Response

`GET /api/report/<id>/evidence` ist kein „Map oder Fehler“-Sonderfall mehr, sondern ein expliziter Union-Contract.

### Variante A — validierte Evidence

Vereinfacht:

```json
{
  "success": true,
  "data": {
    "schema_version": 3
  }
}
```

### Variante B — Evidence bewusst nicht ausgeliefert

Vereinfacht:

```json
{
  "success": false,
  "evidence_omitted": true,
  "reason": "contract_violation"
}
```

Dieser zweite Fall ist für persistierte Altartefakte wichtig: Ein Bericht kann lesbar bleiben, obwohl seine alte Evidence-Map die heute strengere Rollenfamilien-/Cross-Reference-Semantik nicht mehr erfüllt. Die API darf dann nicht so tun, als sei die Evidence validiert.

Exportpfade sind teilweise absichtlich strenger, weil ein ZIP/CSV eine invalidierte Evidence-Datei sonst als geprüftes Artefakt materialisieren würde.

Kanonische Dateien:

- `backend/app/contracts/report_contract.py`
- `frontend/src/contracts/reportContract.ts`
- `schemas/evidence-map-response.schema.json`

---

## Run- und Reportstatus

`RunStatus` und `ReportStatus` sind **nicht** austauschbar.

Ein Report kann fachlich `INCOMPLETE` und trotzdem auslieferbar sein. Der Run-/Resume-Pfad muss diesen Status transportieren, statt alles außerhalb von `COMPLETED` pauschal auf `failed` zu mappen (#1479).

Für Consumer gilt:

- technischer Runstatus beschreibt den Ausführungszustand,
- `metadata.report_status` kann die Ergebnisqualität des Reports genauer benennen,
- Degradierungen sind maschinenlesbar und dürfen nicht nur im Log existieren.

---

## Run-Degradierungen

`RunDegradationModel.component` ist ein striktes Literal-Vokabular. Neue Komponenten müssen gleichzeitig in Backend, Zod und Tests ergänzt werden. Aktuelle Beispiele umfassen unter anderem:

- `persona_generation`
- `requirement_checker`
- `section_generation`
- `outline_planning`
- `run_cancellation`

Der Zweck ist nicht, jeden Fehler mit einem neuen Status zu erschlagen, sondern technische Ausführung und fachliche Ergebnisqualität getrennt sichtbar zu machen.

---

## Status- und Task-Contracts

Nicht jede historische API-Grenze ist bereits vollständig contracts-first. [#1466](https://github.com/arn0ld87/agora/issues/1466) verfolgt verbleibende Bereiche wie die vollständigen Neo4j-/Disk-Teilbäume von `/api/status` und Task-Responses.

Das ist ein **offener Architektur-Slice**, kein Grund, neue untypisierte Dict-Grenzen hinzuzufügen.

---

## Schema-Workflow

Prüfen:

```bash
cd backend
uv run python -m app.contracts.dump_schemas --check
```

Regenerieren:

```bash
cd backend
uv run python -m app.contracts.dump_schemas
```

Danach immer den Diff unter `schemas/` prüfen. Ein regeneriertes Schema ist kein Freifahrtschein: Wenn sich `required`, Enum-Werte oder Union-Branches unerwartet ändern, ist zuerst der Pydantic-Vertrag zu prüfen.

---

## Frontend-Konsumtion

Grundregel:

- Response an der API-Grenze parsen,
- intern mit validierten Typen arbeiten,
- unbekannte additive Werte dort tolerant behandeln, wo Rückwärtskompatibilität vorgesehen ist,
- einen unbekannten Listeneintrag nicht die komplette bekannte Liste zerstören lassen.

Der Provider-Fall aus #1414 ist das Gegenbeispiel: Ein neuer `provider_kind` durfte ein älteres Frontend nicht dazu bringen, alle bekannten ProviderConnections zu verwerfen.

---

## Keine statischen Testzahlen in diesem Dokument

Frühere Versionen dieser Seite nannten „31 Schema-Tests über 7 Domänen“. Solche Zahlen veralten bei einem aktiven Repo schneller als der Satz, der sie beschreibt. Aktuelle Zähler stehen in [`STATUS.md`](STATUS.md) bzw. werden durch die Testtools selbst erzeugt.
