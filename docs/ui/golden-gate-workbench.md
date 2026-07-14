# Agora Designsystem: Golden Gate Workbench

**Version:** 1.0  
**Status:** Umsetzungsgrundlage für Slice 7  
**Zielpfad im Repository:** `docs/ui/golden-gate-workbench.md`

## 1. Zweck

Agora ist eine lokal-first und providerneutrale Analyseplattform. Die Oberfläche soll wie eine präzise Operator-Workbench wirken: ruhig, verlässlich, technisch und hochwertig. Sie darf weder wie eine generische KI-Demo noch wie eine Marketing-Landingpage aussehen.

Das Designsystem gilt verbindlich für:

- App-Shell und Navigation
- Onboarding
- Profil und Einstellungen
- Anbieter- und Modellverwaltung
- `AiModelPicker`
- Runs, Reports und Monitoring
- Projekte, Datensätze und Vorlagen
- Dialoge, Formulare, Tabellen und Statusdarstellungen

## 2. Gestaltungsprinzipien

### 2.1 Präzision vor Dekoration

Jedes sichtbare Element braucht eine funktionale Aufgabe. Farbe, Tiefe und Bewegung strukturieren Informationen, statt Aufmerksamkeit zu verlangen.

### 2.2 Ruhe durch Hierarchie

Wenige Oberflächenebenen, klare Abstände und konsistente Typografie. Keine Glows, Sparkles oder permanenten Verläufe. Menschen müssen ohnehin schon genug blinkende Dinge ertragen.

### 2.3 Ehrliche Zustände

Nicht konfigurierte, eingeschränkte oder experimentelle Funktionen werden eindeutig benannt. Ein deaktivierter Menüpunkt ist kein Produktfeature.

### 2.4 Lokal und Cloud sichtbar unterscheiden

Lokale Dienste, Cloud-APIs und experimentelle CLI-Bridges erhalten unterscheidbare Labels, Symbole und Hilfetexte. Die Unterscheidung darf nicht ausschließlich über Farbe erfolgen.

### 2.5 Zugänglichkeit ist Teil der Komponente

Tastaturbedienung, Fokuszustände, Screenreader-Namen, verständliche Fehlermeldungen und Reduced Motion sind keine spätere Politur.

---

## 3. Markencharakter

| Eigenschaft | Bedeutung |
|---|---|
| Ruhig | geringe visuelle Lautstärke, klare Flächen |
| Präzise | exakte Ausrichtung, nachvollziehbare Zustände |
| Vertrauenswürdig | keine versteckten Fallbacks oder irreführenden Versprechen |
| Technisch | Daten und Systemzustände sind gut lesbar |
| Hochwertig | kontrollierte Tiefe, sorgfältige Typografie |
| Offen | lokal-first, providerneutral, nachvollziehbar |

### Vermeiden

- Neon-Lila und Cyan als dominierende KI-Klischees
- dauerleuchtende Verläufe
- übertriebene Glows
- beliebige Glassmorphism-Schichten ohne Kontrast
- dekorative Animationen bei jeder Interaktion
- riesige Marketing-Headlines in Arbeitsansichten
- Golden-Gate-Brückenmotive als wiederkehrende Dekoration
- verstreute Hex-Werte in Einzelkomponenten

---

## 4. Token-Architektur

Tokens werden in drei Ebenen gepflegt:

1. **Primitive Tokens:** rohe Farb-, Größen- und Zeitwerte
2. **Semantische Tokens:** Bedeutung wie `surface`, `text`, `danger`
3. **Komponenten-Tokens:** nur bei nachweislich besonderem Bedarf

Komponenten verwenden grundsätzlich semantische Tokens. Direkte Primitive sind auf Token-Dateien und dokumentierte Sonderfälle begrenzt.

```text
Primitive
└── bay.950

Semantisch
└── color.background.canvas

Komponente
└── sidebar.background
```

---

## 5. Farben

### 5.1 Primitive Farbpalette

#### Bay

| Token | Wert | Verwendung |
|---|---:|---|
| `bay-950` | `#07111F` | tiefster Hintergrund |
| `bay-900` | `#0B1728` | App-Canvas |
| `bay-850` | `#0F1D30` | Sidebar, Topbar |
| `bay-800` | `#14243A` | Cards und Panels |
| `bay-700` | `#1C304B` | Hover und erhöhte Flächen |
| `bay-600` | `#2B4260` | aktive Rahmen |
| `bay-500` | `#415B78` | dekorative Linien |

#### Fog

| Token | Wert | Verwendung |
|---|---:|---|
| `fog-50` | `#F7F5F0` | primärer Text auf Dunkel |
| `fog-100` | `#ECE9E2` | hoher Kontrast |
| `fog-200` | `#D8D4CB` | sekundärer Text |
| `fog-300` | `#B8B6AF` | gedämpfter Text |
| `fog-400` | `#929690` | Meta und Placeholder |
| `fog-500` | `#6F7775` | deaktiviert |

#### Akzente

| Token | Wert | Bedeutung |
|---|---:|---|
| `gate-400` | `#FF7358` | Hover auf Primäraktion |
| `gate-500` | `#F05A3C` | Primäraktion |
| `gate-600` | `#D7462D` | gedrückter Zustand |
| `gate-700` | `#B93625` | Light-Theme Primärfläche |
| `gold-400` | `#F1C86A` | Fokus, Auswahl, besonderer Hinweis |
| `gold-500` | `#D9A942` | aktive Highlights |
| `mint-400` | `#69D4B0` | Erfolg und verfügbar |
| `mint-500` | `#43B890` | Erfolg auf hellen Flächen |
| `sky-400` | `#6FB1FF` | Information und Cloud |
| `amber-400` | `#F0B75C` | Warnung und eingeschränkt |
| `red-400` | `#F17474` | Fehler auf Dunkel |
| `red-600` | `#B12F2F` | Fehler auf Hell |

### 5.2 Semantische Tokens, Dark Theme

| Token | Wert |
|---|---|
| `--color-bg-canvas` | `bay-950` |
| `--color-bg-app` | `bay-900` |
| `--color-bg-shell` | `bay-850` |
| `--color-bg-surface` | `bay-800` |
| `--color-bg-surface-hover` | `bay-700` |
| `--color-bg-elevated` | `rgba(20, 36, 58, 0.88)` |
| `--color-border-subtle` | `rgba(216, 212, 203, 0.10)` |
| `--color-border-default` | `rgba(216, 212, 203, 0.18)` |
| `--color-border-strong` | `bay-600` |
| `--color-text-primary` | `fog-50` |
| `--color-text-secondary` | `fog-300` |
| `--color-text-muted` | `fog-400` |
| `--color-text-disabled` | `fog-500` |
| `--color-action-primary` | `gate-500` |
| `--color-focus-ring` | `gold-400` |
| `--color-success` | `mint-400` |
| `--color-warning` | `amber-400` |
| `--color-danger` | `red-400` |
| `--color-info` | `sky-400` |

### 5.3 Semantische Tokens, Light Theme

| Token | Wert |
|---|---|
| `--color-bg-canvas` | `#EEEAE2` |
| `--color-bg-app` | `#F5F3EE` |
| `--color-bg-shell` | `#FFFFFF` |
| `--color-bg-surface` | `#FFFFFF` |
| `--color-bg-surface-hover` | `#F0EDE7` |
| `--color-bg-elevated` | `rgba(255, 255, 255, 0.94)` |
| `--color-border-subtle` | `rgba(11, 23, 40, 0.08)` |
| `--color-border-default` | `rgba(11, 23, 40, 0.14)` |
| `--color-border-strong` | `#A9A399` |
| `--color-text-primary` | `#0B1728` |
| `--color-text-secondary` | `#39485A` |
| `--color-text-muted` | `#536171` |
| `--color-text-disabled` | `#7B8490` |
| `--color-action-primary` | `#C8432B` |
| `--color-focus-ring` | `#9A6800` |
| `--color-success` | `#1C5F54` |
| `--color-warning` | `#8A5A00` |
| `--color-danger` | `#B12F2F` |
| `--color-info` | `#1B5A9C` |

### 5.4 Verifizierte Kontrastpaare

| Vordergrund | Hintergrund | Verhältnis | Ergebnis |
|---|---|---:|---|
| Fog 50 | Bay 950 | 17.38:1 | AAA |
| Fog 300 | Bay 950 | 9.33:1 | AAA |
| Fog 400 | Bay 950 | 6.30:1 | AA |
| Bay 950 | Gate 500 | 5.62:1 | AA |
| Bay 950 | Gold 400 | 11.91:1 | AAA |
| Bay 950 | Mint 400 | 10.50:1 | AAA |
| Red 400 | Bay 950 | 6.75:1 | AA |
| Text Primary Light | App Light | 16.22:1 | AAA |
| Text Muted Light | App Light | 5.71:1 | AA |
| Weiß | Light Action Primary (`#C8432B`) | 4.89:1 | AA |

**Regel:** `fog-50` darf nicht als Buttontext auf `gate-500` verwendet werden. Primärbuttons im Dark Theme verwenden `bay-950` als Textfarbe.

---

## 6. Typografie

### 6.1 Schriftfamilien

```css
--font-sans: "Manrope", Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
--font-mono: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
```

- **Manrope:** UI, Navigation, Überschriften und Formulare
- **IBM Plex Mono:** IDs, Zeitwerte, Logs, Code, Modellnamen und technische Metadaten
- Fonts nur aus lizenzierter oder selbst gehosteter Quelle laden
- Ohne Webfonts bleibt das System vollständig nutzbar

### 6.2 Typografische Skala

| Token | Größe / Zeilenhöhe | Gewicht | Verwendung |
|---|---|---:|---|
| `display-sm` | 32 / 40 px | 650 | Onboarding-Titel |
| `heading-xl` | 28 / 36 px | 650 | Seitenüberschrift |
| `heading-lg` | 22 / 30 px | 650 | Bereich |
| `heading-md` | 18 / 26 px | 650 | Card-Titel |
| `body-lg` | 16 / 26 px | 450 | hervorgehobener Fließtext |
| `body-md` | 14 / 22 px | 450 | Standard |
| `body-sm` | 13 / 20 px | 450 | kompakte UI |
| `label-md` | 13 / 18 px | 600 | Labels und Buttons |
| `caption` | 12 / 18 px | 500 | Meta und Hinweise |
| `mono-sm` | 12 / 18 px | 450 | technische Werte |

### Regeln

- Arbeitsansichten verwenden maximal `heading-xl`.
- Fließtext ist nie kleiner als 13 px.
- Form-Labels stehen oberhalb des Feldes.
- Modellnamen und IDs dürfen monospace sein, Beschreibungen nicht.
- Überschriften nutzen `letter-spacing: -0.015em`, Labels maximal `0.01em`.

---

## 7. Abstände und Layout

### 7.1 Spacing-Skala

4-px-Basis mit ausgewählten Zwischenstufen:

| Token | Wert |
|---|---:|
| `space-0` | 0 |
| `space-1` | 4 px |
| `space-2` | 8 px |
| `space-3` | 12 px |
| `space-4` | 16 px |
| `space-5` | 20 px |
| `space-6` | 24 px |
| `space-8` | 32 px |
| `space-10` | 40 px |
| `space-12` | 48 px |
| `space-16` | 64 px |
| `space-20` | 80 px |

### 7.2 Seitenlayout

```text
Desktop
┌──────── Sidebar 264 px ────────┬──────── Content ────────┐
│ Navigation                     │ max. 1440 px             │
│ Systemstatus                   │ 32 px Innenabstand       │
└────────────────────────────────┴──────────────────────────┘
```

- Desktop-Sidebar: 264 px
- kompakte Desktop-Sidebar: 80 px
- Content-Maximum: 1440 px
- Form-Maximum: 720 px
- Lesetext-Maximum: 68 Zeichen
- Hauptgrid: 12 Spalten
- Standard-Gap: 24 px
- dichte Datenansicht: 16 px
- Mobile Innenabstand: 16 px
- Desktop Innenabstand: 32 px

### 7.3 Breakpoints

| Token | Wert | Verhalten |
|---|---:|---|
| `xs` | 320 px | Mindestbreite |
| `sm` | 480 px | Formulare stabilisieren |
| `md` | 768 px | mobile Navigation endet |
| `lg` | 1024 px | Sidebar dauerhaft |
| `xl` | 1280 px | Mehrspalten-Workbench |
| `2xl` | 1536 px | große Monitoring-Ansichten |

Breakpoints folgen Inhalt und Funktion, nicht einzelnen Geräten.

---

## 8. Radien, Rahmen und Tiefe

### 8.1 Radien

| Token | Wert | Verwendung |
|---|---:|---|
| `radius-xs` | 6 px | Badge, kleine Controls |
| `radius-sm` | 10 px | Input, Button |
| `radius-md` | 14 px | Card |
| `radius-lg` | 18 px | Dialog, größere Panels |
| `radius-xl` | 24 px | Onboarding-Container |
| `radius-full` | 999 px | Statuspunkt, Pill |

### 8.2 Schatten

```css
--shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.20);
--shadow-sm: 0 8px 24px rgba(0, 0, 0, 0.18);
--shadow-md: 0 16px 48px rgba(0, 0, 0, 0.24);
--shadow-lg: 0 28px 80px rgba(0, 0, 0, 0.30);
```

- Cards verwenden standardmäßig keinen starken Schatten.
- Tiefe entsteht zuerst durch Oberfläche und Rahmen.
- `shadow-md` und höher nur für Dialoge, Popover und Command-Menüs.
- Keine farbigen Glows.

### 8.3 Blur

| Token | Wert | Einsatz |
|---|---:|---|
| `blur-sm` | 8 px | Sticky Topbar |
| `blur-md` | 16 px | Popover |
| `blur-lg` | 24 px | Dialog-Backdrop |

Blur nur mit ausreichend deckender Hintergrundfläche. Text darf nicht auf unkontrolliertem Bildmaterial liegen.

---

## 9. Motion

### 9.1 Zeiten

| Token | Wert | Verwendung |
|---|---:|---|
| `motion-instant` | 90 ms | Pressed, Checkbox |
| `motion-fast` | 140 ms | Hover, Fokus |
| `motion-base` | 220 ms | Popover, Sidebar |
| `motion-slow` | 360 ms | Dialog, Onboarding-Schritt |

### 9.2 Easing

```css
--ease-standard: cubic-bezier(0.2, 0, 0, 1);
--ease-enter: cubic-bezier(0.16, 1, 0.3, 1);
--ease-exit: cubic-bezier(0.4, 0, 1, 1);
```

### 9.3 Regeln

- Nur `transform` und `opacity` animieren, sofern möglich.
- Keine endlosen Ambient-Animationen in Arbeitsansichten.
- Ladezustände nutzen reduzierte Skeleton-Bewegung.
- Bei `prefers-reduced-motion: reduce` werden Animationen auf 1 ms gesetzt und Parallax-/Slide-Effekte entfernt.
- Statusänderungen dürfen nicht ausschließlich animiert kommuniziert werden.

---

## 10. Fokus und Eingabe

### Fokus-Token

```css
--focus-ring: 0 0 0 2px var(--color-bg-app),
              0 0 0 4px var(--color-focus-ring);
```

### Regeln

- `:focus-visible` wird nie entfernt.
- Fokusreihenfolge folgt der visuellen Reihenfolge.
- Icon-Buttons haben einen zugänglichen Namen.
- Mindestzielgröße: 40 × 40 px, bevorzugt 44 × 44 px auf Touch.
- Fehlertext steht direkt am Feld und wird über `aria-describedby` verbunden.
- Pflichtfelder werden textlich gekennzeichnet.
- Placeholder ersetzt niemals ein Label.

---

## 11. Z-Index

| Token | Wert | Ebene |
|---|---:|---|
| `z-base` | 0 | normale Inhalte |
| `z-sticky` | 100 | Sticky Header |
| `z-dropdown` | 300 | Dropdown und Combobox |
| `z-popover` | 400 | Popover und Tooltip |
| `z-overlay` | 500 | Backdrop |
| `z-modal` | 600 | Dialog |
| `z-toast` | 700 | Toast |
| `z-command` | 800 | globale Command Palette |

Keine willkürlichen Werte wie `99999`.

---

## 12. Statussystem

Jeder Status besteht aus:

1. Symbol
2. Text
3. optionaler Farbe
4. optionaler Erklärung oder Aktion

| Status | Farbe | Beispiel |
|---|---|---|
| Verfügbar | Mint | „Verbunden“ |
| Information | Sky | „Cloud-Anbieter“ |
| Warnung | Amber | „Eingeschränkt“ |
| Fehler | Red | „Authentifizierung fehlgeschlagen“ |
| Neutral | Fog | „Nicht konfiguriert“ |
| Experimentell | Gold | „Lokale CLI-Bridge, experimentell“ |

### Standardisierte Provider-Zustände

- Nicht konfiguriert
- Verfügbar
- Nicht erreichbar
- Zugangsdaten ungültig
- Eingeschränkt
- Nicht unterstützt
- Wird geprüft

Rohdaten wie `authentication_error` dürfen intern bestehen, die UI zeigt verständliche Texte und konkrete Reparaturschritte.

---

## 13. Komponenten

## 13.1 App-Shell

### Sidebar

- 264 px breit, auf Desktop dauerhaft sichtbar
- 80 px kompakter Modus
- Mobile: Drawer mit Modalverhalten
- Logo oben, Hauptnavigation mittig, Systemstatus und Profil unten
- aktive Route: subtile Bay-Fläche, 2-px-Gate-Indikator, `aria-current="page"`
- keine sichtbaren funktionslosen Hauptpunkte
- Gruppen:
  - Arbeiten
  - Ressourcen
  - System
- Textlabels bleiben im normalen Modus sichtbar

### Topbar

- Höhe 64 px
- Seitentitel, Breadcrumb oder Kontext links
- globale Suche beziehungsweise Command Palette
- Status und Profil rechts
- Sticky nur, wenn die Ansicht davon profitiert

## 13.2 Buttons

### Varianten

| Variante | Zweck |
|---|---|
| Primary | genau eine Hauptaktion pro Bereich |
| Secondary | normale Aktion |
| Ghost | Navigation und geringe Priorität |
| Danger | destruktive Aktion |
| Icon | kompakte Werkzeugaktion |

### Größen

| Größe | Höhe |
|---|---:|
| Small | 32 px |
| Medium | 40 px |
| Large | 48 px |

Primary Dark Theme:

```text
Hintergrund: Gate 500
Text: Bay 950
Hover: Gate 400
Pressed: Gate 600
Fokus: Gold-Ring
```

Destruktive Aktionen benötigen bei hohem Schaden eine Bestätigung mit konkretem Objektbezug.

## 13.3 Form Controls

- Höhe standardmäßig 40 px
- Labels oberhalb
- Beschreibung unter Label, Fehler unter Feld
- Inputs auf `surface` mit sichtbarem Rahmen
- Hover verstärkt Rahmen leicht
- Fokus nutzt Gold-Ring
- deaktiviert: Kontrast bleibt lesbar, Cursor und Text erklären Zustand
- Passwort-/API-Key-Felder: anzeigen/verbergen, nie automatisch offenlegen
- Base-URLs und Modell-IDs verwenden optional Monospace

## 13.4 Cards und Panels

### Card

- `surface`-Hintergrund
- 1-px-Standardrahmen
- Radius 14 px
- Padding 20 oder 24 px
- Titel, Meta, Inhalt, Aktionen klar getrennt
- komplette Card nur klickbar, wenn sie genau eine Aktion repräsentiert

### Glass Panel

Nur für Topbar, Popover oder einzelne erhöhte Panels:

```css
background: var(--color-bg-elevated);
backdrop-filter: blur(var(--blur-md));
border: 1px solid var(--color-border-default);
```

Nicht jede Card bekommt Blur. Sonst entsteht der übliche Milchglas-Sumpf, den Software offenbar für Fortschritt hält.

## 13.5 Status Badge

- Höhe mindestens 24 px
- Icon oder Punkt plus Text
- keine rein farbige Kennzeichnung
- maximal drei Wörter
- technische Details in Tooltip oder Detailansicht

## 13.6 `AiModelPicker`

Die zentrale Modellauswahl ist ein zugängliches Combobox-/Command-Menu-Muster.

### Trigger

Zeigt:

- Provider-Icon
- Modellname
- lokal/cloud/bridge
- Verbindungsstatus
- geerbte Auswahl, falls vorhanden
- Dropdown-Indikator

### Menü

1. Suchfeld
2. optional „Workspace-Standard verwenden“
3. Providergruppen
4. Modellzeilen
5. Aktualisieren-Aktion
6. erklärender Fehler- oder Leerzustand

### Modellzeile

- Modellname
- Provider
- Fähigkeitsbadges: Tool Calling, JSON, Vision, Reasoning
- Kontextfenster
- lokal/cloud
- Status
- deaktivierte Modelle mit Erklärung, nicht kommentarlos ausgegraut

### Tastatur

- `ArrowUp` / `ArrowDown`: navigieren
- `Enter`: auswählen
- `Escape`: schließen
- `Home` / `End`: Anfang und Ende
- Suche filtert sofort
- Fokus bleibt nach Auswahl am Trigger

### Nicht zulässig

- stille Fallbacks
- ungeklärte Abkürzungen
- bloßes HTML-`select`
- Modellauswahl nach Namensheuristik statt Fähigkeiten

## 13.7 Provider Card

Enthält:

- Anbietername und Verbindungstyp
- lokal/cloud/bridge
- Status
- Base-URL oder Kontoart, maskiert
- letzte Prüfung
- Fähigkeiten
- Aktionen: Konfigurieren, Testen, Modelle aktualisieren
- Fehler mit Reparaturschritt

Eine experimentelle Subscription-Bridge erhält ein sichtbares „Experimentell“-Label und eine kurze Grenze der Unterstützung.

## 13.8 Onboarding

### Desktop

- zentrierter Container, maximal 1040 px
- linke Spalte: Schritte und Fortschritt
- rechte Spalte: aktueller Inhalt
- persistenter Footer mit Zurück, Überspringen und Weiter

### Mobile

- einspaltig
- kompakter Fortschritt oben
- Footer-Aktionen sticky
- keine horizontalen Stepper

### Verhalten

- jeder Schritt speichert seinen Zustand
- Fortsetzung nach Abbruch
- Fehler blockiert nur, wenn das Abschlusskriterium betroffen ist
- Cloud-, Kosten- und Datenschutzhinweise sind klar, aber nicht alarmistisch
- Abschluss zeigt Systemprüfung als strukturierte Checkliste

## 13.9 Dialoge

- Standardbreite 560 px
- große Workflows maximal 800 px
- Titel, Beschreibung, Inhalt und Footer
- initialer Fokus auf Titel oder erstes sinnvolles Feld
- Fokusfalle und Rückgabe an Auslöser
- `Escape` schließt nicht während irreversibler laufender Aktion
- Destruktiver Dialog nennt Objekt und Auswirkung

## 13.10 Tabellen und Datenraster

- Header bleibt bei langen Tabellen optional sticky
- Zeilenhöhe 44 oder 52 px
- numerische Werte rechtsbündig
- technische IDs monospace
- Sortierung über beschriftete Buttons
- Zeilenaktionen in klarer Menüschaltfläche
- mobile Darstellung priorisiert Spalten oder wechselt zu Karten
- keine horizontale Scrollfalle ohne sichtbaren Hinweis

## 13.11 Logs und technische Ausgaben

- Monospace, mindestens 12 px
- Zeitstempel, Quelle und Level getrennt
- Zeilenumbruch optional
- Kopieraktion
- Filter und Suche
- keine Secrets oder rohe Auth-Daten
- Fehler nicht nur rot, sondern mit Leveltext

## 13.12 Toasts

- Erfolg nur nach abgeschlossener Aktion
- Fehler bleibt lang genug lesbar und bietet Reparatur oder Details
- maximal drei gleichzeitig
- kein Toast für Zustände, die dauerhaft auf der Seite sichtbar sein müssen

---

## 14. Informationsarchitektur

### Hauptnavigation

```text
Übersicht
Neuer Run
Projekte
Datensätze
Vorlagen
Monitoring
```

Nur tatsächlich verfügbare Bereiche werden gezeigt.

### Einstellungen

```text
Profil
KI & Modelle
Embeddings & Daten
Integrationen
Sicherheit & Audit
Erweitert
```

Provider, API-Schlüssel, Modell-Presets und Routing werden als zusammenhängender Workflow unter „KI & Modelle“ organisiert.

---

## 15. Responsive Verhalten

### 320–479 px

- Sidebar als Drawer
- 16 px Seitenabstand
- einspaltige Formulare
- Button-Gruppen umbrechen oder stapeln
- keine Tabelle mit erzwungenem Desktoplayout
- Dialoge füllen fast die Breite
- Model Picker als vollbreites Sheet möglich

### 480–767 px

- Cards einspaltig
- Formgruppen dürfen zweispaltig sein, wenn Labels passen
- Onboarding bleibt einspaltig

### 768–1023 px

- kompakte Navigation oder Drawer
- zweispaltige Dashboards möglich
- Detailpaneele nicht dauerhaft erzwingen

### Ab 1024 px

- permanente Sidebar
- Workbench-Layouts mit Haupt- und Kontextspalte
- Datenansichten nutzen verfügbare Breite bis 1440 px

---

## 16. Inhalt und Sprache

### Ton

- direkt
- sachlich
- verständlich
- keine anthropomorphen KI-Floskeln
- keine unbelegten Erfolgsaussagen

### Gute Beispiele

- „Verbindung testen“
- „Ollama ist unter dieser Adresse nicht erreichbar.“
- „API-Schlüssel ungültig. Prüfe den Schlüssel und die Berechtigungen.“
- „Workspace-Standard: OpenAI / gpt-5.6“
- „10 Personas angefordert, 10 erstellt“

### Schlechte Beispiele

- „Magie wird vorbereitet“
- „Deine KI denkt nach“
- „Ups, etwas ist schiefgegangen“
- „Bald verfügbar“ als dauerhafter Menüpunkt
- „Verbunden“, obwohl nur eine Konfiguration gespeichert wurde

---

## 17. Logo und Markenanwendung

- bevorzugte Kombination: abstraktes Agora-Netzwerkzeichen plus Wortmarke `AGORA`
- Mindestbreite Wortmarke: 96 px
- Icon allein ab 24 px
- Schutzzone: mindestens die Höhe des inneren Icon-Knotens
- auf Bay-Flächen: Fog-Wortmarke, Gate- oder Gold-Akzent
- auf hellen Flächen: Bay-Wortmarke
- monochrome Variante für Favicon, CLI und Dokumentation
- keine Glows, 3D-Effekte oder wechselnden Farbverläufe
- Animation nur beim Start oder in Markenmedien, nicht dauerhaft in der Sidebar
- Reduced Motion zeigt sofort das statische Endbild

---

## 18. CSS- und Komponentenregeln

### Verbindlich

- Tokens zentral in `frontend/src/styles/agora-tokens.css`
- Komponenten verwenden semantische Variablen
- neue Hex-Werte werden im Review beanstandet
- Zustände über `data-state`, `aria-*` oder dokumentierte Varianten
- keine schwergewichtige UI-Bibliothek nur für eine Combobox
- bestehende Komponenten schrittweise migrieren

### Namensschema

```text
--agora-color-*
--agora-space-*
--agora-radius-*
--agora-shadow-*
--agora-motion-*
--agora-z-*
```

### Beispiel

```css
.provider-card {
  color: var(--agora-color-text-primary);
  background: var(--agora-color-bg-surface);
  border: 1px solid var(--agora-color-border-default);
  border-radius: var(--agora-radius-md);
  padding: var(--agora-space-6);
}
```

---

## 19. Migration

### Phase 1: Inventur

- vorhandene Hex-, RGB- und Schattenwerte erfassen
- Komponenten nach Nutzung und Risiko ordnen
- tote Varianten markieren
- visuelle Referenzscreenshots erstellen

### Phase 2: Grundlagen

- Token-Datei einführen
- Theme-Klasse und Systempräferenz anbinden
- Focus-, Motion- und Basis-Typografie definieren
- globale Seitenhintergründe migrieren

### Phase 3: Kernkomponenten

1. Button
2. Input und Select
3. Card und Panel
4. Badge und Status
5. Dialog und Popover
6. App-Shell
7. `AiModelPicker`

### Phase 4: Kernabläufe

1. Onboarding
2. Einstellungen
3. Provider-Verbindungen
4. Embedding-Auswahl
5. Neuer Run

### Phase 5: Datenansichten

- Projekte
- Datensätze
- Vorlagen
- Monitoring
- Reports und Logs

Keine Big-Bang-Umstellung. Alte und neue Komponenten dürfen nur kontrolliert und zeitlich begrenzt parallel existieren.

---

## 20. Qualitätssicherung

### Automatisiert

- Typecheck und Lint
- Komponenten-Tests für Varianten und Zustände
- Tastaturnavigation
- `axe` oder gleichwertige Accessibility-Prüfung
- Playwright-Screenshots für:
  - App-Shell
  - Onboarding
  - Einstellungen
  - `AiModelPicker`
  - Provider Card
  - Fehlerzustand
  - 320 px, 768 px und 1440 px
- Reduced-Motion-Test
- Dark- und Light-Theme

### Manuell

- 200 % Zoom
- reine Tastatur
- Screenreader-Schnellprüfung
- Kontrast
- lange deutsche Texte
- Modell- und Providernamen mit Überlänge
- Offline-, Fehler- und Ladezustände
- mobile Dialoge und Tabellen

---

## 21. Definition of Done für Slice 7

- zentrale Tokens vorhanden
- Dark und Light Theme funktionieren
- App-Shell migriert
- Onboarding migriert
- Einstellungen migriert
- `AiModelPicker` migriert
- keine neuen verstreuten Hex-Werte
- 320 px bis 1536 px geprüft
- WCAG-AA für zentrale Text- und Kontrollpaare
- vollständige Tastaturbedienung
- sichtbare Fokuszustände
- Reduced Motion
- visuelle Regressionen oder dokumentierte Screenshots
- Dokumentation und Handover aktualisiert

---

## 22. Review-Checkliste

- [ ] Wird ein semantisches Token statt eines Hex-Werts verwendet?
- [ ] Ist der Zustand zusätzlich zu Farbe durch Text oder Symbol erkennbar?
- [ ] Funktioniert die Komponente per Tastatur?
- [ ] Ist `:focus-visible` sichtbar?
- [ ] Ist der Name für Screenreader eindeutig?
- [ ] Funktioniert die Komponente bei 320 px?
- [ ] Funktioniert sie bei 200 % Zoom?
- [ ] Sind Lade-, Leer-, Fehler- und deaktivierte Zustände definiert?
- [ ] Respektiert die Animation Reduced Motion?
- [ ] Gibt es keine stillen Fallbacks?
- [ ] Sind lokale, Cloud- und Bridge-Verbindungen klar unterscheidbar?
- [ ] Wurde die visuelle Regression aktualisiert?
