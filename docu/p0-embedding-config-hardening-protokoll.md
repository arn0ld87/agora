# P0-Protokoll — Embedding-Konfiguration härten

**Datum:** 2026-04-22  
**Kontext:** Follow-up auf die Kritik zur Kopplung von `EMBEDDING_MODEL` und `VECTOR_DIM`

---

## 1. Problemstellung

Vor diesem Schritt war die Lage riskant:

- der Backend-Default lag bei `EMBEDDING_MODEL=nomic-embed-text` und `VECTOR_DIM=768`
- praktisch dokumentiert und real bevorzugt wurde aber inzwischen häufig `qwen3-embedding:4b` mit **2560 Dimensionen**
- ein falsch gesetztes oder vergessenes `VECTOR_DIM` fiel unter Umständen **erst spät** auf
- der Fehler zeigte sich dann nicht als klarer Konfigurationsfehler, sondern eher indirekt über Neo4j-Index-/Vektorprobleme

Das war insbesondere für frische Setups problematisch.

---

## 2. Ziel

Die Konfiguration sollte so gehärtet werden, dass:

1. bekannte Embedding-Modelle ihre erwartete Dimension **ableiten** können
2. ein Mismatch nicht nur geloggt, sondern **hart erkannt** wird
3. der Backend-Start mit einer **echten Probe** validiert, ob Modell und Dimension wirklich zusammenpassen
4. `.env.example` den tatsächlichen v0.4.0-Stand besser widerspiegelt

---

## 3. Umgesetzte Änderungen

### 3.1 `backend/app/config.py`

Eingeführt:
- `KNOWN_EMBEDDING_DIMS`
- `infer_vector_dim_for_model(model_name)`

Zusätzlich geändert:
- `VECTOR_DIM` wird nun standardmäßig aus `EMBEDDING_MODEL` abgeleitet, wenn keine explizite Env-Variable gesetzt ist
- `Config.validate()` meldet bekannte Modell-/Dimensions-Mismatches bereits auf Konfigurationsebene

### 3.2 `backend/app/storage/embedding_service.py`

Neue Fail-Fast-Funktion:
- `validate_embedding_configuration(...)`

Diese Funktion macht zwei Dinge:
1. statische Prüfung gegen bekannte Modell→Dim-Mappings
2. echte Probe über `EmbeddingService.embed("dimension probe")`

Wenn die tatsächliche Vektorlänge nicht zu `VECTOR_DIM` passt, wird ein **`EmbeddingError`** geworfen.

### 3.3 `backend/app/__init__.py`

Die Flask-App validiert jetzt die Embedding-Konfiguration **beim Startup**, noch vor dem Neo4jStorage-Setup.

Effekt:
- falsche Modell-/Dim-Kombinationen failen **beim Start**
- die App läuft nicht mehr in einen halbkaputten Zustand hinein

### 3.4 `.env.example`

Aktualisiert auf den realen Stand:
- Qwen3-Embedding als empfohlener Pfad
- `VECTOR_DIM=2560`
- dokumentierter Fallback auf `nomic-embed-text` + `VECTOR_DIM=768`
- neue/fehlende Beispielvariablen ergänzt:
  - `AGORA_AUTH_TOKEN`
  - `AGORA_EXTRA_ORIGINS`
  - `AGORA_LOG_FORMAT`
  - `AGENT_LANGUAGE`
  - `REPORT_LANGUAGE`
  - Webtools-Hinweise

---

## 4. Tests / Absicherung

### Neue Testdatei
- `backend/tests/test_embedding_service.py`

Abgedeckte Fälle:
- bekannte Modell→Dim-Inferenz
- statischer Mismatch wird abgewiesen
- Laufzeit-Mismatch zwischen Probe-Vektor und `VECTOR_DIM` wird abgewiesen
- gültige Konfiguration liefert die tatsächliche Dimension zurück

### Zusätzlich angepasst
- Backend-Lint-Whitelist um neue betroffene Dateien erweitert:
  - `backend/app/__init__.py`
  - `backend/app/config.py`
  - `backend/app/storage/embedding_service.py`
  - `backend/tests/test_embedding_service.py`

---

## 5. Verifikation

### Targeted Tests
Befehl:
```bash
cd backend && uv run pytest tests/test_embedding_service.py tests/test_status.py
```

Ergebnis:
- **11/11 Tests bestanden**

### Targeted Ruff
Befehl:
```bash
cd backend && uv run ruff check app/__init__.py app/config.py app/storage/embedding_service.py tests/test_embedding_service.py
```

Ergebnis:
- **bestanden**

### Gesamtcheck
Befehl:
```bash
npm run check
```

Ergebnis:
- Backend Ruff (scoped) → **bestanden**
- Backend Tests → **67 bestanden**
- Frontend Lint → **0 Fehler, 21 Warnungen**
- Frontend Build → **bestanden**

---

## 6. Bewertung

Dieser Schritt beseitigt eine echte Konfigurations-Zeitbombe:

- bekannte Modelle bekommen automatisch den naheliegenden `VECTOR_DIM`
- falsch gesetzte Werte werden früh erkannt
- die Laufzeitprobe verhindert, dass sich Alias-/Provider-Unterschiede still einschleichen
- `.env.example` ist näher am tatsächlich empfohlenen v0.4.0-Setup

Kurz: **früher Fehler, klarerer Fehler, geringere Onboarding-Falle**.
