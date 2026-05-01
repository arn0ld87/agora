# Repository Review: arn0ld87/agora

## Kurzbewertung

| Bereich | Bewertung | Begründung |
|---|---:|---|
| Architektur | 7.5/10 | Klare Trennung zwischen Flask-API, Service-Layer, GraphStorage/Neo4j, Event-Bus und Frontend. Die README dokumentiert die Zielarchitektur und die API-Aufteilung nachvollziehbar. |
| Codequalität | 7/10 | Gute Modularisierung, Retry-Wrapper, Validierungsfunktionen und zentrale API-Envelopes. Einzelne Versionen/Runtime-Kommentare sind inkonsistent, und einige Pfade bleiben experimentell. |
| Sicherheit | 6/10 | Viele sinnvolle Härtungen sind vorhanden: restriktives CORS, optionaler Token-Guard, SSRF-Blocker, DOMPurify, Secret-Redaction, Upload-Schutz. Kritisch bleiben Default-Debug/Auth-Setup, schwacher Beispiel-SECRET_KEY, Token in localStorage, bekannte CVE-Ignores und Multi-Worker-Ticket-Replay-Lücke. |
| Tests | 8/10 | CI führt Backend-Tests, Frontend-Tests, Ruff, ESLint, Build, npm audit, pip-audit und Gitleaks aus. Laut README existieren 488 Backend- und 31 Frontend-Tests. Ich habe die Tests nicht ausgeführt. |
| Dokumentation | 7/10 | README und Security-Doku sind ungewöhnlich ausführlich. Problematisch sind widersprüchliche Versionsangaben und falsche/unklare Docker-Compose-Aussagen. |
| Deployment | 5.5/10 | Compose, Dockerfile und Prod-Override existieren, aber Default-Compose und Dockerfile-Ziel passen erkennbar nicht sauber zusammen. Neo4j-Ports werden offen gemappt. |
| Wartbarkeit | 7/10 | Gute Refactoring-Spuren, DI-Container, zentrale Composables, API-Module. Risiko durch komplexe Pipeline, OASIS-Subprozesse, lokale Artefakte und Versionsdrift. |

## Gesamturteil

Das Projekt ist **MVP-tauglich für lokale, vertrauenswürdige Single-User-Setups** und technisch deutlich über einem reinen Prototyp. Es ist aber **nicht produktionsnah**, wenn „produktionsnah“ öffentlich erreichbar, multi-user-fähig, dauerhaft betreibbar und sauber gehärtet bedeutet.

- **Größter technischer Vorteil:** Architektur und Refactoring-Stand sind erstaunlich ordentlich: Service-Layer, DI-Container, Redis/File-Event-Bus, API-Envelopes, Frontend-Composables und CI-Gates sind vorhanden.
- **Größtes Risiko:** Das Default-Betriebsmodell kann zu offen sein: `.env.example` setzt `FLASK_DEBUG=true`, `AGORA_AUTH_TOKEN` ist auskommentiert, Docker bindet intern auf `0.0.0.0`, Compose veröffentlicht Ports. Das ist für lokale Entwicklung bequem, aber als Sicherheitsmodell ungefähr so beruhigend wie ein Haustürschlüssel unter der Fußmatte.

## Faktenbasis

Geprüfte zentrale Dateien:

- `README.md`
- `package.json`
- `frontend/package.json`
- `backend/pyproject.toml`
- `.env.example`
- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `.github/workflows/ci.yml`
- `backend/app/__init__.py`
- `backend/app/config.py`
- `backend/app/utils/auth.py`
- `backend/app/utils/signed_ticket.py`
- `backend/app/api/auth.py`
- `backend/app/api/graph.py`
- `backend/app/api/report.py`
- `backend/app/models/project.py`
- `backend/app/utils/file_parser.py`
- `backend/app/utils/llm_client.py`
- `backend/app/services/web_tools.py`
- `backend/app/storage/neo4j_storage.py`
- `backend/app/storage/neo4j_write.py`
- `frontend/src/api/index.js`
- `frontend/src/components/Step4Report.vue`
- `frontend/src/utils/markdown.js`
- `docu/security-hardening.md`

Nicht bewertet durch Ausführung:

- Tests wurden nicht lokal ausgeführt.
- Docker-Image wurde nicht gebaut.
- Dependency-Audit wurde nicht live ausgeführt.
- Laufzeitverhalten mit Ollama/Neo4j/Redis wurde nicht gestartet.
- Vollständige Historie und alle Commits wurden nicht manuell geprüft.

## Kritische Probleme

### 1. Unsicheres Default-Setup bei Kopie von `.env.example`

**Problem:** `.env.example` setzt `FLASK_DEBUG=true`, lässt `AGORA_AUTH_TOKEN` auskommentiert und enthält einen öffentlichen Platzhalter für `SECRET_KEY`.

**Datei/Pfad:**

- `.env.example`
- `backend/app/config.py`
- `backend/app/utils/auth.py`
- `Dockerfile`
- `docker-compose.yml`

**Risiko:**

Bei `cp .env.example .env` und anschließendem Docker-Start kann das Backend im Debug-Modus ohne API-Token laufen. `Config.validate()` erzwingt `AGORA_AUTH_TOKEN` nur im Nicht-Debug-Modus. `auth.py` macht den Guard zum No-Op, wenn `AGORA_AUTH_TOKEN` leer ist. Docker setzt `FLASK_HOST=0.0.0.0`, Compose veröffentlicht Backend/Frontend-Ports.

**Empfohlener Fix:**

- `.env.example`: `FLASK_DEBUG=false` als sichtbaren Default setzen.
- `Config.validate()` muss bekannte Platzhalter wie `change-me-use-token_urlsafe-32`, `change-me`, `agora`, `password` im Nicht-Debug-Modus hart ablehnen.
- Compose-Beispiele für lokale Entwicklung und Produktivbetrieb strikt trennen.
- API-Port im Default-Compose auf Loopback binden:

```yaml
ports:
  - "127.0.0.1:${AGORA_BACKEND_PORT:-5001}:5001"
  - "127.0.0.1:${AGORA_FRONTEND_PORT:-5173}:5173"
```

### 2. Dockerfile/Compose-Target inkonsistent

**Problem:** `Dockerfile` definiert `dev`, `prod-builder` und `prod`; der letzte Stage ist `prod`. `docker-compose.yml` nutzt nur `build: .` ohne `target: dev`, mappt aber Port `5173` und kommentiert Dev-Verhalten. Ohne explizites Target baut Docker standardmäßig den letzten Stage.

**Datei/Pfad:**

- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `README.md`

**Risiko:**

Der dokumentierte Schnellstart „Frontend unter localhost:5173“ kann mit dem Default-Compose fehlschlagen, wenn tatsächlich der `prod`-Stage gebaut wird und nur Gunicorn auf `5001` läuft.

**Empfohlener Fix:**

Entweder Default-Compose eindeutig als Dev definieren:

```yaml
services:
  agora:
    build:
      context: .
      target: dev
```

oder Default-Compose produktiv machen und Frontend nicht auf `5173` veröffentlichen.

### 3. Signierte Tickets sind bei Gunicorn mit zwei Workern nicht global single-use

**Problem:** `signed_ticket.py` hält eingelöste Tickets in einem prozesslokalen `_seen`-Dict. Die Doku im Code sagt selbst, dass Multi-Worker-Deployments die Single-Use-Garantie pro Worker verlieren. Der Prod-CMD startet Gunicorn mit `--workers 2`.

**Datei/Pfad:**

- `backend/app/utils/signed_ticket.py`
- `Dockerfile`

**Risiko:**

Ein Ticket kann bei zwei Workern theoretisch mehrfach akzeptiert werden, wenn Requests auf unterschiedliche Worker fallen.

**Empfohlener Fix:**

- Ticket-Redemption in Redis speichern, z. B. `SET ticket:<sig> 1 NX EX <ttl>`.
- Alternativ `--workers 1` für Single-User-Local-Deployments explizit dokumentieren, aber das ist nur ein Workaround.

### 4. Bekannte Dependency-Advisories werden in CI ignoriert

**Problem:** Der CI-Security-Job ignoriert sechs CVEs wegen `camel-oasis`, `camel-ai`, `sentence-transformers` und verwandter Pins.

**Datei/Pfad:**

- `.github/workflows/ci.yml`
- `docu/security-hardening.md`

**Risiko:**

Das ist als temporäre Baseline nachvollziehbar, aber produktionsnah ist es nicht. Ignorierte CVEs müssen aktiv getrackt werden, sonst wird „temporär“ zur berühmten permanenten Übergangslösung, also zur eigentlichen IT-Kulturleistung.

**Empfohlener Fix:**

- GitHub Issues je Advisory anlegen.
- CI-Kommentar um Ablaufdatum ergänzen.
- Monatlichen Dependency-Upgrade-Job einführen.
- Prüfen, ob `camel-*` isoliert oder ersetzt werden kann.

### 5. Neo4j-Ports werden offen veröffentlicht

**Problem:** Compose mappt `7474:7474` und `7687:7687`.

**Datei/Pfad:**

- `docker-compose.yml`

**Risiko:**

Auf einem Server sind Neo4j Browser und Bolt je nach Firewall/LAN/Tailnet erreichbar. Auth ist vorhanden, aber unnötige Exposition bleibt Angriffsfläche.

**Empfohlener Fix:**

Für lokale Nutzung:

```yaml
ports:
  - "127.0.0.1:7474:7474"
  - "127.0.0.1:7687:7687"
```

Für echten Betrieb: keine Host-Port-Veröffentlichung, nur internes Docker-Netz.

## Wichtige Verbesserungen

| Priorität | Bereich | Maßnahme | Aufwand | Wirkung |
|---|---|---|---|---|
| Hoch | Security | `.env.example` und `Config.validate()` gegen Debug/Placeholder-Defaults härten | niedrig | Verhindert offene Fehlkonfigurationen |
| Hoch | Deployment | `docker-compose.yml` mit explizitem `target: dev` oder produktiver Port-Strategie korrigieren | niedrig | Schnellstart wird reproduzierbar |
| Hoch | Security | Redis-basierte Ticket-Redemption statt prozesslokalem `_seen` | mittel | Single-use Tickets funktionieren mit mehreren Workern |
| Hoch | Dependencies | CVE-Baseline in Issues überführen und Upgrade-Plan für `camel-*` | mittel | Sicherheitsrisiko wird steuerbar |
| Mittel | Network Security | Neo4j-Ports nur auf Loopback oder gar nicht veröffentlichen | niedrig | Weniger Angriffsfläche |
| Mittel | Frontend Security | Token nicht dauerhaft in `localStorage` ablegen | mittel | XSS-Folgeschaden sinkt |
| Mittel | Versionierung | Versionen in README, root package, frontend, backend und `__version__` synchronisieren | niedrig | Weniger Betriebs-/Release-Verwirrung |
| Mittel | Tests | Security-Regressions für Debug/Auth/Token/Ticket/Port-Doku ergänzen | mittel | Kritische Defaults bleiben stabil |
| Niedrig | Dokumentation | Betriebsmodi „local dev“, „trusted LAN“, „prod-like“ trennen | niedrig | Weniger Fehlbedienung |

## Konkreter Refactoring-Plan

### PR 1: Secure Defaults und Config-Validation

**Ziel:** Keine offene API durch versehentlich übernommene Beispielwerte.

**Änderungen:**

- `.env.example`: `FLASK_DEBUG=false`.
- `Config.validate()` lehnt bekannte Platzhalter in Nicht-Debug hart ab.
- Neue Tests für:
  - Debug false + fehlender Token → Fehler.
  - Debug false + Placeholder `SECRET_KEY` → Fehler.
  - Debug true + fehlender Token → erlaubt, aber Warning.
- README-Schnellstart mit explizitem lokalen Dev-Hinweis.

**Akzeptanzkriterien:**

- `uv run pytest tests/test_config_security.py` grün.
- App startet in Nicht-Debug nicht mit Placeholder-Secret.
- README zeigt sicheren Token-Setup-Befehl.

### PR 2: Docker Compose klar in Dev und Prod trennen

**Ziel:** Reproduzierbarer Start ohne falsche Port-Erwartung.

**Änderungen:**

- `docker-compose.yml` als Dev-Compose mit `target: dev`.
- `docker-compose.prod.yml` als Prod-Override mit nur Backend-Port oder Reverse-Proxy-Hinweis.
- Neo4j-Ports im Dev-Compose auf `127.0.0.1` binden.
- README-Schnellstart korrigieren.

**Akzeptanzkriterien:**

- `docker compose config` zeigt `target: dev`.
- `docker compose up -d --build` startet Vite auf `5173`.
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` zeigt keinen Frontend-Port `5173`.

### PR 3: Ticket-Redemption in Redis

**Ziel:** Single-use-Tickets funktionieren über mehrere Gunicorn-Worker.

**Änderungen:**

- `signed_ticket.consume()` optional mit Redis-Backend.
- Fallback auf In-Memory nur im File-/Dev-Modus.
- Tests für Replay über simulierten Shared Store.
- Doku in `security-hardening.md` aktualisieren.

**Akzeptanzkriterien:**

- Zweiter Consume desselben Tickets schlägt auch bei separater Prozesssimulation fehl.
- Ohne Redis bleibt lokaler Dev lauffähig, aber mit Warning bei mehreren Workern.

### PR 4: Dependency-Baseline abbauen

**Ziel:** Ignorierte CVEs nicht im CI-Kommentar verrotten lassen.

**Änderungen:**

- Je ignorierter CVE ein Issue mit Paket, Upstream-Pin, Risiko, Zielversion.
- `pip-audit`-Ignore-Liste mit Kommentar `expires`.
- Evaluieren, ob `camel-oasis` isoliert in Subprozess/Container mit restriktiveren Rechten laufen kann.

**Akzeptanzkriterien:**

- CI bleibt grün.
- Security-Issues existieren.
- Doku nennt Verantwortlichkeit und Prüffrequenz.

### PR 5: Frontend-Token-Härtung

**Ziel:** Weniger Schaden bei XSS oder Browser-Plugin-Zugriff.

**Änderungen:**

- `localStorage` nur als Dev-Fallback dokumentieren.
- Für Prod: Token per Runtime-Input nur im Memory halten oder Backend-Session mit HttpOnly-Cookie einführen.
- DOMPurify-Konfiguration mit Tests gegen `<script>`, `onerror`, `javascript:`.

**Akzeptanzkriterien:**

- Bestehender Dev-Flow funktioniert.
- Tests prüfen Markdown-XSS-Regression.
- Prod-Doku empfiehlt kein dauerhaftes `localStorage`-Token.

## Security-Fixes

Konkrete Maßnahmen ohne Codeänderung:

1. `.env` für Betrieb sofort härten:

```env
FLASK_DEBUG=false
SECRET_KEY=<token_urlsafe_32_oder_länger>
AGORA_AUTH_TOKEN=<token_urlsafe_32_oder_länger>
AGORA_ALLOW_ANONYMOUS=false
AGORA_CORS_ALLOW_ALL=false
NEO4J_PASSWORD=<starkes_passwort>
```

2. Neo4j nur lokal binden:

```yaml
neo4j:
  ports:
    - "127.0.0.1:7474:7474"
    - "127.0.0.1:7687:7687"
```

3. Backend-Port nicht ungefiltert veröffentlichen:

```yaml
agora:
  ports:
    - "127.0.0.1:${AGORA_BACKEND_PORT:-5001}:5001"
```

4. Bei Tailscale/WireGuard nur explizite Origins setzen:

```env
AGORA_EXTRA_ORIGINS=https://agora.tailnet.example
```

5. CVE-Ignores nicht „akzeptieren“, sondern tracken.

## Tests, die ergänzt werden sollten

- `Config.validate()` lehnt Placeholder-Secrets im Nicht-Debug-Modus ab.
- `FLASK_DEBUG=true` + leerer Token erzeugt Warning und wird als Dev-only markiert.
- `AGORA_ALLOW_ANONYMOUS=true` ist im Prod-Healthcheck sichtbar.
- `?token=` wird in Prod deaktivierbar oder erzeugt Deprecation-Metrik.
- Signed Ticket Replay mit mehreren Worker-Kontexten.
- Redis-Ticket-Redemption `SET NX EX`.
- `docker compose config` Snapshot-Test für `target: dev`.
- Neo4j-Port-Bindings nur Loopback in Dev.
- Markdown-XSS: `<script>`, `<img onerror>`, `[x](javascript:alert(1))`.
- Upload-Grenzen: Dateiendung, PDF-Header, 50-MB-Limit, Path-Traversal-Dateiname.
- SSRF-Blocker: `localhost`, `127.0.0.1`, `10.0.0.1`, `169.254.169.254`, IPv6 `::1`.
- Cypher-Label-Sanitizer gegen Backticks und lange/ungültige Entity-Typen.
- Report-/Simulation-Logs dürfen keine Tokens enthalten.

## Fehlende Dokumentation

Exakt ergänzen:

- `docu/deployment-dev.md`: lokaler Dev-Betrieb mit Vite + Flask.
- `docu/deployment-prod-like.md`: Gunicorn, Reverse Proxy, Auth, CORS, Tailscale/WireGuard.
- `docu/security-threat-model.md`: Assets, Trust Boundaries, Angreifer, bekannte Restrisiken.
- `docu/dependency-risk-register.md`: ignorierte CVEs, Owner, Zielversion, Frist.
- `docu/auth.md`: Token-Header, Ticket-Flow, Query-Token-Deprecation, localStorage-Risiko.
- `docu/backup-restore.md`: Neo4j-Daten, Upload-Artefakte, Reports, Simulationen.
- `docu/operations.md`: Logs, Healthchecks, Ressourcenbedarf, Redis/Neo4j/Ollama-Ausfall.
- `docu/release-process.md`: Versionsquellen synchronisieren, Changelog, Tags, Container-Images.

## Empfehlung

- **Weiterentwickeln:** Ja, aber als lokales/trusted-network MVP.
- **Erst refactoren:** Ja, zuerst Config/Compose/Auth-Defaults.
- **Security-Fixes priorisieren:** Ja, PR 1 bis PR 4 vor weiteren Features.
- **Tests nachziehen:** Ja, besonders Security-Regression und Compose-Snapshot.
- **Deployment verbessern:** Ja, Dev/Prod sauber trennen und Neo4j nicht offen veröffentlichen.

## Klare technische Empfehlung

**Erst Security- und Deployment-Basis stabilisieren, dann Features bauen.**

Reihenfolge:

1. Secure Defaults + Placeholder-Validation.
2. Docker Compose Target/Ports korrigieren.
3. Ticket-Redemption mit Redis.
4. CVE-Baseline aktiv abbauen.
5. Frontend-Token-Handling verbessern.

Danach ist das Projekt stark genug für private Demos, kontrollierte Testnutzer und weitere Produktentwicklung. Für öffentliche Nutzung fehlen echte AuthN/AuthZ, Rollenmodell, Secrets-Management, Dependency-Risikoreduktion und belastbare Betriebsdokumentation.
