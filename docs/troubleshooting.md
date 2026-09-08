# Troubleshooting — bekannte Fehlerbilder

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Produktversion:** `0.9.5`

Symptom → wahrscheinliche Ursache → Diagnose → Behebung. Für Fehlercodes siehe [`api-contracts.md`](api-contracts.md), für Konfiguration [`configuration.md`](configuration.md), für Provider-Routing [`provider-runtime-settings.md`](provider-runtime-settings.md).

---

## 1. Datenbank & Infrastruktur

### Neo4j nicht erreichbar

**Symptome**

- `neo4j_unavailable`
- Graph-/Evidence-Operationen schlagen fehl
- `/api/status` meldet Neo4j nicht erreichbar

**Prüfen**

```bash
docker compose ps neo4j
docker compose logs --tail 200 neo4j
docker compose exec neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1"
```

**Typische Ursachen**

- `NEO4J_URI`, User oder Passwort falsch
- Neo4j noch nicht healthy
- Netzwerk-/Compose-DNS-Problem
- Pool-/Connection-Timeout

Agora besitzt Startup-Retry und fork-sichere Storage-Initialisierung. Wiederholte `Failed to write data to connection`-Meldungen sind deshalb nicht automatisch ein bekannter „Neo4j-Bug“; zuerst prüfen, ob Container, Socket oder Gegenstelle tatsächlich beendet/recreated wurden.

### Redis nicht erreichbar

**Symptome**

- Live-Events/Streams fehlen oder werden langsamer
- Ticket-/Event-Bus-Warnungen
- Integrationstests skippen bzw. failen

```bash
docker compose ps redis
docker compose exec redis redis-cli ping
```

`EVENT_BUS_BACKEND=auto` kann auf den File-Pfad zurückfallen. Das macht Redis aber nicht zu einer persistenten Jobqueue: Prepare-/Report-/Graph-Threads bleiben bei Prozessende gefährdet (#1472).

### Stale Simulation nach Container-/Worker-Restart

Seit #1476 läuft Startup-Reconciliation bei App-Start und unter Gunicorn zusätzlich in `post_fork`.

Erwartetes Verhalten bei toter persistierter PID:

```text
pending / processing / paused
        + tote PID
        ↓
failed
termination_reason=process_restart
```

Ein `COMPLETED`/`STOPPED`-State wird ohne beweisbare Run-ID-Zuordnung **nicht** auf irgendein anderes Manifest übertragen.

Wenn Reconciliation bewusst deaktiviert werden soll:

```bash
AGORA_STARTUP_RECONCILIATION=false
```

Das ist ein Debug-/Sonderfall, keine empfohlene Betriebsart.

---

## 2. LLM-Provider und Routing

### Modell geht an den falschen Endpoint

Der alte Reflex „`LLM_BASE_URL` ändern“ ist inzwischen oft die falsche Ebene.

Prüfen in dieser Reihenfolge:

1. aktive Workspace-/Run-Route,
2. `provider_id` + `model_id`,
3. `ProviderConnection`,
4. `transport`/`auth_mode` aus der Provider-Registry,
5. Secret-Resolver,
6. erst dann `.env`-Fallback.

Der frühere Persona-Fehler aus #1418 (Modell aus Route, Endpoint/Key aus `.env`) ist im Code behoben. Wenn dasselbe Muster neu erscheint, ist es ein Regression-Befund und nicht „bekanntes Verhalten“.

### Codex CLI erscheint ohne Base-URL/API-Key

Das ist **korrekt**.

`codex_cli` hat:

```text
transport = cli
auth_mode = session
base_url  = None
```

Diagnose:

```bash
codex --version
codex login
```

Im Container muss das Binary vorhanden und die Session read-only eingebunden sein. Agora darf für diese Route nicht auf einen HTTP-Key aus `.env` zurückfallen.

### Codex-CLI-Simulationsrunden schlagen mit „argument list too long“ fehl

Der produktive Fix übergibt große Prompts über stdin (`codex exec ... -`). Taucht `Errno 7 Argument list too long` auf aktuellem `main` erneut auf, ist das eine Regression im CLI-Aufrufpfad, nicht ein erwarteter Linux-Grenzfall.

### Bedrock-Modell im Katalog, Chat trotzdem 400

Der aktuelle Bedrock-Provider verwendet den OpenAI-kompatiblen Mantle-Pfad. Katalogsichtbarkeit bedeutet nicht automatisch `/v1/chat/completions`-Fähigkeit.

- native Anthropic-/bestimmte GPT-5.x-Bedrock-Modelle können den separaten Converse/SigV4-Pfad benötigen (#1287)
- regionale Kataloge unterscheiden sich
- Base-URL-/Region-Override kann zusätzlich von #1289 betroffen sein

### ProviderConnection gespeichert, aktive Base-URL trotzdem Default

Siehe [#1289](https://github.com/arn0ld87/agora/issues/1289). Ein gespeicherter Connection-Override und die Active-Config sind unterschiedliche Persistenzpfade. Bis zur Behebung den tatsächlich aufgelösten Runtime-Endpoint prüfen, nicht nur das Eingabefeld in der UI.

---

## 3. Embeddings

### UI zeigt aktives Embedding-Modell, Runtime nutzt trotzdem Env

Das ist der bekannte SSoT-Bruch [#1417](https://github.com/arn0ld87/agora/issues/1417).

**Warum gefährlich:** Zwei Embedding-Modelle können dieselbe Dimension haben und trotzdem inkompatible Vektorräume erzeugen. `1536 == 1536` beweist nur gleiche Länge, nicht gleiche Semantik.

Bis zur Behebung:

- aktive Store-Konfiguration prüfen,
- `EMBEDDING_MODEL`/`EMBEDDING_BASE_URL`/`VECTOR_DIM` in Runtime prüfen,
- nach Modellwechsel den vorgesehenen Migrations-Lifecycle verwenden,
- keine Vektoren zweier Modelle in denselben Index mischen.

### Embedding-Dimensionsfehler

Nicht manuell blind Indizes löschen. Der vorgesehene Weg ist der Migration-Lifecycle aus ADR-0007 mit Validierung und Rollback-Möglichkeit.

---

## 4. Persona-Erzeugung

### 20 Personas vorhanden, aber alle regelbasierte Platzhalter

Ein vollständiger Modell-Fallback ist inzwischen **blockierend** und darf nicht mehr als normale READY-Simulation weiterlaufen.

Wenn eine aktuelle Version trotzdem `READY`/normalen Erfolg meldet:

- `generation_source`/Degradierungen prüfen,
- Provider-Route prüfen,
- Prepare-Logs auf Budget-/Providerfehler prüfen,
- Regression gegen #1419/#1420 behandeln.

### Persona gehört plötzlich in falsche Branche/Organisation

Bekannter offener Befund: [#1471](https://github.com/arn0ld87/agora/issues/1471). `detect_domain_drift` kann einen falschen Zusatzkontext übersehen, wenn Persona und Quelle **irgendeine** Domäne teilen.

Nicht nur `profession` leeren. Die erfundene Organisation/Rolle kann weiter im Persona-Text stehen.

### BFW / BFW Leipzig / Berufsförderungswerk Leipzig werden mehrfach Personas

Alias-/Koreferenzauflösung vor dem Persona-Cap ist noch nicht vollständig; siehe [#1470](https://github.com/arn0ld87/agora/issues/1470). Technische Komponenten können ebenfalls zu spät als Persona-Kandidaten aussortiert werden.

---

## 5. Simulation

### Nutzer-Stop endet als `failed`

Auf aktuellem Code sollte ein expliziter Stop als:

```text
status=stopped
termination_reason=user_stop
```

enden (#1474). Ein `failed` nach bewusstem Stop ist ein Regression-Befund.

### Force-Restart wird vom alten Monitor überschrieben

Seit #1474 tragen Monitore Generation-Tokens und dürfen die neue Prozessgeneration nicht finalisieren/aufräumen. Taucht ein solcher Orphan-Finalize erneut auf, `monitor_generation`-/ProcessManager-Tests heranziehen.

### Agent verlässt seine Rolle

Bekannt offen: [#1323](https://github.com/arn0ld87/agora/issues/1323). Im Referenzlauf wurden mindestens 23 starke Rollenwechsel unter 234 texttragenden Aktionen gefunden (~9,8 %).

Das ist kein reiner Stilfehler. Solche Aktionen nicht als belastbare Stakeholder-Evidence behandeln, ohne den Rollenbezug zu prüfen.

### Twitter-Feed wirkt zwischen identischen Läufen zufällig

Bekannt offen: [#1236](https://github.com/arn0ld87/agora/issues/1236). Der OASIS-Twitter-Recommender nutzt `Twitter/twhin-bert-base` über einen Pooler, dessen Gewichte im verwendeten Checkpoint nicht trainiert vorliegen und neu initialisiert werden können.

Ein fester Seed allein macht einen ungeeigneten Pooler nicht semantisch richtig.

---

## 6. Report & Evidence

### Teilreport wird als vollständig angezeigt

Seit #1479 müssen Cancel-, fehlgeschlagene Section-, Requirement- und Fallback-Outline-Pfade zu einem ehrlichen `INCOMPLETE` führen, wenn der Bericht nicht vollständig ist.

Consumer sollen `metadata.report_status` beachten. `INCOMPLETE` kann auslieferbar sein, ist aber nicht dasselbe wie ein vollständiger Report.

### Evidence-Endpunkt liefert 200, aber keine Evidence-Map

Das kann absichtlich sein:

```json
{
  "success": false,
  "evidence_omitted": true,
  "reason": "contract_violation"
}
```

Seit #1477 degradiert der direkte Evidence-Lesepfad bei bestimmten invaliden Altartefakten so, damit der Report lesbar bleibt. Exporte können strenger reagieren.

### Resume lädt Markdown, aber Evidence fehlt

Auf aktuellem Code soll das **nicht** passieren: Evidence wird vor Markdown geschrieben, Markdown ist Commit-Marker, und ein Markdown-only-Orphan wird vor Regeneration entfernt (#1475).

Wenn bei Resume altes Markdown mit neuer/fehlender Evidence gekoppelt wird, ist das ein Persistenz-Regressionsfehler.

### „Nahezu alle“ ist supported, Evidence zeigt nur eine Stimme

Bekannt offen: [#1345](https://github.com/arn0ld87/agora/issues/1345). Relevante Evidence ist nicht automatisch stark genug, einen Quantor zu tragen.

### Report „entdeckt“ eine Aussage, die wörtlich im Seed steht

Bekannt offen: [#1240](https://github.com/arn0ld87/agora/issues/1240). Evaluationsdokumente dürfen Erwartungsantworten/Meta-Konstruktion nicht als gleichrangige Domänen-Evidence ingestieren.

Bis zur Evidence-Typisierung Eval-Seeds sauber trennen: **Szenariofakten hinein, Lösungsschlüssel hinaus.**

---

## 7. Budgets

### Run überschreitet Budget über Tool/Vision/Interview

#1478 hat diese Umgehungen für die normalen produktiven Pfade geschlossen:

- Tool-Calls prüfen Budget pro physischem Provider-Attempt
- Vision wird geprüft und im Ledger gebucht
- Direct- und IPC-Interviews tragen `run_id`/Budget-Attribution
- harte `BudgetExceededError` werden nicht in generische Interviewfehler verwandelt

### Bekannte Budget-Lücke im Parallelrunner

Der Default-Parallelrunner besitzt einen eigenen `ParallelIPCHandler`, der noch nicht dieselbe vollständige `SubprocessBudgetGuard`-Attribution besitzt. Siehe `STATUS.md`. Bei Budget-Audits diesen Pfad separat behandeln.

---

## 8. Installation & Secrets

### `.env` enthält noch `change-me`, `agora`, `password` etc.

`./install.sh` behandelt bekannte Placeholder inzwischen wie „nicht gesetzt“ und generiert sichere Werte, soweit Agora sie selbst erzeugen kann (#1483).

Neu installieren bzw. die betroffenen Werte bewusst ersetzen. Nicht einen Placeholder nur deshalb behalten, weil er syntaktisch ein String ist.

### `AGORA_SECRET_KEY` / `AGORA_FERNET_KEY` ungültig

Beide müssen gültige Fernet-Keys sein. `install.sh` erzeugt sie im Host-/Docker-Pfad entsprechend.

- `AGORA_SECRET_KEY`: LLM-Provider-Secret-Store
- `AGORA_FERNET_KEY`: persistierte Agora-API-Keys/zugehörige Secrets

Alte Schlüssel nicht löschen, bevor verschlüsselte Bestandsdaten migriert/gesichert sind.

### Backup-Skript findet `backend/reports/` nicht

Der echte Reportpfad ist:

```text
backend/uploads/reports/
```

Die alte `backend/reports/`-Angabe war Doku-Drift und wurde mit #1483 korrigiert.

---

## 9. Tests & CI

### Unit-/Contract-Tests ändern sich abhängig von lokaler `.env`

Das soll seit #1462 nicht mehr passieren. Die Testsuite setzt kontrollierte Defaults und importiert keine persönliche Repo-`.env` als implizite Wahrheit.

### Integrationstest ist grün, obwohl Redis/Neo4j gar nicht läuft

Für die echte Integrationsschicht `AGORA_TEST_REQUIRE_SERVICES=1` setzen. Im CI-Integration-Job ist das Pflicht (#1481).

Relevante Variablen:

- `AGORA_TEST_REDIS_URL`
- `AGORA_TEST_NEO4J_URI`
- `AGORA_TEST_NEO4J_USER`
- `AGORA_TEST_NEO4J_PASSWORD`

### GitHub Actions fehlen auf einem PR

Nicht automatisch „Tests grün“ daraus machen. In mehreren September-PRs wurden Gates wegen Actions/Billing remote auf dem ARM-Server ausgeführt und dokumentiert. Für Release-/Merge-Aussagen unterscheiden zwischen:

- lokal/remote ausgeführten Gates,
- PR-Checks,
- scheduled E2E,
- aktuellem Head.

---

## 10. Dependency-Risiken

### NLTK Advisory

[#661](https://github.com/arn0ld87/agora/issues/661) bleibt als Upstream-Risiko offen. Dass Scanner eine Version außerhalb `last_affected` nicht mehr melden, ist nicht automatisch ein dokumentierter Upstream-Fix.

Aktueller Hardstop: **28.09.2026** laut Dependency-Risk-Register.

### `ImportError: Blocked import of regex ...`

Für den nltk-Import-Hook wird `NLTK_DISABLE_IMPORT_SECURITY=1` in den vorgesehenen App-/Container-/Testpfaden gesetzt. Ein nackter Python-Prozess, der `app` nicht importiert, kann den Schalter selbst benötigen.

---

## Standard-Diagnose

```bash
# Dienste
docker compose ps

# Backend / DB / Redis
docker compose logs --tail 200 agora
docker compose logs --tail 200 neo4j
docker compose exec redis redis-cli ping

# Health
curl -fsS http://localhost:5001/health

# Authentifizierter Status
curl -fsS \
  -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
  http://localhost:5001/api/status
```

Bei einem neuen Fehlerbild zuerst prüfen, ob es wirklich einem bekannten Issue entspricht. Ähnliche Logzeilen sind kein Beweis für dieselbe Ursache. Computer sind da erfreulich kreativ.
