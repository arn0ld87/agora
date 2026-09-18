# Runbook: LLM-Profile von SQLite auf PostgreSQL umstellen

Zugehöriger Plan: [`../plans/supabase.md`](../plans/supabase.md) §10 („Phase 4: Erste echte Migration – LLM Profiles").
Werkzeuge: [`backend/scripts/migrate_llm_profiles_to_postgres.py`](../../backend/scripts/migrate_llm_profiles_to_postgres.py), [`backend/scripts/migrate_profile_secrets.py`](../../backend/scripts/migrate_profile_secrets.py).

## Warum dieses Runbook existiert

Das Umlegen von `AGORA_LLM_PROFILE_BACKEND` ist eine Zeile in der Umgebung und dauert eine Sekunde. Was davor passieren muss, dauert länger, und genau daran hängt, ob die Anwendung danach dieselben Profile sieht wie vorher. Ein Schalter, der vor der Migration umgelegt wird, zeigt auf eine leere Tabelle — die Anwendung startet, meldet keinen Fehler und hat keine einzige Route mehr.

## Was sich dabei nicht ändert

**IDs bleiben identisch.** Der bisherige Store erzeugt sie als `uuid4().hex`, 32 Zeichen ohne Bindestriche. In PostgreSQL ist die Spalte ein `UUID` — dieselbe Zahl, andere Schreibweise. Der Adapter gibt sie deshalb immer als `.hex` zurück. Täte er das nicht, zeigte jede gespeicherte Referenz der Form `llm_model: "profile:<id>"` in einer Simulationskonfiguration ins Leere.

**Zeitstempel bleiben identisch.** `created_at` und `updated_at` werden übernommen, nicht neu gesetzt. Eine Migration, die alles auf „heute" stellt, verliert genau die Information, mit der sich später nachvollziehen lässt, was wann entstand.

**Die SQLite bleibt liegen.** Sie wird weder verändert noch gelöscht (§10 Schritt 9). Die Migrationsskripte öffnen sie mit `mode=ro`.

## Voraussetzungen

```bash
# In der Umgebung des Backends:
#   DATABASE_URL=postgresql+psycopg://…   (Schema-Präfix ist Pflicht)
#   AGORA_SECRET_KEY=…                    (Fernet-Key, derselbe wie bisher)

cd backend
uv run alembic -c migrations/alembic.ini upgrade head
```

Ohne `alembic upgrade head` existiert `agora.llm_profiles` nicht, und die Migration bricht ab, statt eine Tabelle zu raten.

## Der Ablauf

Die Reihenfolge ist die aus §10 und nicht verhandelbar — jeder Schritt prüft den vorigen.

```bash
cd backend

# 1. Baseline vorher. Siehe runbooks/migration-baseline.md.
uv run python scripts/migration_baseline.py \
  --data-dir uploads --instance-dir instance --output ../baseline-vorher.json

# 2. Vorschau: was würde übertragen?
uv run python scripts/migrate_llm_profiles_to_postgres.py --dry-run

# 3. Übertragen (Metadaten nach PostgreSQL, Schlüssel in den Fernet-Store)
uv run python scripts/migrate_llm_profiles_to_postgres.py

# 4. Gegenprüfung — muss mit Exit 0 enden
uv run python scripts/migrate_llm_profiles_to_postgres.py --verify
```

**Erst wenn Schritt 4 grün ist**, wird umgeschaltet:

```bash
# 5. AGORA_LLM_PROFILE_BACKEND=postgres setzen, Backend neu starten

# 6. Funktionsprüfung in der Anwendung: Profilliste öffnen, ein Profil
#    auswählen, einen Lauf starten. Das prüft, was --verify nicht prüfen kann.

# 7. Baseline nachher und Vergleich
uv run python scripts/migration_baseline.py \
  --data-dir uploads --instance-dir instance --output ../baseline-nachher.json
uv run python scripts/migration_baseline.py \
  --compare ../baseline-vorher.json ../baseline-nachher.json
```

## Was `--verify` prüft, und was nicht

Es vergleicht beide Seiten feldweise: Anzahl, IDs, `name`, `provider`, `base_url`, `model_name`, `is_default`, beide Zeitstempel — und die Schlüssel **über den entschlüsselten Klartext**, nicht über bloße Existenz. Ein Eintrag, der unter der falschen Profil-ID liegt oder aus einem früheren Lauf mit anderem Wert stammt, fällt damit auf. Einträge in PostgreSQL, die es in der SQLite nicht gibt, werden ebenfalls benannt.

Es prüft **nicht**, ob die Anwendung danach funktioniert. Dafür ist Schritt 6 da. Ein grünes `--verify` heißt: die Daten sind vollständig angekommen — nicht: das Routing benutzt sie richtig.

## Der Rückweg

```bash
# AGORA_LLM_PROFILE_BACKEND=sqlite setzen, Backend neu starten
```

Die SQLite ist unverändert, also ist der Rückweg sofort wirksam. **Was dabei verloren geht:** jedes Profil, das *nach* der Umstellung in PostgreSQL angelegt oder geändert wurde, steht nicht in der SQLite. Der Rückweg ist deshalb zeitlich begrenzt brauchbar — er gilt für den Tag der Umstellung, nicht für den Monat danach. Wer später zurück muss, migriert in die Gegenrichtung und hat dafür kein Werkzeug.

## Der Sonderfall Schlüssel

Die Profil-Schlüssel liegen nach der Umstellung im Fernet-Store `llm_profile_secrets.json`, verschlüsselt mit `AGORA_SECRET_KEY`. Dieser Wert muss **derselbe bleiben**. Eine Rotation ohne Neuverschlüsselung macht jedes Profil unbrauchbar.

Das fällt allerdings auf, statt still zu wirken: der Store wirft dann `ProfileSecretDecryptionError`, statt ein leeres Feld zurückzugeben. Genau dafür existiert die Unterscheidung — ein Profil, das nach einer Rotation stillschweigend ohne Authentifizierung weiterliefe, wäre der schlimmere Fall.

Ob überhaupt Schlüssel hinterlegt sind, lässt sich ohne Master-Key prüfen:

```bash
uv run python scripts/migrate_profile_secrets.py --verify
```
