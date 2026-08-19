# Agora — Neuhülle & Funktionsöffnung

**Branch:** `feat/frontend-dossier` · **Worktree:** `/mnt/work/Projekte/agora-neu`
**Stand:** 2026-08-18 · **Grundlage:** Grilling-Session 18.08.2026 (Q1–Q35)
**Fundament:** Commit `018b1dea` (Slice D0) bleibt und gilt als erledigt.

---

## 0. Warum überhaupt

Agora wirkt altbacken, weil es light-only und flach ist, und der Komfort fehlt,
weil fertige Backends keine Oberfläche haben:

| Fertig im Backend | Aufrufer im Frontend |
|---|---|
| `GET /api/report/list` | **keiner** |
| `GET /api/graph/project/list`, `/data/<id>`, `/snapshot/<id>/<round>`, `/<id>/diff`, `/<id>/export` | **keiner** (keine Route im Router) |
| `GET/POST/DELETE /api/simulation/persona-library` | nur `Step2EnvSetup.vue:343` |
| `POST /api/runs/<id>/cancel` | nur `Step3Simulation.vue:339` |
| `POST /api/simulation/<id>/pause` + `/resume` | **keiner** |

Dazu: `Topbar.vue:57` zeigt ein hartkodiertes `aria-hidden`-Div mit dem Text `AD`,
obwohl `store/userProfile.ts` und `contracts/userProfileContract.ts` ein echtes
Profil inkl. Avatar führen.

---

## 1. Festlegungen aus dem Grilling

### Gestaltung
1. Richtung **B (Dossier)** als Gerüst — Ablage links, Objekt-Dossier rechts,
   Stapel als Rückweg. Aus Richtung C übernommen: **eine Weiter-Aktion pro
   Ablage-Zeile** („9 Befunde prüfen", „Personas freigeben", „Zusehen").
2. Palette warm dunkel, Akzent **Kupfer `#d08a52`** (nicht Marken-Orange
   `#FF6A00` — es würde mit der Statusskala kollidieren). Werte stehen bereits
   in `tokens-v3.css` (D0).
3. Typo: **Archivo** (UI) · **Newsreader** (Berichtstext, Vita, Zitate — nicht
   Überschriften) · **Geist Mono** (IDs, Zahlen).
4. **Fonts self-hosted** über `@fontsource-variable/archivo` und
   `@fontsource-variable/newsreader` (inkl. Italic-Achse für Zitate).
   Der Google-Fonts-CDN-Link aus D0 (`frontend/index.html`) wird ersetzt —
   Agora läuft über Tailscale, externe Font-Requests sind dort falsch.
5. **Eigener `[data-theme="dark"]`-Block.** D0 hat den `light`-Selektor
   umgefärbt; das wird aufgelöst. Light-Palette wird **nicht** gebaut, das
   Token-Gerüst bleibt leer stehen. Die Dark-Readiness-Klausel in
   `assets/styles/__tests__/designTokens.spec.ts` (Z. 128/143/145/153) greift
   damit erstmals.
6. **Textstufen getrennt.** D0 setzte `--text-secondary` und `--text-tertiary`
   auf denselben Wert `#7c736a` — die Stufe existierte nicht, und Fließtext lag
   mit 4,04:1 unter der eigenen 4,6:1-Regel. Die Vorlage kennt beide Töne:
   `--text-secondary: #a89f94` (7,3:1) für lesbaren Text, `--text-tertiary:
   #7c736a` (4,0:1) für Labels und Metazeilen, kein Fließtext. Farbtreue bleibt
   gewahrt, beide Werte stammen aus dem Entwurf.

### Objektmodell
7. Ablage zeigt **Läufe** als Zeilen; ein Filter „Alle Jobs" legt die Rohebene
   der fünf `run_type`-Werte frei (`graph_build`, `ontology_generate`,
   `report_generate`, `simulation_prepare`, `simulation_run`).
   Vokabular verbindlich in `CONTEXT.md` → Glossar: **Lauf** = das ganze
   Vorhaben (UI-Zeile), **Job** = ein Einzelschritt daraus. „Vorgang" und
   „Run" werden in der Oberfläche nicht mehr verwendet.
8. Berichte, Personasätze und Graphen sind gleichrangige Objekte in der Ablage.
9. Einstellungen werden Overlay über der aktuellen Route.
10. Der Wizard verliert „Schritt 3 von 5"; die Step-Views bleiben als Routen
    und werden Stationen, erreichbar über die Weiter-Aktion.

### Abbrechen
11. Cancel für alle Job-Typen, in denen es technisch trägt.
    **Vorhanden:** `simulation_run`, `report_generate` (inkl. Teilreport).
    **Neu:** `simulation_prepare`, `graph_build`.
    **Ausgenommen:** `ontology_generate` — läuft synchron im Request-Handler
    (`api/graph_build.py:266`), ein einzelner LLM-Call, kein Job. Statt
    Abbrechen bekommt er sichtbaren Fortschritt.
12. Abgebrochener Graph-Build wird **behalten** und als unvollständig
    gekennzeichnet, nicht zurückgerollt.
13. **Pause** nur für `simulation_run` — existiert bereits im Backend
    (`api/simulation_run.py:802/838` über `control_state.json`), es fehlt
    ausschließlich die Oberfläche.
14. Im UI: Zeilenaktion in der Ablage, Dossier-Kopf, globaler Topbar-Indikator.
    **Kein Bestätigungsdialog** — sofort abbrechen mit 5-Sekunden-Rückgängig.
    Der Abbruch ist kooperativ, Teilergebnisse bleiben, es gibt nichts zu
    schützen.
15. Cancel-Flag bleibt In-Process (`services/sim/cancel_flag.py`). Belegt:
    `backend/gunicorn.conf.py:28` schreibt `workers = 1` als HARDSTOP fest.

### Funktion
16. Graph als Objekt mit **Runden-Scrubber** und **Diff-Liste** („12 Entitäten
    neu, 3 Relationen entfernt") — die Liste ist wichtiger als die Grafik.
17. Bericht-Chat als Dossier-Reiter, jederzeit, auf `POST /api/report/chat`.
18. Schnellstart „Neue Simulation aus Personasatz": Personas wählen + Szenario
    schreiben, ein minimaler Graph wird intern erzeugt. `graph_id` bleibt im
    Backend Pflicht — solche Läufe landen in derselben Ablage und
    Report-Pipeline wie alle anderen.
19. Aus einem Bericht eine neue Simulation ableiten — Block 4.
20. **Gestrichen:** zwei Berichte vergleichen.

### Mobile (390px)
21. Monitoring und Lesen: Ablage als Startbildschirm, Dossier als Vollbild,
    Stapel als Rückweg, Abbrechen überall erreichbar. Graph und
    Persona-Prüfung nur ansehbar.
22. **Kein Hamburger, keine Tab-Leiste** — die Ablage trägt die Navigation.

### Entsorgt
23. Notification-Glocke (`Topbar.vue`, kein Backend), `DensityToggle`,
    `Home.vue` (ADR-0010), `RunsView.vue`, `RunDetailView.vue`,
    das `AD`-Platzhalter-Div → echtes Nutzermenü aus `userProfile`
    mit Theme- und Sprachumschaltung.

### Vorgehen
24. **Feature-Flag** an der Shell-Wurzel; `main` bleibt durchgehend benutzbar.
25. Große Blöcke, große PRs (bewusste Abweichung von `AGENTS.md:15`).
    Preis dafür: jeder Block muss zwischendurch lauffähig sein.

---

## 2. Feature-Flag

```
VITE_AGORA_SHELL = "dossier" | "classic"      # Build-Default
localStorage["agora.shell"]                    # Laufzeit-Override im Browser
```

Aufgelöst in einem Composable `useShellVariant()`, ausgewertet **an genau einer
Stelle**: der Wurzel-Route. `classic` mountet `AppShell.vue` wie heute,
`dossier` mountet `ShellRoot.vue`. Kein Flag tief in Komponenten — sonst wird
er nicht mehr entfernbar.

Entfernt wird der Flag am Ende von Block 3, zusammen mit `AppShell.vue`,
`Sidebar.vue`, `Topbar.vue` und den Legacy-Views.

---

## 3. Blöcke

### B1 — Fundament (Frontend, mechanisch)

Baut auf D0 auf, korrigiert dessen drei Abweichungen.

**Fonts**
- `package.json`: `@fontsource-variable/archivo`, `@fontsource-variable/newsreader`
- `frontend/src/main.ts`: Font-Importe
- `frontend/index.html`: Google-Fonts-`preconnect` + Stylesheet-Link **entfernen**;
  das `data-theme='light'`-Setz-Skript (~Z. 19–22) und seinen Kommentar
  „Design v3 ist light-only" korrigieren
- `frontend/src/assets/styles/fonts.css`: Geist Sans raus, Geist Mono bleibt

**Tokens**
- `tokens-v3.css`: Werte aus dem `light`-Selektor in einen echten
  `[data-theme="dark"]`-Block überführen; Light-Gerüst leer stehen lassen;
  `--text-secondary` auf ≥4,6:1 heben
- `states.css`, `global.css`: nachziehen

**Entkernung — 31 Dateien / 234 echte Farbwerte, aber nicht alle hier**

(Eine frühere Zählung nannte 88/563; sie zählte Issue-Referenzen wie `#764` in
Kommentaren als Hex-Farben mit. Die Zahlen unten sind kommentarbereinigt.)

| Gruppe | Dateien | Werte | in B1? |
|---|---:|---:|---|
| LEGACY (`RunsDashboard`, `RunDetailView`, `HistoryDatabase`, `Home`) | 4 | 69 | **nein** — wird gelöscht |
| SHELL + REPORT | 8 | 41 | **nein** — B3 schreibt sie neu |
| GRAPH (`GraphDiffPanel` 39, `GraphCanvas` 10, …) | 4 | 51 | **nein** — B3 |
| FORMS | 14 | 63 | ja |
| SETTINGS | 5 | 49 | ja |
| SIMFEED | 7 | 52 | ja |
| COMPARE (`BranchComparePanel` allein 59) | 1 | 59 | ja |
| STEPS | 21 | 84 | ja |
| SONSTIGE | 24 | 95 | ja |

→ B1 entkernt **72 Dateien / 402 Werte**. 161 Werte entfallen durch Löschen
oder Neubau. Reine Token-Substitution, keine Logik.

**Fertig, wenn:** `bash scripts/pre-push-gate.sh frontend` grün, Agora in
`classic` unverändert bedienbar, nur dunkel.

---

### B2 — Abbrechen & Pause (Backend, parallel zu B1)

Referenzmuster: `report_agent/workflow.py:1330/1423` (Stage-Boundary-Checks)
und `services/report_generation.py:70–99` (`finish_cancelled_run`).

**`simulation_prepare`** — mittleres Risiko, Ziel ist eine Datei, kein Graph
- Checkpoints zwischen den drei Phasen: `services/prepare_service.py`
  vor Z. 791 / 829 / 852
- Checkpoint in der `as_completed`-Schleife
  `services/oasis_profile_generator.py:2312` (bremst neue Ergebnisse; laufende
  Persona-Generierungen laufen aus — akzeptiert)
- FSM braucht einen `stopped`-Zweig; heute nur `READY`/`FAILED`
  (`prepare_service.py:872–878`)

**`graph_build`** — höchstes Risiko
- Checkpoint vor `add_text_batches` (`services/graph_build.py:479`)
- Checkpoint in `as_completed` (`services/graph_builder.py:436`) plus
  `shutdown(wait=False, cancel_futures=True)`
- **Bewusst akzeptiert:** `storage/neo4j_write.py::_persist_episode` committet
  pro Entität (Z. 360–406) und pro Relation (ab Z. 438) einzeln. Laufende
  Worker hinterlassen halb geschriebene Episode-Knoten. Der Graph wird deshalb
  als `unvollständig` markiert statt gelöscht.
- `build_task()` braucht einen Cancel-Zweig, der `mark_graph_completed`
  umgeht — sonst bleibt `project.status = GRAPH_BUILDING` hängen

**Nicht angefasst:** `ontology_generate`.

**Tests neu:** `test_prepare_cancel.py`, `test_graph_build_cancel.py`
(heute existiert Cancel-Abdeckung nur für `simulation_run` und
`report_generate`).

**Fertig, wenn:** Abbruch in beiden Typen führt zu `status="stopped"`,
`termination_reason="user_cancel"`, Teilzustand bleibt lesbar, 449
Backend-Tests grün.

---

### B3 — Objektmodell (der Brocken)

Vorlagen liegen fertig zerlegt in `docs/design/screens/`:
`01-ablage.html`, `02-kommandopalette.html`, `03-laeufe.html`,
`04-simulation.html`, `05-akteure.html`, `06-quellenumfeld.html`,
`07-bericht.html`, `08-einstellungen.html`, `09-systemregeln.html`.

**Neu**
- `components/shell/ShellRoot.vue`, `Shelf.vue` (Ablage), `Dossier.vue`,
  `Stack.vue` (Rückweg)
- `composables/useShellVariant.ts` (Flag), `composables/useNextStep.ts`
  (Weiter-Aktion, rein frontend-seitig aus `RunDetail` abgeleitet)
- `types/shelf.ts` — Objekttypen: Vorgang, Lauf, Bericht, Personasatz, Graph
- Routen: Ablage-Wurzel, Graph-Objekt, Bericht-Objekt, Personasatz-Objekt;
  Settings als Overlay-Router-View

**Angebunden — Endpoints, die endlich einen Aufrufer bekommen**
- `report/list` → Bericht-Objekte in der Ablage
- `report/chat` → Dossier-Reiter am Bericht
- `graph/project/list`, `graph/data/<id>`, `graph/snapshot/<id>/<round>`,
  `graph/<id>/diff`, `graph/<id>/export` → Graph-Objekt mit Scrubber und
  Diff-Liste, aufbauend auf `components/graph/GraphDiffPanel.vue`
- `runs/<id>/cancel`, `simulation/<id>/pause|resume` → Zeilenaktion,
  Dossier-Kopf, Topbar-Indikator
  **Stolperstelle:** `run_id` und `simulation_id` werden unabhängig vergeben
  und nur über `linked_ids.simulation_id` verbunden (`api/runs.py:78ff`) —
  das hat schon einmal jeden Abbrechen-Klick mit HTTP 400 scheitern lassen.

**Gelöscht (am Blockende, mit dem Flag)**
`views/Home.vue`, `views/RunsView.vue`, `views/RunDetailView.vue`,
`components/RunsDashboard.vue`, `components/v4/shell/{AppShell,Sidebar,SidebarItem,SidebarGroup,Topbar,DensityToggle}.vue`,
Notification-Glocke, `AD`-Div → Nutzermenü aus `userProfile`.

**Testid-Kontrakt — Voraussetzung, nicht Nacharbeit**
Der Shell-Bereich hat heute **keine** Einträge in `contracts/testIds.ts`;
Tests hängen an CSS-Klassen (`.app-shell__sidebar`, `.topbar__hamburger`,
`.run-row`, `[data-app-shell-drawer]`, `[data-sidebar-trigger]`, `[data-crumb]`).
Deshalb bricht jede Umbenennung sofort. Die neuen Komponenten bekommen von
Anfang an Testids in `testIds.ts`.

---

### B4 — Öffnung

- Personasätze als Top-Level-Objekt (verwalten, anlegen, bearbeiten) —
  `PersonaLibraryPanel.vue` wandert aus `Step2EnvSetup.vue:343` heraus
- Schnellstart „Neue Simulation aus Personasatz" + Adapter, der einen
  minimalen Graph erzeugt
- Mobile 390px
- Aus Bericht neue Simulation ableiten

---

## 4. Tests

**22 müssen angepasst werden** (alle in B3, außer wo vermerkt):

*Bricht sicher:* `shell/__tests__/{AppShell,Sidebar,Sidebar.disabled-stubs,Topbar,DensityToggle,useShellStore}.spec.ts`,
`stores/__tests__/shell.spec.ts`, `router/__tests__/index.spec.ts`,
`views/__tests__/{Home,RunsView,AppShellWrappers}.spec.ts`,
`components/__tests__/RunsDashboard.spec.ts`,
`views/v4/steps/__tests__/StepWrapperViews.spec.ts` (mountet echtes AppShell),
`tests/e2e/drawer-focus-trap.spec.ts` (härteste Kopplung: `.topbar__hamburger`,
`[data-app-shell-drawer]`, `.app-shell__main`)

*Bricht wahrscheinlich:* `shell/__tests__/{SidebarItem,SidebarGroup,Breadcrumbs,CommandPalette}.spec.ts`,
`composables/__tests__/useSidebarState.spec.ts`,
`stores/__tests__/commandsStore.spec.ts` (feste IDs `nav:dashboard`, `nav:runs`, …),
`tests/e2e/golden-gate-accessibility.spec.ts` (nur Blöcke `Shell → Runs` und
`Run Detail`), `tests/e2e/run-budget.spec.ts`

**Regressionsnetz — muss durchgehend grün bleiben:**
`composables/__tests__/useCommandPalette.spec.ts`,
`router/__tests__/onboardingGuard.spec.ts`, `tests/accessibility-helpers.spec.ts`,
`tests/e2e/{health,ai-model-picker,upload-graph,minimal-report,report-modes}.spec.ts`,
`i18n/__tests__/locale-coverage.spec.ts`, sowie die zehn Specs, die
`AppShell.vue` wegmocken und nur die `breadcrumbs`-Prop prüfen — solange diese
Schnittstelle erhalten bleibt.

**Kein Risiko aus dem Theme-Wechsel:** 0 Snapshot-Tests, 0 Tests auf Farbwerte.

---

## 5. Reihenfolge

```
B1 ──────────────┐
                 ├── B3 ── B4
B2 ──────────────┘
```

B1 und B2 laufen parallel und berühren sich nicht (Frontend-Tokens gegen
Backend-Jobs). B3 braucht beide: die Tokens für die Optik, die Cancel-Endpoints
für die Zeilenaktionen. B4 setzt auf dem Objektmodell auf.

---

## 5a. Stand (18.08.2026)

| Block | Zustand | Wo |
| --- | --- | --- |
| B1 Fundament | **erledigt, auf main** | PR #1370 |
| B2 Abbrechen | **erledigt, auf main** | PR #1371 |
| B3 Objektmodell | **erledigt, auf main** | PR #1372 |
| B4 Öffnung | **in Arbeit** | `feat/b4-oeffnung` |

Was B3 noch fehlt: Bericht-Leseumgebung mit Belegrand, Graph-Objekt mit
Rundenscrubber, Einstellungen als Overlay, Löschen der Altansichten
(`Home.vue`, `RunsView.vue`, `RunDetailView.vue`, `RunsDashboard.vue`,
`v4/shell/*`) und zuletzt das Entfernen des Flags.

Drei Fehler, die beim Bauen von B3 auffielen und im PR mit erledigt sind:
`listPersonaTemplates` gab die Envelope zurück, deklarierte aber ein Array —
Personasätze wären in der Ablage nie erschienen. Die dynamisch gebildeten
Statusschlüssel (`shelf.status.report_*`, `project_*`) existierten in keiner
Locale, und das mitgegebene `{ fallback }` war wirkungslos. Und das Dossier
behauptete ohne Auswahl „Noch keine Objekte“, während die Ablage voll war.

### B4 im Einzelnen

| Teil | Zustand |
| --- | --- |
| Mobile (390px) | erledigt — ⌘K raus aus dem Markup, Jobs-Tabelle scrollt im eigenen Kasten, Kopfzeile gibt auf schmal Wortmarke und Trenner frei |
| Aus Bericht ableiten | erledigt — im Dossier des Berichts, mit Übernahme der Personas |
| Personasätze als Objekt | erledigt — in der Ablage, mit Beruf/Land/Interessen im Dossier |
| Start nur aus Personas | Backend-Service in Arbeit; Endpunkt und Einstieg in der Ablage folgen |

Zum letzten Punkt: Der OASIS-Lauf braucht den Graphen **zur Laufzeit nicht**
— `branching_service.create_branch` beweist, dass `CREATED → PREPARING → READY`
ohne die Entity-Phase geht, und `add_simulation_profile` schreibt Personas
bereits im richtigen Format. Die harte Bindung an eine `graph_id` sitzt in der
**Report**-Erzeugung (drei Stellen). Der ehrliche Vorbehalt: Berichte aus einem
reinen Persona-Lauf laufen technisch durch, aber ohne Graph-Belege — das ist
ein Qualitätsproblem, kein technisches, und gehört dem Nutzer vorher gesagt.

---

## 6. Offen / bewusst verschoben

- `_persist_episode` auf eine Transaktion pro Chunk umbauen — eigene Aufgabe,
  gehört nicht in einen UI-Umbau
- `ontology_generate` auf `enqueue` umstellen — nur falls die Wartezeit
  tatsächlich stört
- Light-Palette füllen
- Zwei Berichte vergleichen (gestrichen, bis es konkret gebraucht wird)
