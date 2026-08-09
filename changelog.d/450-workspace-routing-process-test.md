### Fixed (Robuster Multi-Prozess-Routing-Test — 2026-08-09)

- **Routing-Store-Test misst wieder die Lock-Invariante:** Die sieben Subprocess-Worker melden nach ihren Cold Imports explizit Readiness; erst danach beginnt die gemeinsame Lock-Deadline. Deterministisches Cleanup verhindert zugleich verwaiste Children. (#450)
