# Deployment — Entwicklung

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Scope:** Lokaler Entwicklungsbetrieb auf einer Single-User-Maschine, entweder Host/Bare-Metal oder Docker Compose.

> **Paketmanager ist Bun, Backend-Environment kommt über `uv`.** Keine zweite npm-/pip-Dependency-Wahrheit daneben anlegen.

Für produktionsnahe Härtung siehe [`deployment-prod-like.md`](deployment-prod-like.md).

---

## 1. Voraussetzungen

| Komponente | Anforderung | Zweck |
|---|---|---|
| Git | aktuell | Repository |
| Bun | >= 1.3 | JS-Paketmanager/Task-Runner |
| Node.js | `^22.12.0 || ^24.0.0 || >=26.0.0` | Vite-/Frontend-Testtooling; durch Vitest 5/`install.sh` vorgegeben |
| `uv` | aktuell unterstützte Version | Python-Environment/Dependencies |
| Python | 3.14 über Backend-Toolchain | Backend |
| Neo4j | 5.18+ | Graph-Storage |
| Redis | Compose oder lokaler Service | Events/Tickets/Integration |
| Docker Compose | optional | vollständiger Dev-Stack |
| LLM-/Embedding-Zugang | lokal, HTTP oder unterstützter CLI-Transport | Pipeline |

`install.sh` prüft die für den gewählten Pfad nötigen Werkzeuge und ist der bevorzugte Einstieg.

---

## 2. Host-/Bare-Metal-Setup

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
./install.sh
```

**Nicht zusätzlich `cp .env.example .env` ausführen.** `install.sh` erstellt die Datei bereits und ersetzt bekannte Secret-Platzhalter.

Automatisch erzeugt werden:

- `SECRET_KEY`
- `AGORA_AUTH_TOKEN`
- `AGORA_SECRET_KEY`
- `AGORA_FERNET_KEY`

Danach `.env` für die lokale Infrastruktur konfigurieren, insbesondere:

```text
NEO4J_PASSWORD
NEO4J_URI      (wenn nicht Default)
NEO4J_USER     (wenn nicht Default)
```

LLM-/Embedding-Konfiguration kann je nach Provider über Connections/UI bzw. lokale Defaults erfolgen. Die aktuelle Routingarchitektur steht in [`provider-runtime-settings.md`](provider-runtime-settings.md).

### Start

```bash
bun run dev
```

Typische Endpunkte:

| Dienst | URL |
|---|---|
| Frontend | `http://localhost:5173` |
| Backend | `http://localhost:5001` |
| Liveness | `http://localhost:5001/health` |
| Diagnose | `http://localhost:5001/api/status` |

Bei gesetztem `AGORA_AUTH_TOKEN` ist `/api/status` zu authentifizieren:

```bash
set -a
. ./.env
set +a

curl -fsS \
  -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
  http://localhost:5001/api/status
```

---

## 3. Lokale Infrastruktur

### Nur Neo4j/Redis aus Compose

Wenn Backend/Frontend auf dem Host laufen sollen:

```bash
docker compose up -d neo4j redis
```

Dann verwendet der Host-Betrieb typischerweise:

```text
NEO4J_URI=bolt://localhost:7687
```

Die exakten Compose-Bindings stehen in `docker-compose.yml`; nicht von alten Doku-Screenshots ableiten.

### Ollama lokal

Ollama ist eine mögliche, aber nicht die einzige Runtime. Modellname, Context-Limit und Embedding-Dimension müssen zur konkreten Installation passen.

Beispiel:

```bash
ollama list
```

Keine Modell-ID als „Agora-Default“ dokumentieren, wenn sie nur die lokale Entwicklerinstallation beschreibt.

### CLI-Provider

Ein Provider mit `transport="cli"`, insbesondere `codex_cli`, braucht keine HTTP-Base-URL und keinen Agora-API-Key.

Lokale Voraussetzung:

```bash
codex --version
codex login
```

---

## 4. Docker-Dev-Stack

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
./install.sh --docker
```

Alternativ nach bereits erfolgtem Setup:

```bash
docker compose up -d --build
```

Der Dev-Stack darf Hot-Reload/zusätzliche Hostports besitzen. Für Prod-like gelten andere Mount-/Read-only-/Port-Regeln.

### Diagnose

```bash
docker compose ps
docker compose logs -f agora
docker compose logs --tail 200 neo4j
docker compose logs --tail 200 redis
```

---

## 5. Datenpfade im Dev-Betrieb

Wichtige persistente Bereiche:

```text
backend/uploads/                  Uploads, Simulationen, Reports
backend/uploads/reports/          Report-Artefakte
backend/data/                     Provider-/API-Key-/Routingdaten
backend/instance/                 Instanz-/UI-Settings
backend/.cache/                   regenerierbare Caches
```

Ein früher dokumentierter alternativer Report-Root ist kein aktueller Pfad.

### Bind-Mount-Rechte

Container können Host-Verzeichnisse mit einer anderen UID anlegen. Wenn Host-Tools danach auf `backend/.cache/` oder andere Bind-Mounts nicht schreiben können, Ownership gezielt korrigieren statt mit `chmod -R 777` die nächste Überraschung vorzubereiten.

Beispiel auf Linux:

```bash
sudo chown -R "$USER":"$(id -gn)" backend/.cache
```

---

## 6. Tests und Gates

### Schneller lokaler Gesamtcheck

```bash
bun run check
```

### Repo-Gate

Vor Push entsprechend [`runbooks/pre-push-gate.md`](runbooks/pre-push-gate.md):

```bash
bash scripts/pre-push-gate.sh
```

Je nach Slice können gezielte Modi sinnvoll sein; das Runbook ist führend.

### Backend

```bash
cd backend
uv run ruff check app tests
uv run mypy app
uv run pytest
```

### Frontend

```bash
cd frontend
bun run check
```

### Schemas

```bash
cd backend
uv run python -m app.contracts.dump_schemas --check
```

### STATUS-Sync

Normaler PR-Check soll nicht zwangsläufig teure Testzähler neu schreiben. Für einen dedizierten Refresh:

```bash
bash scripts/sync-status.sh --no-cache
```

---

## 7. Echte Redis-/Neo4j-Integrationstests

Seit #1481 existiert eine eigene Integrationstest-Schicht unter:

```text
backend/tests/integration/
```

Sie testet reale Redis-/Neo4j-Interaktion und ist vom normalen Unit-Testpfad getrennt.

In CI wird der dafür vorgesehene Job mit echten Services ausgeführt; fehlende benötigte Services sollen dort nicht als freundlicher Skip einen grünen Integrationsnachweis vortäuschen.

Lokal nur ausführen, wenn die dafür dokumentierten `AGORA_TEST_*`-/Service-Variablen gesetzt sind.

---

## 8. Embedding-Entwicklung

Embedding-Konfiguration besitzt einen eigenen Store-/Migrationspfad.

Bekannte Grenze #1417: Die UI-/Store-Aktivierung ist noch nicht für jeden Runtime-Consumer die alleinige Wahrheit. Bei Tests eines Embedding-Wechsels deshalb sowohl Store/Connection als auch effektive Runtime-Konfiguration prüfen.

Nie einen bestehenden Vektorindex nur deshalb wiederverwenden, weil die neue Konfiguration dieselbe Dimension meldet. Zwei Modelle können dieselbe Dimension und einen inkompatiblen semantischen Raum besitzen.

---

## 9. Reproduzierbarkeit im Dev-Test

Ein gespeichertes `random_seed` ist noch kein vollständiger Replay-Vertrag. Tests, die Reproduzierbarkeit behaupten, müssen klar benennen, welche Zufallsquelle sie tatsächlich kontrollieren.

Offene Gesamtthemen: #763/#1274.

---

## 10. Häufige Fehler

### `.env` nach `install.sh` überschrieben

Symptom: Secret-Platzhalter oder fehlende Keys tauchen wieder auf.

Behebung: `.env` nicht erneut aus `.env.example` kopieren; `install.sh` als Bootstrap verwenden.

### Provider funktioniert im Test, aber falscher Runtime-Pfad

Prüfreihenfolge:

1. aktive Route,
2. ProviderConnection,
3. Provider-Typ/Transport,
4. Secret-Resolver,
5. erst danach Env-Fallback.

### Mehr Gunicorn-Worker im Dev/Prod-like gesetzt

Nicht als Performance-Tuning übernehmen. Produktion ist aktuell bewusst auf einen Web-Worker begrenzt, solange prozesslokale Job-/Monitorzustände existieren.

### Container-Neustart während Prepare/Report/Graph

Diese Langläufer sind noch nicht vollständig restart-sicher (#1472). Bei Entwicklungs-Recreates mit laufenden Jobs mit verlorener Arbeit rechnen.

---

## 11. Was Dev und Prod-like unterscheidet

| Thema | Dev | Prod-like |
|---|---|---|
| Hot Reload | ja | nein |
| Debug | möglich | aus |
| Root-Filesystem | weniger restriktiv | read-only-orientiert |
| Netzwerk | lokale Entwicklungsports | restriktive Bindings/Proxy |
| Auth | lokale Debug-Ausnahme möglich | Pflicht/Fail-fast |
| Gunicorn | nicht zwingend | 1 Worker, gevent |
| Daten | Test-/Entwicklungsdaten | Backup-/Recovery-Pflicht |

Ein grüner Dev-Stack ist deshalb kein Prod-like-Smoke. Für Release-/Betriebsfragen den gehärteten Pfad separat testen.
