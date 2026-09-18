Projektmetadaten haben einen zweiten Adapter: `PostgresProjectRepository` auf
der neuen Tabelle `agora.projects`. Der Spaltenschnitt ist Kern plus Nutzlast —
die Felder, nach denen abgefragt und sortiert wird, bekommen eine eigene Spalte,
alles Übrige liegt in `payload jsonb`. Die Aufteilung wird aus
`Project.to_dict()` abgeleitet statt gepflegt, damit ein künftiges Vertragsfeld
nicht still verlorengeht.

`backend/scripts/migrate_projects_to_postgres.py` überträgt den Dateibestand,
lässt das Dateisystem unberührt und vergleicht mit `--verify` jedes Feld jedes
Projekts. Ablauf und Rückweg stehen in
`docs/runbooks/projekt-postgres-umstellung.md`.

Umgeschaltet ist nichts: `AGORA_PROJECT_BACKEND` bleibt im Default auf `file`.
Neu ist, dass `Config.validate()` den Wert `postgres` ohne gesetzte
`DATABASE_URL` schon beim Start ablehnt statt erst beim ersten Projektzugriff.
