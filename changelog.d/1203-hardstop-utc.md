### Behoben

- `test_on_hardcutoff_day_list_must_already_be_empty` verglich das Datum der
  lokalen Zeitzone (`datetime.date.today()`) gegen das UTC-Datum, das
  `scripts/check-pip-audit-hardstop.sh` mit `date -u` bildet. In Zeitzonen mit
  UTC-Versatz fielen beide zwischen Mitternacht und dem Versatz auf
  verschiedene Tage — der Test setzte den Cutoff dann auf den Folgetag aus
  Sicht des Skripts, das nahm korrekt den „vor dem Hardcutoff"-Zweig und lieferte
  Exit 0 statt der erwarteten 2. In Europe/Berlin betraf das das Zeitfenster
  00:00–02:00. Der Test bildet sein „heute" jetzt ebenfalls in UTC. (#1203)
