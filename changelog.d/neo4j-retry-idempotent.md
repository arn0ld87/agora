### Behoben

- Der Graph-Build bricht nicht mehr mit `ConstraintValidationFailed` ab, wenn Neo4j die Bestätigung einer bereits committeten Transaktion nicht mehr zustellen kann. Episode-Knoten und RELATION-Kanten werden per `MERGE` statt `CREATE` geschrieben und überstehen damit einen Retry; zuvor riss die zweite Ausführung entweder den ganzen Build ab (Episode, Unique-Constraint) oder legte still eine Dublette an (RELATION, ohne Constraint).
