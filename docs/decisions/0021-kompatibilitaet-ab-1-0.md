# ADR-0021: Kompatibilitäts- und Deprecation-Policy ab 1.0

- Status: Accepted (Entscheidung im Grilling vom 26.09.2026, [#1657](https://github.com/arn0ld87/agora/issues/1657); die Auslegung „Antwortfeld“ in §4 und der Stichtag in §5 wurden vom Maintainer am 02.10.2026 bestätigt)
- Datum: 02.10.2026
- Bezug: [#1651](https://github.com/arn0ld87/agora/issues/1651) (Wayfinder-Karte), [#1657](https://github.com/arn0ld87/agora/issues/1657), [#1663](https://github.com/arn0ld87/agora/issues/1663) (`schema_version`), [#1654](https://github.com/arn0ld87/agora/issues/1654) (Cutover), [#1664](https://github.com/arn0ld87/agora/issues/1664), [ADR-0010](0010-vue-v4-route-consolidation.md)

## Kontext

Das Freigabekriterium für 1.0 verlangt „versionierte API-, Report-, Run- und Persistenzverträge“ und „dokumentierte Kompatibilitäts- und Deprecation-Regeln“ (`ROADMAP.md`). Bis `0.9.x` galt keine Zusage: Endpunkte, Felder und Ablageformate änderten sich mit jedem Slice, aufgefangen von Changelog-Fragmenten und `docs/runbooks/upgrade.md`.

Vor dieser Entscheidung war bereits versioniert:

- die Report-Verträge über `schema_version` als `Literal` (`report_contract.py`, `report_v3.py`) samt Migrationspfad (`evidence_migrations.py`),
- Run-Manifest und Run-Budget über `schema_version: Literal[1]`,
- die PostgreSQL-Metadaten über die Alembic-Revision mit Start-Gate (`schema_gate.py::verify_schema_at_head`).

Unversioniert waren die HTTP-API als Ganzes sowie das Dokument-Manifest und der Personasatz. Letztere hat #1663 nachgezogen.

## Entscheidung

### 1. API-Version = App-Version

Die HTTP-API hat **keinen URL-Präfix** wie `/api/v1/`. Ihre Version ist die App-Version nach SemVer. Verbindlich ist die Datei `VERSION`, `backend/pyproject.toml` und `frontend/package.json` folgen ihr (`check_version_drift.py`):

| Stufe | Bedeutung für Verträge |
|---|---|
| MAJOR (`2.0.0`) | einziger Ort für Breaking Changes und für die Entfernung angekündigter Deprecations |
| MINOR (`1.x.0`) | additive Änderungen, neue Endpunkte, neue Deprecations |
| PATCH (`1.x.y`) | Fehlerbehebungen ohne Vertragsänderung |

Der generierte Schema-Satz unter `schemas/` zum Tag `v1.0.0` ist der **eingefrorene 1.0-Vertrag**. Spätere `1.x`-Stände dürfen ihn nur additiv erweitern.

### 2. Kein Breaking in 1.x

Die Zusage gilt für zwei Dinge:

- **Dokumentierte Endpunkte:** alles, was in [`docs/api.md`](../api.md) steht, samt Envelope-Form aus [`docs/api-contracts.md`](../api-contracts.md).
- **Persistierte Formate:** PostgreSQL-Schema `agora` sowie die Dateiartefakte unter `uploads/` und `AGORA_DATA_DIR`, soweit sie einen Vertrag in `backend/app/contracts/` haben.

Als Breaking gilt jede Änderung, nach der ein Client oder Bestand, der zu `1.0.0` passte, fehlschlägt oder etwas anderes bedeutet:

- einen Endpunkt, ein Feld oder einen Enum-Wert entfernen oder umbenennen,
- einen Typ ändern oder ein optionales Eingabefeld zur Pflicht machen,
- erlaubte Eingaben einschränken,
- die Bedeutung eines unveränderten Feldes ändern,
- Bestand nicht mehr lesen können.

Nicht Breaking sind:

- neue Endpunkte,
- neue optionale Eingabefelder,
- neue Antwortfelder,
- neue Enum-Werte in Antworten, sofern der Vertrag sie als erweiterbar dokumentiert.

Externe Clients müssen unbekannte Antwortfelder ignorieren. Der eigene Frontend-Spiegel (Zod, teils `.strict()`) wird nach der Contracts-first-Regel im selben Change nachgezogen.

**Nicht** unter die Zusage fallen:

- undokumentierte Endpunkte,
- interne Python-Module und Skripte,
- Prompt-Texte,
- Inhalt und Qualität von Simulations- und Berichtsergebnissen. Eine Reproduzierbarkeitszusage gibt es weiterhin nicht, siehe #763/#1274.

### 3. Persistenz

- **PostgreSQL:** Die Alembic-Revision versioniert das Schema. Migrationen in `1.x` laufen vorwärts und halten Bestand lesbar. Der Rückweg je Schritt steht in `docs/runbooks/upgrade.md`.
- **Dateiartefakte:** Versioniert werden sie über `schema_version`. Heute tragen das Feld die Report- und Evidence-Verträge, das Run-Manifest und das Run-Budget, das Dokument-Manifest und der Personasatz (#1663). Andere persistierte Dateien wie `simulation_config.json` oder `state.json` haben noch keins, sie gelten als Version 1. Ändert sich das Format eines Dateiartefakts in `1.x`, bekommt es im selben Change `schema_version` und einen Lesepfad für die Vorgängerversion. Fehlt das Feld im Bestand, gilt er als Version 1.
- **Altbestand** wird gelesen und bei Bedarf migriert. Vertragswidriger Altbestand wird **sichtbar degradiert**, nach dem Muster `evidence_omitted`, und nie still verworfen oder als Erfolg ausgegeben.
- **Legacy-Stores** (JSON/SQLite-Metadaten vor dem PostgreSQL-Cutover) sind nach [#1654](https://github.com/arn0ld87/agora/issues/1654) nur noch Migrationsquelle für Upgrades aus `0.9.x`. Entfernt werden sie frühestens **zwei stabile Releases nach dem Cutover**.

### 4. Deprecation

Eine Deprecation durchläuft drei Schritte:

1. **Ankündigung im Changelog** (Fragment unter `changelog.d/`, Kategorie `Changed`). Sie nennt den Nachfolger und die frühestmögliche Entfernungsversion.
2. **Warnung im Betrieb:**
   - **Log:** Jede Nutzung erzeugt eine Warnung, bei Konfigurationsschaltern mit `DeprecationWarning` (Muster `LLM_DISABLE_JSON_MODE` in `backend/app/llm/client.py`).
   - **Antwort:** Die Antwort eines deprecateten Endpunkts trägt die Header `Deprecation` (RFC 9745, Datum der Ankündigung) und `Link: <…>; rel="successor-version"`. Ist die Entfernung terminiert, kommt `X-Agora-Removal-Version` dazu. Das Muster steht in `backend/app/api/deprecation.py::add_legacy_deprecation_headers`.
3. **Entfernung frühestens in der nächsten MAJOR-Version (`2.0.0`).**

**Auslegung zu #1657:** Die Entscheidung spricht von „Log und Antwortfeld“. Umgesetzt ist das als **Antwort-Header**, nicht als Feld im JSON-Body. Ein zusätzliches Body-Feld wäre für die `.strict()`-Spiegel selbst eine Vertragsänderung, und Streams sowie Datei-Exporte haben keinen Envelope. Ein Body-Feld kommt nur dort in Frage, wo der Vertrag es bereits vorsieht.

### 5. Geltungsbeginn und offene Einzelfälle

Die Zusagen gelten **ab dem Tag `v1.0.0`**. Bis dahin, also für `0.10.x` und die `1.0.0-rc.*`, bleiben Breaking Changes erlaubt, wenn Changelog-Fragment und `upgrade.md` sie ausweisen.

Was zum Tag `v1.0.0` noch im Code steht, fällt unter die 1.x-Zusage und bleibt bis mindestens `2.0.0`. Stichtag für jede Entfernung vor 1.0 ist der Schnitt von `1.0.0-rc.1`. Danach wird nichts Dokumentiertes mehr entfernt.

| Einzelfall | Stand am 02.10.2026 | Stichtag / Folge |
|---|---|---|
| `/settings-classic` → `/settings/general` (Redirect) | laut [ADR-0010](0010-vue-v4-route-consolidation.md) auf `1.0.0` **Deferred**, testabgedeckter Deep-Link | Entfernen bis `1.0.0-rc.1`, sonst bleibt der Redirect bis `2.0.0` |
| Legacy-Routen `/api/settings/llm-profiles*` und `/api/llm/providers*` (inkl. API-Keys) | `Deprecation` seit 18.07.2026, `X-Agora-Removal-Version: 1.0.0`, Nachfolger `/api/llm/provider-connections`. Das eigene Frontend ruft beide Gruppen noch auf: `frontend/src/api/llmProfiles.ts`, `llmRouting.ts` (Provider- und Modellliste) und `llmProviderKeys.ts` (API-Keys). Vor der Entfernung müssen alle drei migriert sein | Entfernen bis `1.0.0-rc.1`, sonst verfällt die angekündigte Version und die Entfernung rückt auf `2.0.0` |
| Header `X-Agora-Token` | in `docs/auth.md` als Backward-Compatibility geführt, keine Entfernung angekündigt | ohne Ankündigung vor `1.0.0-rc.1` Teil des 1.x-Vertrags |
| Override-Key `llm_model` in Branch-Requests (`branch_request_contract.py`, #886) | als deprecated markiert, keine Entfernung angekündigt | wie `X-Agora-Token` |
| Env-Alias `LLM_DISABLE_JSON_MODE` | `DeprecationWarning`, laut `docs/configuration.md` veraltet | Env-Variablen sind kein HTTP- oder Ablagevertrag. Änderungen laufen über `upgrade.md`, die Entfernung folgt trotzdem Schritt 1–3 |
| Legacy-Metadaten-Stores | Migrationsquelle (#1654) | frühestens zwei stabile Releases nach dem Cutover |

## Konsequenz

- `docs/api.md`, Abschnitt „Konventionen“, verweist auf dieses ADR. Wer einen dokumentierten Endpunkt oder ein persistiertes Format ändert, prüft die Änderung gegen Entscheidung §2.
- Es gibt **keinen automatischen Breaking-Change-Check** gegen den Schema-Satz von `v1.0.0`. `dump_schemas --check` erkennt nur Drift zwischen Code und `schemas/`, nicht ob eine Änderung additiv ist. Bis ein Werkzeug das leistet, prüft das Review.
- Die Log-Warnung aus §4 fehlt heute noch: Die Legacy-LLM-Routen setzen nur die Header. Wer dort eine Deprecation über `1.0.0` hinaus bestehen lässt, ergänzt die Warnung.
- Die Einzelfälle in §5 werden im Freeze vor `1.0.0-rc.1` entschieden. Danach ändert sich die Tabelle nicht mehr. Eine spätere Entfernung braucht ein neues ADR für `2.0.0`.
- Der Abschnitt `0.10 → 1.0` in `docs/runbooks/upgrade.md` übernimmt die Entscheidungen aus §5, sobald sie gefallen sind.
