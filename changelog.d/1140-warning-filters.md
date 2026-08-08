### Changed

- Testläufe filtern vier belegte Upstream-Warnquellen (pytest-asyncio, neo4j, OpenTelemetry-Flask) gezielt nach Nachricht und Modul; projekteigene DeprecationWarnings bleiben sichtbar und gate-fähig ([#1090](https://github.com/arn0ld87/agora/issues/1090), [#1140](https://github.com/arn0ld87/agora/pull/1140)).
