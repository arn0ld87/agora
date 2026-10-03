---
type: changed
---

**Development:** Die Worker-Subagenten (`agora-refactor-worker`, `agora-test-worker` jeweils mit und ohne `-m3`) führen Backend-Tests und Pflichtprüfungen remote auf **gns3** aus statt auf dem armserver; der Remote-Helper ist immer über `bash` mit dem eigenen `pwd`-Pfad aufzurufen. Frontend-Worker und Test-Worker-Frontend-Blöcke laufen nur die berührten Vitest-Specs (`bunx vitest run <Pfade>`) statt der vollen Suite (`bun run test`). Gate-Verantwortung vereinheitlicht: genau ein Scope-Gate pro Worker-Commit, außer das Briefing überlässt es dem Lead. Veraltete Modell-IDs aktualisiert (`claude-sonnet-4-6` → `claude-sonnet-5-5`, `claude-opus-4-7` → `claude-opus-5-5`); die seit PR #1703 obsolete `nala`-Regel entfernt. NEIN-Listen schützen jetzt den Produktiv-Stack auf beiden Hosts (gns3 und armserver).
