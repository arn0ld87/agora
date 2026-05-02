# Voice-Register-Katalog (Layer 2 · Sub-Slice 10)

Vier Register, ein Pflichtfeld pro Persona. Anker für Prompt-Ingenieur und Auditor — nicht für LLM-Konsum.

## formal-de

- Sie-Form, keine Anglizismen, keine Werbesprache.
- Behörden-, Konzern-, akademischer Kontext.
- Klare Satzstrukturen, sparsame Adjektive.
- Beispiel-Persona: Verwaltungsbeamtin im BMI, Compliance-Officer, Universitätsdozent.
- Beispielsatz: „Aus regulatorischer Sicht ist die Maßnahme zu hinterfragen, da die Datenlage nicht eindeutig ist."

## neutral-de

- Alltagssprache, Du-Form möglich, gemischtes Vokabular.
- Default für die meisten Personas.
- Eingestreute Anglizismen okay, solange im DACH-Sprachgebrauch verankert.
- Beispiel-Persona: IT-Umschüler, Pflegekraft, Mittelstands-Mitarbeiter, Studentin.
- Beispielsatz: „Find ich gut, dass das jetzt mal angegangen wird — wurde langsam Zeit."

## technical-de

- Präzise, knapp, Fachvokabular zulässig.
- Keine Marketing-Phrasen, keine emotionale Aufladung.
- Sätze enden mit Substantiven, nicht mit Adjektiven.
- Beispiel-Persona: Senior-Developer, DevOps-Engineer, Data-Scientist, Forscherin.
- Beispielsatz: „PR sieht ok aus, aber `merge-base` fehlt im Pre-Commit-Hook — Diff gegen `origin/main` hängt damit von der Branch-History ab."

## skeptisch-de

- Kritisch-distanziert, hinterfragend, bei Bedarf sarkastisch.
- Buzzwords werden in Anführungszeichen gesetzt oder explizit dekonstruiert.
- Eigene Position klar, fremde Positionen werden zitiert und seziert.
- Beispiel-Persona: Aktivistin, Investigativ-Journalist, Verbraucherschützer, Netzpolitik-Blogger.
- Beispielsatz: „Wieder ein „revolutionärer" Wurf, der am Ende nur die alten Probleme in neue Foliensätze packt."

## Anwendung im Persona-Prompt

- Pflichtfeld `voice_register` in der JSON-Spec, exakt einer der vier Strings.
- Heuristik-Anker im Prompt: Beruf/Bildung/Kontext bestimmen das Register.
  - Beamtin/Konzern-Compliance → `formal-de`
  - Umschüler/Privatperson → `neutral-de`
  - Senior-Developer/Wissenschaftlerin → `technical-de`
  - Aktivistin/Watchdog → `skeptisch-de`
- Bei fehlendem oder ungültigem LLM-Output: Auto-Fallback `neutral-de`, Logger-Warning, Validation-Eintrag in `missing_fields`.

## Was das Register NICHT ist

- Keine Sprachfärbung („Berlinerisch", „Wienerisch") — das ist eine separate Achse.
- Kein Tonfall-Indikator („wütend", „freundlich") — das gehört in `persona`-Fließtext.
- Keine Gattung („Boomer", „Gen-Z") — das gehört in Demografie-Felder.
