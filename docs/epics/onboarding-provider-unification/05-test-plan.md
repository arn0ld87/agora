# Test Plan

## Gates pro Slice

```bash
(cd backend && uv run python -m app.contracts.dump_schemas)
git diff --exit-code schemas/
(cd backend && uv run pytest tests/contracts/ -v)
(cd backend && uv run pytest -x -q)
(cd backend && uv run ruff check .)
(cd backend && uv run mypy app)
(cd frontend && npm run check)
(cd frontend && npm test -- --run)
```

## Contract- und Adaptertests

- `extra="forbid"` auf neuen Verträgen.
- Pydantic-/Zod-Roundtrips.
- Legacy-Profile und Stage-Routen werden verlustfrei gelesen.
- Secrets erscheinen nur als `secret_ref`/maskierter Status.
- Capability `unknown` wird nicht als unterstützt behandelt.

## Provider und Model-Picker

- Live-, Cache-, Fallback- und Custom-Quelle sichtbar.
- Auth-, Connection-, Rate-Limit-, Timeout- und Capability-Fehler typisiert.
- Tastatur, Screenreader, Suche, Offline und Refresh.
- gleicher Picker an mindestens drei Einsatzstellen.
- `LlmProvidersView` und Provider-/Profile-/Routing-Stores direkt testen.

## Onboarding

- erster Start, Speichern nach jedem Schritt, Abbruch und Resume.
- lokaler Modus ohne Cloud-Key.
- Avatar: MIME, Größe, Vorschau, Löschen, SVG-Ablehnung.
- erneutes Öffnen über Settings.
- Router-Guard, serverseitiger Completion-Status und Back/Forward-Navigation.

## Embeddings

- OpenAI, Gemini, Ollama local; reale Dimension wird per Probe bestätigt.
- Modellwechsel ohne Daten, mit Daten, bei Abbruch und bei Teilfehler.
- neue Indizes parallel, keine Löschung vor Validierung.
- Rollback stellt alte Konfiguration und Lesbarkeit wieder her.
- Ollama-Download-Stream gemockt: Fortschritt, Timeout, Abbruch, Injection.

## Persona-Invariante

Für 1, 5, 10, 30, 50 und 100 gilt in API, Persistenz, Profilgenerator,
OASIS-Eingabe, Retry und Report:

```text
requested == generated == persisted == simulated
```

Zusätzlich: deterministische Quoten, keine doppelten IDs, Retrys hängen keine
Profile an, Skeptikerquote erhöht die Gesamtzahl nicht.

## Bekannte Baseline

Vor Frontend-Slice 2 oder 5 muss der bestehende Vitest-Teardown-Fehler aus
`HistoryView.spec.ts`/`CommandPalette.vue` separat grün sein. Er darf nicht als
Nebeneffekt eines Feature-Slices kaschiert werden.

Zusätzlich fehlen heute Responsive-/Focus-Management-Tests für mobile Sidebar,
Provider-Grid und den produktiven v4-Model-Picker.
