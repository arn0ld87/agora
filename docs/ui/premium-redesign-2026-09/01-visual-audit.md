# Agora UI — Visual Audit (Stand 05.09.2026)

**Basis:** gerenderte App aus `main` (`e80d11eb`), lokaler Stack mit Stub-LLM, ein vollständiger Lauf (`sim_cf5500a23f56`, `report_f5e440a94153`), 23 Routen bei 1440×900, 1280×800, 1024×768 und 390×844. Screenshots: `docs/ui/premium-redesign-2026-09/shots/` (Ist) und `docs/design/screens/` (Vorlage, Aug 2026).

Bewertet wird die tatsächlich gerenderte Anwendung, nicht der Quellcode. Beide Shells sind im Umlauf: die **Dossier-Shell** (`/ablage`, Default seit PR #1375) und die **klassische AppShell** (`/dashboard`, `/runs`, `/v4/*`, `/settings/*`), in der alle Arbeitsansichten weiterhin liegen.

## 1. Bewertung (0–10)

| Dimension | Note | Begründung |
|---|---|---|
| Gesamteindruck | **4** | Die Dossier-Shell hat eine eigene, ernsthafte Identität (warm-dunkel, Kupfer, Archivo/Newsreader/Geist Mono, Hairlines statt Cards). Sobald man klickt, landet man in der alten AppShell mit Card-Kit, Wizard-Stepper und Legacy-Views mit eigenem Header und Footer. Zwei Produkte in einem. |
| Informationsarchitektur | **3** | Zwei Navigationsmodelle (Ablage/Stapel vs. Sidebar/Breadcrumb). `/runs` und `/runs/:id` sind Entwickler-Registry-Ansichten, kein Nutzerobjekt. Graphen tauchen in der Ablage nicht auf, Settings sind eine Sidebar-Gruppe mit sechs Unterseiten. Die wichtigste Frage „was läuft, wie weit, was tue ich als Nächstes“ beantwortet keine Startseite. |
| Layout | **4** | Dossier: 400px-Liste + leere 1040px-Fläche ohne Auswahl. AppShell: Hero-Formular 550px hoch, Stats-Zeile, dann Cards; Report-Seite 44 691px hoch; History-Tabelle 700px in 1180px Content. Kein gemeinsames Raster, Content-Breiten pro Seite anders. |
| Typografie | **5** | Die drei Familien sind richtig gewählt. Aber: 40 verschiedene font-size-Werte, Masse der UI auf 10–13px, drei Label-Systeme (Mono-Uppercase mit „№ 01 —“, Sans-Uppercase, Sans normal), Mono-Uppercase auch für Hilfetexte und Leerzustände, englische Display-Headline in `/v4/history`. |
| Farben | **5** | Palette und Hairline-System sind gut. Fremdkörper: blau-violetter Logo-Glyph, violette `.env`-Pill, Status-Grün/Gelb/Rot in je drei Tönen, Kupfer als Fokus-, Selektions-, Primär- *und* Card-Rahmenfarbe. 239 hartkodierte Hex-Werte in 56 Komponenten. |
| Konsistenz | **2** | 35 Border-Radius-Werte, 21 native `<select>` neben gestylten Selects und reka-ui-Dropdowns, Buttons in fünf Bauformen (Pill, Outline, Ghost, Mono-Uppercase, ungestylter Kasten „Neues Profil“), zwei Radius-Skalen, zwei Shells, Sprachmix DE/EN (Runs, Compare, „History, resume, branching“, „Task completed“). |
| Informationsdichte | **4** | Dossier viel zu dünn (Lauf zeigt Status, Uhrzeit, ID — sonst nichts). AppShell zu locker (Hero, Cards mit 24px-Padding, Riesenzahlen „0 / 3 / — / 0“). Die Vorlage `03-laeufe.html` zeigt, wie dicht es sein sollte. |
| Interaktionsdesign | **4** | Jede Ablage-Zeile hat denselben Button „Bericht lesen“, auch der Lauf. `/feed` hat keine Shell und keinen Rückweg. Abbrechen/Pause existieren nur als Text-Buttons. „Starten“ auf dem Dashboard ist grau und 700px vom Formular entfernt. LOGS-FAB, „?“ und ⌘K-Chip konkurrieren als Chrome. |
| Simulation UX | **2** | Step-3-Seite zeigt Erklärtext und einen Button. Weder Agentenzahl, Runden, Provider, Modell noch Fehler. Der Live-Feed ist eine leere Seite mit zwei Plattform-Boxen. Die Vorlage `04-simulation.html` (Rundenachse, vier Bahnen, Eingriffe) ist nicht gebaut. |
| Report UX | **3** | Bericht = Formular (Modell, Modus, Neu generieren) + linearer 44k-px-Stack aus 12 Abschnitten. Confidence als „0% · spekulativ“-Chip ohne Erklärung. Keine Outline im Viewport, kein Belegrand, keine Unsicherheiten-Übersicht. Das Dossier des Berichts listet nur Abschnittstitel. |
| Accessibility | **6** | Fokusringe, ARIA-Rollen, FocusScope und reduced-motion sind vorhanden. Schwächen: Mono-Uppercase-Hilfetexte in 10–11px, `--text-tertiary` (4,0:1) für Labels und Leerzustände, rohe Exception-Texte, fehlende sichtbare Struktur im Report. |

## 2. Die 15 größten Designprobleme (nach Auswirkung)

1. **Zwei Shells, zwei Navigationsmodelle.** Ablage/Stapel für Einstieg, AppShell/Sidebar für alles Weitere. Jeder Klick auf „Bericht lesen“ wechselt das Produkt. (`ShellRoot.vue` vs. `AppShell.vue`)
2. **Legacy-Views im Shell.** `/runs` und `/runs/:id` bringen eigenen Header („✕ Agora / ← STARTSEITE“), Website-Footer, native Selects und ISO-Timestamps mit Mikrosekunden. (`RunsDashboard.vue`, `RunDetailAppShellView.vue`)
3. **Simulation ohne Instrument.** Step 3 zeigt Text + Button; der Feed ist shell-los und leer. Keine Antwort auf „was läuft, wie weit, gibt es Probleme, kann ich eingreifen“. (`Step3Simulation.vue`, `StepSimulationFeedView.vue`)
4. **Bericht als Formular-Stack.** Erst Modell/Modus-Formular, dann 12 Abschnitte linear, 44 691px. Keine Leseumgebung, keine Outline im Viewport, kein Belegrand. (`Step4Report.vue`)
5. **Leeres Dossier.** Lauf-Dossier: Status/Zeit/ID, sonst nichts. Bericht-Dossier: Abschnittstitel. Die Vorlage sieht Kennzahlstreifen (Runden, Belege, Aussagen), Bestandteile und Red-Team-Kasten vor. (`Dossier.vue`, `useObjectDetail.ts`)
6. **Leere Startfläche.** `/ablage` ohne Auswahl: ein Satz in 1040×850px. Kein Überblick über aktive Läufe, keine offenen nächsten Schritte, keine Systemprobleme.
7. **Label-Chaos.** Mono-Uppercase-Kicker mit „№ 01 —“ auf jeder Card, Sans-Uppercase-Feldlabels, Mono-Uppercase-Hilfetexte (Env-Setup), Mono-Uppercase-Leerzustände (Interaktion), Serif-Unterzeilen. Drei Systeme auf einer Seite.
8. **Typo-Skala ohne Skala.** 40 font-size-Werte; 11px ist der häufigste Wert (111×). Body ist 15px, die Arbeitsfläche läuft auf 10–13px.
9. **Card-Kit statt Struktur.** Dashboard, Graph-Build, Env-Setup, Settings: identische Rounded Cards mit gleichem Radius, teils Card-in-Card, einmal mit Kupfer-Rahmen ohne Grund. LLM-Provider: 3×3 Cards mit **acht Primärbuttons**.
10. **Fremdfarben und Farbüberladung.** Logo-Glyph blau/violett, `.env`-Pill violett, Kupfer gleichzeitig Primär, Fokus, Selektion, Stepper-Linie, Card-Rahmen, Kicker.
11. **Aktionen ohne Hierarchie.** Ablage-Zeile: immer „Bericht lesen“, auch beim Lauf. Dashboard: „Starten“ grau, weit rechts. Report: „Neu generieren“ oben, Abschnitte darunter. Graph-Build: Export-Formate als Haupt-Toolbar.
12. **Sprachmix.** „Runs“, „Compare“, „History, resume, branching“, „Task completed“, „REPORT GENERATION COMPLETED“, Breadcrumb „Settings / General“ über Titel „Allgemein“.
13. **Rohe Technik im UI.** Python-Exception als Systemstatus, `run_type`-Werte als Mono-Labels (report_generate), UUIDs als Zeilenwerte, Env-Variablennamen als Tabellenspalten.
14. **Chrome-Rauschen.** LOGS-FAB auf jeder Seite (kollidiert mit Inhalten), „?“-Kreis, ⌘K-Chip, „Komfort“-Toggle, „MODELL: Modell wählen … STANDARD“-Chip, der nichts sagt.
15. **Inkonsistente Controls.** 21 native `<select>`, 35 Radius-Werte, Buttons in fünf Bauformen, Checkbox-Labels mal Mono-Uppercase, mal normal, Sidebar-Sub-Items ungleich gesetzt.

## 3. Neue Designrichtung

### Entscheidung zur Farbwelt (Widerspruch zum Brief)

Der Brief nennt Navy `#0A0F2C` und `#5C4EFF` als Ausgangsbasis, „kein Zwang“. Ich rate davon ab und bleibe bei der im Repo seit August dokumentierten Richtung (PLAN.md §1, `tokens-v3.css`, `docs/design/screens/`):

- Navy + Violett ist exakt die Palette, die der Brief unter „generischer AI-SaaS-Look“ verbietet. Sie ist heute der Default von Linear-Klonen und jedem LLM-generierten Dashboard.
- Die warm-dunkle Palette mit Kupfer ist bereits gebaut, getestet (`designTokens.spec.ts`) und trägt eine erkennbare Identität: Papier-und-Tinte, Recherche, Dossier. Sie kollidiert nicht mit der Statusskala (Grün/Gelb/Rot), was `#5C4EFF` als Info-Farbe tun würde.
- Die Marke „Agora“ hat im Frontend heute einen blauen Glyph, im Repo aber Kupfer-Ring als Wortmarke. Der Glyph wird angepasst, nicht die Palette.

Was ich an der bestehenden Richtung ändere: weniger Mono-Uppercase, eine Type-Scale, eine Radius-Skala, Kupfer nur für Primäraktion und Selektion, Türkis `#5fb6c9` (aus der Vorlage) als einzige zweite Signalfarbe für „live/jetzt“.

### Visuelle Sprache

**Ein Instrument, keine Kachelwand.** Flächen werden durch Hairlines und Surface-Stufen getrennt, nicht durch Cards. Cards gibt es nur für abgesetzte Objekte (Red-Team-Kasten, Toast, Dialog). Zahlen stehen in Geist Mono, Lesetext in Newsreader, alles andere in Archivo. Struktur-Elemente (Kicker, Hairline, Nummer) tragen Information oder fallen weg.

### Layoutprinzipien

- **Eine Shell.** ShellRoot mit 46px-Kopfzeile, Stapel als Rückweg, Ablage links. Alle Arbeitsansichten (Simulation, Bericht, Graph, Akteure, Einstellungen) öffnen als Vollbild-Objekt im selben Rahmen, nie in einer zweiten Sidebar-Welt.
- **Raster:** Seitenpadding 24px, Spaltenabstand 16px, vertikaler Rhythmus 8px. Content-Breiten: Liste 400px, Lesespalte 62ch, Belegrand 320px, Vollbild bis 1600px.
- **Dichte:** Standardzeile 44px (Liste), 36px (Tabelle), Kontrollhöhe 32px, kompakte Variante 28px.
- **Above the fold:** Jede Ansicht beantwortet in den ersten 900px Zustand, Fortschritt, Problem, nächste Handlung.

### Typografie

| Rolle | Familie | Größe / Zeilenhöhe | Gewicht | Verwendung |
|---|---|---|---|---|
| display | Archivo | 28 / 1.15 | 600 | Dossier-Titel, Vollbild-Titel |
| title | Archivo | 20 / 1.25 | 600 | Abschnitt, Panel-Titel |
| heading | Archivo | 16 / 1.35 | 600 | Zeilen-Titel, Tabellen-Objekt |
| body | Archivo | 14 / 1.5 | 400 | UI-Text, Beschreibungen |
| small | Archivo | 12.5 / 1.45 | 400/500 | Meta, Hilfetext, Tabellenzellen |
| label | Archivo | 11.5 / 1.3 | 500, Tracking 0.02em | Spaltenköpfe, Feldlabels — **kein Uppercase** |
| prose | Newsreader | 17 / 1.6 | 400 | Berichtstext, Zitate (Italic-Achse) |
| mono | Geist Mono | 12 / 1.4 | 400/500 | IDs, Zahlen, Zeiten, Log |
| mono-lg | Geist Mono | 22 / 1.1 | 500 | Kennzahlen im Statstreifen |

Uppercase bleibt nur für Kind-Tags (LAUF / BER / PERS / GRPH) und Status-Chips, in Geist Mono 10.5px.

### Komponentenstil

- Buttons: `primary` (Kupfer-Fläche, dunkle Schrift), `secondary` (Hairline-Rahmen), `ghost` (nur Text), `danger` (Coral-Rahmen). Höhe 32px, Radius 6px, ein Primärbutton pro Fläche.
- Inputs/Selects: Surface-inset, 1px Hairline, 32px, Radius 6px; native Selects nur mit `appearance:none` + eigenem Chevron. Kein Mono in Inputs außer bei IDs.
- Tabellen: 36px-Zeilen, Hairline unten, Spaltenköpfe `label`, Zahlen rechtsbündig in Mono, Zeile hover = surface-hover, selected = accent-tint + 2px Kupfer-Kante links.
- Status: Text vor Farbe („Simulation pausiert · Runde 12/20“), Farbpunkt 8px daneben. Chips nur für Kind und Status, nie für Meta.
- Leerzustände: ein Satz + eine Handlung, kein Icon-Illustrationsblock.

### Informationsdichte

Dossier-Kopf: Titel + Statussatz + Kennzahlstreifen (5 Zahlen). Darunter Bestandteile als Zeilen mit Zahl und Weiter-Aktion. Simulation: vier Bahnen nebeneinander. Bericht: drei Spalten. Tabellen mit 7–8 Spalten sind erwünscht, wenn die Spalten Prüfgrößen sind (Aussagen, Belege, Lücken, Nächster Schritt).

## 4. Design-System (Foundations + semantische Tokens)

Zielbild für `tokens-v3.css` nach Entkernung: **~60 semantische Tokens**, Compat-Aliase in eine eigene Datei `tokens-compat.css`, die pro Slice schrumpft.

```text
bg.canvas        #0b0a09   Grund hinter allem
bg.base          #14110f   Seite / Panels
bg.elevated      #1b1815   abgesetzte Fläche (Dialog, Toast, Card)
bg.inset         #0d0c0a   Inputs, Code, Log
bg.hover         rgba(242,236,228,.06)
bg.selected      rgba(208,138,82,.10)   Kupfer-Tint

text.primary     #f2ece4   (≥ 15:1)
text.secondary   #a89f94   (7.3:1) Beschreibungen, Meta
text.muted       #7c736a   (4.0:1) nur Labels ≥ 11.5px/500, nie Fließtext
text.on-accent   #1a120b

border.default   rgba(242,236,228,.12)
border.strong    rgba(242,236,228,.22)
border.subtle    rgba(242,236,228,.08)

accent.primary   #d08a52   Primäraktion, Selektion, aktiver Filter
accent.hover     #e6a878
accent.live      #5fb6c9   „jetzt“, laufende Runde, Live-Indikator (einzige zweite Signalfarbe)

status.success   #7fb069   Text + Punkt
status.warning   #d4a23c
status.error     #e2603f
status.info      = text.secondary (Info ist kein Farbereignis)
status.*-bg      jeweils 12 % Alpha

focus.ring       2px accent.primary, offset 2px
```

**Spacing:** 4 / 8 / 12 / 16 / 24 / 32 / 48 (sp-1…sp-7). **Radius:** 0 / 4 (Chip) / 6 (Control) / 10 (Card/Dialog) / 999 (Punkt). **Shadows:** nur `shadow.overlay` (Dialog/Toast) und `shadow.popover`. **Borders:** 1px, nie 1.5px außer Brand-Ring. **Icons:** 16px in Zeilen, 20px im Kopf, Strichstärke 1.5. **Motion:** 120ms ease-out für Hover/Fokus, 200ms für Panel/Tab, 320ms für Overlay; Fortschritt und Live-Punkt sind die einzigen Daueranimationen; `prefers-reduced-motion` schaltet Transitions ab und lässt Fortschritt als Sprung.

Was **gestrichen** wird: `--bg-grid`, Mesh-Tokens, `--r-pill` als Default, v1-Aliase (`--mono-*`, `--plasma-*`, `--neon-orange*`, `--paper-*`, `--ink-*`), `--accent-glow`, `--surface-glass*` — die Glas-/Glow-Tokens sind aus `tokens-v3.css` entfernt und überleben nur noch als Aliase in `tokens-compat.css`, bis die konsumierenden Regeln in `global.css` migriert sind.

## 5. Seitenplan

| Ansicht | Ist-Problem | Zielzustand | Änderungen |
|---|---|---|---|
| Ablage (Start) | Leere rechte Fläche, gleiche Aktion pro Zeile, Uhrzeit ohne Datum | Ohne Auswahl zeigt das Dossier eine **Übersicht**: laufende Läufe mit Fortschritt, offene nächste Schritte, Systemhinweise, Schnellstart. Zeilen tragen Zustandssatz und *ihre* Weiter-Aktion | `Dossier.vue` Übersichtszustand, `useShelf` nextAction pro Kind, Datum bei älteren Objekten, Filter als Text-Tabs |
| Dossier Lauf | Status/Zeit/ID, sonst nichts | Kennzahlstreifen (Runden, Personas, Belege, Aussagen, Budget), Bestandteile (Quellenumfeld, Akteure, Verlauf, Belege, Ausgabe) mit Zahl + Link, Jobs des Laufs als Zeitleiste, Eingriffe (Pause/Abbruch) | `useObjectDetail` erweitern (bestehende Endpunkte: `/runs`, `/simulation/<id>`, `/profiles`, `/metrics`) |
| Dossier Bericht | Abschnittsliste | Executive Summary in Serif, Confidence-Verteilung, Belege/Lücken/Hypothesen als Zahlen, Red-Team-Befunde, „Bericht lesen“ | `useObjectDetail` + Report-Contract-Felder |
| Läufe (`/runs`) | Legacy-Registry mit Footer | Ablage mit Filter „Läufe“ als dichte Tabelle (Runden, Zustand, Aussagen, Belege, Lücken, Angefasst, Nächster Schritt), Auswahl → Vergleich | `/runs` → Redirect `/ablage?filter=lauf`; Tabellenmodus in `Shelf.vue` |
| Simulation live | Text + Button, Feed shell-los | Vollbild im Shell: Kopfzeile (Runde x/y, vergangen, s/Runde, Fortsetzen/Abbrechen), Rundenachse, vier Bahnen (Akteure, Reddit, Twitter, Themen/System/Ereignisse), Eingriffe | Neuer `SimulationLiveView.vue` unter ShellRoot; Daten aus `/feed-snapshot`, `/metrics`, `/runs/<id>/events`, `/usage` |
| Simulation Setup | Card-in-Card, Mono-Hilfetexte | Ein Formular: Personas (Zahl, Quote), Runden, Plattform, Modell, Budget; Vorschau der Kosten | `Step2EnvSetup.vue`/`Step3Simulation.vue` Restyle, Feldlabels vereinheitlicht |
| Bericht lesen | Formular + 44k-px-Stack | Drei Spalten: Outline links, Serif-Lesespalte 62ch, Belegrand rechts (Claims mit Confidence-Wort, Belege, Lücken, Red-Team). Modell/Modus in ein Overlay „Neu generieren“ | `Step4Report.vue` aufteilen: `ReportReader.vue`, `ReportOutline.vue`, `ReportEvidenceRail.vue` |
| Graph | Toolbar aus Exporten, Warnbox, Cards | Objekt in der Ablage; Dossier zeigt Kennzahlen + Diff-Liste; Vollbild: Canvas + Detailpanel + Filter/Legende; Export im Overflow-Menü | `GraphDetailPanel.vue` bleibt, Toolbar reduzieren, Graph in `useShelf` als Objekt |
| Akteure/Personas | Wizard-Card | Objekt „Personasatz“ + Prüfung als Tabelle (Name, Rolle, Land, Zustand, Freigabe) | `PersonaCardGrid` → Tabelle mit Detail-Drawer |
| Einstellungen | 6 Unterseiten, Card-Grid mit 8 Primärbuttons | Overlay über der Route mit linker Sektionsliste; Provider als Liste mit einem Detail-Formular rechts; ein Primärbutton | `SettingsOverlay.vue`, Provider-Liste statt Grid |
| Onboarding | Karten-Wizard | bleibt, Restyle auf Formular-Stil |
| Interaktion/Umfrage | Mono-Tabs, Mono-Listen | Dossier-Reiter „Nachfragen“ mit Agentenliste (Sans) und Chat-Spalte | Restyle |
| History/Compare | Marketing-Hero, native Selects | History entfällt (Ablage-Filter „Alle Jobs“), Compare wird Zwei-Läufe-Auswahl aus der Läufe-Tabelle | Routen → Redirects |

## 6. Screenshots / visuelle Referenz

- Ist: `docs/ui/premium-redesign-2026-09/shots/ist/{desktop,small,phone}--*.png`
- Vorlage (Aug 2026): `docs/design/screens/01-ablage.html`, `04-simulation.html`, `07-bericht.html`, `03-laeufe.html`
- Vorlagen gerendert (alle zehn `docs/design/screens/*.html`, inkl. Kommandopalette, Akteure, Quellenumfeld, Einstellungen, Systemregeln): `docs/ui/premium-redesign-2026-09/shots/design/{00-vorspann,01-ablage,02-kommandopalette,03-laeufe,04-simulation,05-akteure,06-quellenumfeld,07-bericht,08-einstellungen,09-systemregeln}.png`
- Zielbilder dieses Audits (HTML auf `targets/tokens.css`, dem Referenz-Stylesheet für PR 1): `docs/ui/premium-redesign-2026-09/targets/{ablage-uebersicht,simulation-live,bericht-lesen}.html`
- Zielbilder gerendert: `docs/ui/premium-redesign-2026-09/shots/targets/{desktop,small}--{ablage,simulation,bericht}.png`
- Vorher/Nachher-Vergleich PR 1 (`ui(tokens)`, #1427, Commit `06bbb37c`): `docs/ui/premium-redesign-2026-09/shots/vergleich-pr1/` und [`02-screenshot-vergleich-pr1.md`](02-screenshot-vergleich-pr1.md)

### Was die Zielbilder gegenüber den Vorlagen aus `docs/design/screens` ändern

- **Ablage:** Das leere Dossier wird zur Übersicht („Braucht dich“ / „Läuft gerade“ / „Zuletzt fertig“ / System). Eine einzige Primäraktion („Quelle ablegen“) oben rechts; Zeilenaktionen erscheinen erst bei Hover. Filter in Satzschrift statt Mono-Versalien, Zähler in Mono. Kein „?“-FAB, kein LOGS-FAB – Protokoll und Suche sitzen in der Kopfzeile.
- **Simulation:** Ein Kennzahl-Streifen beantwortet die sechs Fragen (Runde, Zeit/ETA, Agenten, Tool-Calls, Budget, Fehler) auf einen Blick. Degradierung ist eine gelbe Zeile mit Ursache, Fallback-Modell und Konsequenz – kein Modal, kein Toast. Tool-Calls stehen als Zeile im Beitrag, Fallback-Antworten tragen ein Badge. Unter 1280 px werden Reddit/Twitter zu Tabs.
- **Bericht:** Die Zusammenfassung ist Abschnitt 0 mit „Was der Bericht trägt“ (Befund + Vertrauensstufe + Belegzahl). Der Belegstand steht als Satz über dem Titel (0 high · 4 medium · 25 low, 92 ungebundene Belege), nicht als KPI-Kachel. Belegrand rechts bleibt sticky; die Quellengattungen aus `EvidenceSourceKind` werden wörtlich gezeigt, inklusive „inferred – nicht zulässig“.

### Responsive-Befunde (Ist)

- 390 px: Dossier-Titel bricht Wort für Wort über neun Zeilen (Display-Größe nicht fluid); Filter-Tabs in zwei Zeilen; drei schwebende Elemente (Primärbutton, LOGS, „?“) konkurrieren.
- 1024 px: Classic-Dashboard mit drei konkurrierenden Spalten, 440 px hohe Dropzone; Legacy-Simulation mit Header-Overlap (Breadcrumb über Modell-Chip).
- 1280 px: Layout nicht fluid, nur Ränder schrumpfen; kein horizontaler Overflow auf keiner Route.
- Konsequenz im Token-Set: `--fs-display: clamp(22px, 2.2vw, 28px)`, `text-wrap: balance` auf Titeln, Breakpoints 1280 / 1024 / 768 mit festen Regeln (Ablage 340 px, Dossier als Overlay unter 1024).

## 7. Implementierungsplan (kleine, prüfbare PRs)

Reihenfolge nach Hebelwirkung. Jeder PR: Vitest + `bun run check` + Screenshot-Vergleich der betroffenen Routen bei 1440 und 1024.

| # | PR | Inhalt | Risiko |
|---|---|---|---|
| 1 | `ui(tokens)`: Type-Scale, Radius-Skala, Label-Stil | `tokens-v3.css` entkernen, `tokens-compat.css` abspalten, `.t-*`-Klassen auf neue Skala, `text-transform: uppercase` aus Feldlabels/Hilfetexten, Logo-Glyph auf Kupfer | niedrig (Snapshot-Tests der Tokens anpassen) |
| 2 | `ui(shell)`: Chrome bereinigen | LOGS-FAB → Kopfzeilen-Icon, „?“ → Menü, ⌘K-Chip einheitlich, Brand-Ring statt Glyph, `/feed` in den Shell | niedrig |
| 3 | `ui(ablage)`: Übersicht + Zeilen | Dossier-Übersichtszustand, Weiter-Aktion pro Kind, Datum, Filter-Tabs | mittel |
| 4 | `ui(dossier)`: Lauf + Bericht anreichern | Kennzahlstreifen, Bestandteile, Jobs-Zeitleiste; Bericht-Summary, Confidence-Verteilung | mittel (nur bestehende Endpunkte) |
| 5 | `ui(controls)`: Button/Input/Select/Table-Primitives | 21 native Selects, fünf Button-Bauformen, Tabellenstil; Settings-Provider als Liste | mittel |
| 6 | `ui(report)`: Leseumgebung | Dreispaltiger Reader, Outline, Belegrand, Overlay „Neu generieren“ | hoch (größte Datei, 1767-Zeilen-Spec) |
| 7 | `ui(simulation)`: Live-Instrument | Kopfzeile, Rundenachse, vier Bahnen, Eingriffe | hoch (Polling/Events) |
| 8 | `ui(runs)`: Läufe-Tabelle + Vergleich | `/runs` → Ablage-Tabelle, Compare-Auswahl, History-Redirect | mittel |
| 9 | `ui(settings)`: Overlay | Sektionsliste + Formular | mittel |
| 10 | `chore(ui)`: Legacy löschen | `RunsDashboard.vue`, `Home.vue`, `RunDetailView`, AppShell-Reste, `useShellVariant` | niedrig nach 3–9 |

Backend-Wünsche (separat, nicht Teil der UI-PRs): Bericht-Titel nicht auf 80 Zeichen hart abschneiden (`report/list`), Statusmeldungen lokalisierbar statt „Task completed“, Systemstatus mit strukturiertem Fehlercode statt Exception-String.
