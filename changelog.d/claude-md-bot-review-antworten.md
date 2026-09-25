### Changed (Review-Regel für Bot-Kommentare — 2026-09-25)

- **Review-Kommentare von Bots werden einzeln beantwortet:** `CLAUDE.md` schrieb „keine Bot-Kommentar-Einzelantworten“ vor und widersprach damit `docs/runbooks/pr-workflow.md` §9 (jeder Thread wird aufgelöst oder begründet zurückgewiesen). Jetzt gilt überall: Jeder Review-Kommentar, auch von Codex oder CodeRabbit, bekommt eine eigene Antwort im Thread, behoben mit Commit-Hash oder begründet zurückgewiesen, danach wird der Thread aufgelöst. `pr-workflow.md` §7 führt das als Merge-Voraussetzung.
