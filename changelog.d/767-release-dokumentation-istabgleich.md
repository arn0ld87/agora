### Fixed (Release-Dokumentation auf aktuellen Stand — 2026-10-02)

- **Veraltete RC-Blockerlisten korrigiert:** README in beiden Sprachen, STATUS, ROADMAP, CONTEXT, Handoff und Agenten-Prioritäten unterscheiden geschlossene Tickets von offenen Verträgen, Gates und Betriebsnachweisen. GitHub-Abgleich gegen `main@4cbf0eb8`; der rote Python-Audit und der noch offene pypdf-PR #1748 sind ausdrücklich belegt. (#767)
- **Replay-Grenze richtig dokumentiert:** #1274 ist geschlossen; `random_seed=null` ist die Maintainer-Entscheidung, keine offene RNG-Wiring-Zusage. LLM-Koreferenz bleibt außerhalb des #1470-Scopes, Role Leakage wird lesend markiert statt im Subprozess verworfen.
- **Agenten- und Prüfanleitungen synchronisiert:** Produktversion 0.9.6, produktiver PostgreSQL-Cutover gegenüber Legacy-Code-Defaults, aktuelles Backend-Coverage-Gate sowie Versions-/Typ-Schuld-/STATUS-Prüfungen. Generierte Testzähler und historische Referenzläufe bleiben unverändert.
