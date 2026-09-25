## Fixed

- Fällt `install_bert_memory_profile("auto")` wegen knappem Container-RAM auf fp16
  zurück, steht das jetzt als Warnung im Simulationslog (#1646). Vorher geschah das
  still: Der Twitter-Recommender brauchte auf der CPU rund 12 Minuten pro Forward,
  und der Lauf wirkte in der ersten Twitter-Runde hängend.
- `docs/runbooks/rls-rollen.md`: Auf Supabase aktiviert ein Event-Trigger RLS auf
  `public.alembic_version`. Die dort nötige Lese-Policy für `agora_app` ist jetzt
  dokumentiert. Ohne sie verweigert das Start-Gate den Start, obwohl die
  Revision in der Tabelle steht.
