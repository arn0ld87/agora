### Fixed (LLM-Routing-Einstieg vollständig lokalisiert — 2026-09-06)

- Die LLM-Routing-Einstellungsansicht löst Seitentexte, Run-Auswahl, Feldlabels, Aktualisieren-Aktion, Leerzustand und Fallback-Ladefehler jetzt über `vue-i18n` auf. Deutsche und englische Texte liegen unter `settings.v4.llmRouting.*`; ein englischer Render-Regressionstest verhindert, dass die englische Oberfläche erneut deutsche Literale zeigt. (#1440)
