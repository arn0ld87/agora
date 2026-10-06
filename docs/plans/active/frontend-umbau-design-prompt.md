# Gestaltungsauftrag für Claude Design: Agora-Frontend

Stand 2026-10-05. Gehört zu [`frontend-umbau.md`](frontend-umbau.md) (Etappe 0).

Der Auftrag läuft in **zwei Durchgängen**. Durchgang 2 wird erst gestartet, wenn der Maintainer Durchgang 1 abgenommen hat. Jeder Durchgang ist ein eigener, vollständiger Prompt; der Text zwischen den Linien wird unverändert übergeben.

Anhänge für beide Durchgänge:

- die drei Screenshots von „Screens 5" (Bibliothek, Einstellungen) als Vorbild für Aufbau und Ruhe,
- die Screenshots des heutigen Agora (Ablage, Simulation, Live-Feed) als Beispiel dafür, was abgelöst wird,
- für Durchgang 2 zusätzlich die abgenommenen Entwürfe aus Durchgang 1.

---

## Durchgang 1: Bildsprache, Hülle, Bibliothek, Lauf-Übersicht

---

Du gestaltest die Oberfläche von **Agora** neu. In diesem ersten Durchgang legst du die Bildsprache fest und zeigst sie an drei Ansichten. Bitte entwirf noch nichts darüber hinaus; die übrigen Ansichten folgen in einem zweiten Auftrag, sobald diese drei abgenommen sind.

### Was Agora ist

Agora ist eine Analyse-Anwendung für eine einzelne Person, die am Schreibtisch am großen Bildschirm arbeitet. Sie lädt Dokumente zu einer strittigen Entscheidung hoch, etwa die Schließung eines Kreißsaals. Agora baut daraus einen Wissensgraphen, erzeugt synthetische Personas der Beteiligten (Hebammen, Kreistag, Klinikleitung, Bürgerinitiative), lässt sie in einer simulierten Twitter- und Reddit-Umgebung diskutieren und schreibt am Ende einen Bericht, in dem jede Aussage mit Belegen verknüpft ist.

Wichtig für den Ton der Gestaltung: Agora sagt kein menschliches Verhalten vorher. Alles, was Personas äußern, ist eine synthetische Modellausgabe. Die Oberfläche soll nüchtern und prüfbar wirken, wie ein gutes Arbeitswerkzeug, und nicht wie ein Orakel oder ein Marketing-Dashboard.

### Die Begriffe

Bitte verwende genau diese deutschen Begriffe und keine Synonyme:

- **Lauf**: ein vollständiges Vorhaben von der Quelle bis zum Bericht. Das Hauptobjekt der Anwendung.
- **Graph**: das aus den Dokumenten gewonnene Wissensnetz aus Entitäten und Beziehungen.
- **Personasatz**: eine Sammlung synthetischer Personas.
- **Bericht**: das lesbare Ergebnis eines Laufs. Ein Lauf kann mehrere Fassungen haben.
- **Job**: ein einzelner technischer Arbeitsschritt. Erscheint nur am Rand.

Die gesamte Oberfläche ist deutsch, mit korrekten Umlauten.

### Die Bildsprache

Vorbild ist die Mac-App „Screens 5" in den angehängten Bildern. Übernimm ihre Ruhe und ihren Aufbau, nicht ihr Aussehen im Detail; Agora soll danach eigenständig wirken und in einem Browser laufen, nicht wie eine Kopie aussehen.

- **Flächen:** neutrales Graphit ohne Braunstich in drei Helligkeitsstufen für Seitenleiste, Inhalt und Karte. Bereiche trennen sich durch Flächen und Abstand. Linien nur in Tabellen und Listen. Das heutige Agora rahmt Kästen in Kästen; das soll verschwinden.
- **Akzent:** genau eine Akzentfarbe, ein Violett, für Auswahl, Hauptknopf und Verknüpfungen. Sie wird nie für Zustände benutzt.
- **Zustandsfarben:** Grün, Gelb und Rot gehören allein den Zuständen. Im heutigen Agora ist Orange zugleich Markenfarbe und Warnfarbe, sodass ein gewöhnlicher Knopf wie eine Warnung aussieht. Diese Verwechslung ist der Hauptgrund für die getrennte Akzentfarbe.
- **Schrift:** eine serifenlose Systemschrift für die Bedienung. Festbreitenschrift nur für Kennungen, Protokoll und Code. Keine Schreibmaschinen-Etiketten mit Nummern.
- **Formen:** weiche Radien (Karten etwa 12, Felder etwa 8), runde farbige Symbolplaketten in Listen wie in den Screens-5-Einstellungen, Schalter für An/Aus.
- **Hell und Dunkel:** beide Varianten, gleichwertig. Die Anwendung folgt der Systemeinstellung.
- **Dichte:** Entwirf in der Stufe „Komfort". Eine Stufe „Kompakt" existiert als Einstellung; zeig sie einmal an der Listenansicht.
- **Barrierefreiheit:** Kontraste nach WCAG 2.1 AA, sichtbarer Tastaturfokus, kein Zustand, der nur über Farbe erkennbar ist (immer zusätzlich Symbol oder Wort).

### Die Hülle

Sie umgibt jede Ansicht.

**Seitenleiste**, schmal, einklappbar auf Symbole, mit Gruppenüberschriften und Zählern:

```
Bibliothek
  Läufe                 9
  Graphen               3
  Personasätze          2
Im Blick
  Läuft gerade          0
  Braucht dich          2
Werkzeuge
  Vergleich
  Aktivität            42
──────────────────────────
● System        Einstellungen
```

Der Punkt vor „System" zeigt den Zustand der Dienste.

**Werkzeugleiste** oben: Brotkrumen, Suche mit Tastenkürzel ⌘K, Hauptknopf „Neuer Lauf", Umschalter Kacheln/Liste und Sortierung, ein Knopf für die Konsole mit Zähler, Profilmenü.

**Konsole:** ein Auszug am unteren Rand, den man von jeder Seite aufziehen kann, um die Meldungen des Servers zu beobachten. Zeig sie in einem Bild geschlossen (nur der Knopf) und in einem aufgezogen, mit Filter nach Stufe (Fehler, Warnung, Info), Suche und Pause.

### Ansicht 1: Bibliothek → Läufe (Startseite)

Die erste Ansicht nach dem Öffnen. Läufe als Kachelraster.

Eine **Lauf-Kachel** zeigt:

- die Frage des Laufs als Titel, zweizeilig, nie abgeschnitten,
- die Quelle,
- fünf kleine Stufenpunkte mit Zustand: Graph, Personas, Simulation, Bericht, Interviews,
- Datum und Kosten,
- bei laufenden Läufen die Runde und den Fortschritt,
- bei gestoppten oder fehlgeschlagenen den Grund in einem Satz.

Über den Kacheln ein schmales Band **„Im Blick"**, das nur erscheint, wenn etwas läuft oder Aufmerksamkeit braucht.

Bitte zeig diese Zustände an je einer Kachel, klar unterscheidbar:

| Zustand | Bedeutung |
|---|---|
| läuft | Simulation in Runde 11 von 24 |
| fertig | alle Stufen abgeschlossen |
| **unvollständig** | ein Bericht ist lesbar, aber Abschnitte fehlen |
| gestoppt | vom Nutzer angehalten |
| Budget erschöpft | Kostengrenze erreicht |
| fehlgeschlagen | mit Grund |

„Unvollständig" darf nie wie „fertig" aussehen. Es ist ein eigener, sichtbarer Zustand und kein Erfolg mit Fußnote.

Inhalte für die Kacheln (echte Daten aus einem Beispiel-Lauf):

- Frage: „Welche Risiken entstehen für Schwangere, Beschäftigte und die Versorgung im Südkreis, wenn der Kreistag die Schließung des Kreißsaals Brenkhausen beschließt?"
- Quelle: `seed-3-geburtshilfe-hollerau.md`
- weitere Läufe mit derselben Quelle und anderen Zuständen, dazu ein Lauf mit der Quelle `seed_document.md` und dem Zustand „fehlgeschlagen".

Zusätzlich: dieselbe Ansicht als **Liste**, der **Leerzustand** (noch kein Lauf) und ein **Ladezustand**.

### Ansicht 2: Lauf → Übersicht

Ein geöffneter Lauf ist ein Arbeitsbereich mit sechs festen Reitern:

```
Übersicht · Graph · Personas · Simulation · Bericht · Interviews
```

Jeder Reiter trägt seinen Zustand als kleine Marke. Reiter ohne Inhalt sind anklickbar.

Die Übersicht zeigt eine Zeile je Stufe mit: Zustand, verwendetem Modell, Dauer, Tokens, Kosten und genau einem Knopf für den nächsten sinnvollen Schritt (Starten, Fortsetzen, Ansehen, „Neu erzeugen mit …"). Vor dem Start einer Stufe ist das Modell an dieser Stelle änderbar; es soll deutlich als Stellschraube erkennbar sein, nicht als unscheinbares Etikett.

Darunter: der Budgetstand des Laufs (Zeit, Tokens, Kosten, Aufrufe, jeweils verbraucht von erlaubt), die Frage, und zwei Karten für den verknüpften Graphen und Personasatz.

Zeig den Lauf in zwei Zuständen: einmal mitten in der Simulation, einmal abgeschlossen mit dem Bericht im Zustand „unvollständig" und einer Persona-Stufe, die auf Ersatz-Personas zurückfallen musste. Solche Rückfälle sind Qualitätsminderungen und müssen in der Zeile sichtbar sein.

### Ansicht 3: Dialog „Neuer Lauf"

Ein Dialog mit fünf Gruppen, kein mehrstufiger Assistent:

1. **Frage** (Pflichtfeld) und optional die Streitfrage.
2. **Graph:** vorhandenen wählen, neu aus einer Quelle anlegen (Datei ablegen) oder ohne Graph.
3. **Personasatz:** vorhandenen wählen oder erzeugen lassen.
4. **Modelle:** ein Profil wählen, etwa „Sparsam", „Ausgewogen", „Gründlich". Darunter aufklappbar „je Stufe anpassen" mit vier Zeilen (Graph, Personas, Simulation, Bericht) und einer groben Kostenangabe je Stufe. Zeig den Dialog einmal zugeklappt und einmal aufgeklappt.
5. **Umfang und Budget:** Tage, Runden, Grenzen für Zeit, Tokens, Kosten und Aufrufe, dazu eine Vorabschätzung.

Zwei Knöpfe: „Starten" und „Nur anlegen".

### Was ich von dir bekomme

1. **Ein Bausteinblatt:** Farben für Hell und Dunkel mit Namen und Werten, Schriftgrößen, Abstände, Radien, Schatten; Knöpfe in allen Zuständen; Eingabefeld, Auswahl, Schalter, Segmentwahl; Reiter; Kachel und Listenzeile; Zustandsmarken für alle sechs Laufzustände; die Marken „SIM", „manuell", „Fallback" und „Interview"; Hinweisband; Leerzustand; Dialog.
2. **Ansicht 1** in Dunkel und Hell, dazu Liste, Leer- und Ladezustand.
3. **Ansicht 2** in Dunkel, in beiden beschriebenen Zuständen.
4. **Ansicht 3** in Dunkel, zu- und aufgeklappt.
5. **Die Hülle** mit eingeklappter Seitenleiste und mit aufgezogener Konsole.

Entwirf für eine Breite von 1440 Pixeln und zeig Ansicht 1 zusätzlich bei 1024 Pixeln. Ein Telefon-Layout ist nicht nötig.

Wenn dir beim Entwerfen eine Stelle auffällt, an der die beschriebene Struktur nicht aufgeht, gestalte sie so, wie du es für richtig hältst, und schreib einen Satz dazu, was du geändert hast und warum.

---

## Durchgang 2: Kernstrecke als klickbarer Prototyp und Einzelansichten

Erst nach Abnahme von Durchgang 1 übergeben. Die abgenommenen Entwürfe und das Bausteinblatt werden angehängt.

---

Du setzt die Gestaltung von **Agora** fort. Bildsprache, Hülle, Bibliothek, Lauf-Übersicht und der Dialog „Neuer Lauf" sind abgenommen und hängen an; halte dich an das Bausteinblatt und erfinde keine zweite Variante eines vorhandenen Bausteins. Fehlt dir ein Baustein, ergänze ihn im Blatt.

Zur Erinnerung, worum es geht: Agora lässt synthetische Personas über eine strittige Entscheidung diskutieren und schreibt daraus einen Bericht, in dem jede Aussage mit Belegen verknüpft ist. Der eigentliche Wert liegt in dieser Prüfbarkeit. Das größte Problem der heutigen Oberfläche ist, dass die Teile nicht miteinander verbunden sind: Vom Bericht kommt man nicht zum Beitrag, auf den er sich stützt, und der Graph ist nach seiner Erstellung nicht mehr erreichbar. Deine Entwürfe sollen genau diese Verbindungen spürbar machen.

Drei Regeln gelten in jeder Ansicht:

- Jede synthetische Äußerung (Beitrag, Kommentar, Interview-Antwort, Zitat im Bericht) trägt die Marke **„SIM"**.
- Qualitätsminderungen sind sichtbar: „unvollständig", Ersatz-Personas („Fallback") und von Hand geänderte Graph-Einträge („manuell") werden nie wie der Normalfall dargestellt.
- Keine Formulierung, die Vorhersage verspricht. Agora zeigt plausible Reaktionen, keine Prognosen.

### Teil A: klickbarer Prototyp der Kernstrecke

Ein durchklickbarer Ablauf mit echten Inhalten aus dem Beispiel-Lauf zur Geburtshilfe in Hollerau:

**Bibliothek → Lauf öffnen → Übersicht → Graph → Simulation (Feed, einen Faden öffnen) → Bericht (Claim anklicken, Beleg erscheint rechts, Sprung zum Beitrag im Feed)**

#### A1: Lauf → Graph

Drei Spalten. Links Suche, Filter nach Typ mit Zählern (Person, Organisation, Ort, …) und die Entitätenliste. In der Mitte der Graph mit einem Umschalter **Netz | Tabelle**. Rechts die Detailspalte zur gewählten Entität: Name, Typ, Aliase, Beschreibung, Beziehungen, Herkunft (Dokument und Abschnitt).

Im Lauf ist der Graph nur lesbar. Im Kopf stehen Name, Quelle, Zahl der Entitäten und Beziehungen, der Zustand „gesperrt, verwendet von 2 Läufen" und die Knöpfe „In Bibliothek öffnen" und „Duplizieren und bearbeiten".

Entitäten für das Beispiel: Kliniken Hollerau gGmbH, Kreißsaal Brenkhausen, Hollerau-Nord, Kreistag, Geschäftsführung, Hebammenverband, Anke Wübbena (Sprecherin der freiberuflichen Hebammen), Dr. Birgit Sander, Betriebsrat Kliniken Hollerau, Rettungsdienst des Landkreises, Initiative „Kreißsaal bleibt in Brenkhausen", Landesministerium, CDU, Moorhagen.

#### A2: Lauf → Simulation → Feed

Unterreiter **Feed · Runden · Diagnose**. Der Feed hat drei Spalten und zeigt **ein Netzwerk zur Zeit**:

- links der Umschalter Twitter | Reddit und Filter nach Persona, Runde und Streitfrage,
- in der Mitte die Zeitleiste,
- rechts die Karte der gerade gewählten Persona (Rolle, Haltung, Knopf „Befragen") und die Aktivität je Runde.

Oben ein Rundenregler: live mitlaufen oder nach dem Lauf Runde für Runde zurückgehen.

Die beiden Netzwerke sollen so aufgebaut sein, wie man es von ihnen kennt, damit man ohne Erklärung versteht, wer wem antwortet:

- **Twitter:** einspaltige Zeitleiste. Beitragskarte mit Avatar, Name, Zeit, Text und Zählern für Antworten, Weiterleitungen und Zustimmung. Ein Klick öffnet die **Faden-Ansicht**: der Beitrag oben, darunter die Antworten mit Verbindungslinie.
- **Reddit:** Beitragsliste mit Stimmenzahl und Kommentarzahl. Ein Klick öffnet den Beitrag mit eingerücktem, einklappbarem Kommentarbaum.

Übernimm den vertrauten Aufbau, aber keine Marken, Logos oder Farben der echten Plattformen; es sind simulierte Räume, und sie sollen wie ein Teil von Agora aussehen.

Beispielinhalte:

- Geschäftsführung: „Beschlussvorlage: Die Geschäftsführung der Kliniken Hollerau gGmbH schlägt vor, die Geburtshilfe in Brenkhausen zum 30. Juni 2027 zu schließen und in Hollerau-Nord zu bündeln. Grund: unbesetzte Hebammenstellen, 23 Tage Kreißsaal-Schließung 2025 und ein Defizit von 1,9 Mio. €."
- Anke Wübbena, als Antwort darauf: „Als Sprecherin der freiberuflichen Hebammengruppe im Südkreis kann ich diesen Beschlussvorschlag nicht unwidersprochen stehen lassen. Die 23 Tage Kreißsaal-Schließung sind eine direkte Folge unbesetzter Stellen und mangelnder Kooperationsbereitschaft mit uns freiberuflichen Kolleginnen."
- Hebammenverband: „Wir lehnen die Schließung ab, solange das Land nicht über einen Sicherstellungszuschlag entschieden hat."
- Rettungsdienst des Landkreises: „Die Fahrzeit von Moorhagen nach Hollerau-Nord liegt bei 52 Minuten, bei Glätte bis zu 72 Minuten, deutlich über dem Richtwert von 40 Minuten."
- CDU: „Wir tragen die Bündelung mit, wenn das Land einen Sicherstellungszuschlag zahlt und Brenkhausen so dauerhaft gesichert werden kann."
- Dr. Birgit Sander: „Mit Kinderklinik im Haus ist die Versorgung von Risikogeburten in Hollerau-Nord sicherer."
- Initiative „Kreißsaal bleibt in Brenkhausen": „6.400 Unterschriften, 900 Teilnehmende bei der Demonstration."

Zusätzlich als Einzelbilder: der Feed vor dem Start (Leerzustand mit Erklärung, Modell und Startknopf), der Unterreiter **Runden** und der Unterreiter **Diagnose** (Protokoll der Werkzeugaufrufe und Fehler dieses Laufs, gleiche Komponente wie die Konsole).

#### A3: Lauf → Bericht

Drei Spalten:

- **links die Gliederung** mit Zustand je Abschnitt (fertig, mit Mängeln, fehlt) und zwei eigenen Einträgen „Hypothesen" und „Datenlücken" mit Zähler,
- **in der Mitte der Bericht** als ruhiges Lesedokument in Lesebreite. Hier, und nur hier, darf eine Leseschrift mit Serifen und großzügiger Zeilenhöhe stehen, weil es ein Dokument ist und kein Bedienfeld. Einzelne Aussagen (Claims) sind dezent markiert und tragen eine kleine Marke für die Belastbarkeit (hoch, mittel, niedrig). Zitate von Personas stehen als Karte mit „SIM".
- **rechts die Belegspalte:** Ein Klick auf einen Claim zeigt seine Belege, gruppiert nach Art (Dokument, Graph, Simulation, Interview), jeder mit einem Sprung an den Ursprung: zur Stelle im Dokument, zur Kante im Graph-Reiter, zum Beitrag im Feed.

Im Kopf: die Frage, ein Fassungswähler („Fassung 3, 05.10., Modell …"), der Zustand, „Neu erzeugen mit …" und Export.

Ist der Bericht unvollständig, steht oben ein **Hinweisband** mit der Liste dessen, was fehlt. Kein kleines Etikett.

Drei Dinge müssen im Text klar unterscheidbar sein, weil sie fachlich verschieden sind: ein **Claim** (belegte Aussage), eine **Hypothese** (plausibel, aber nicht ausreichend belegt) und eine **Datenlücke** (die Quellen enthalten die nötige Information nicht).

Zusätzlich als Einzelbild: die Druck- und Exportfassung, nur die Mitte, Belege als Fußnoten. Und der Bericht in Hell.

### Teil B: Einzelansichten

#### B1: Lauf → Interviews

Drei Spalten: links die Liste der Gespräche und „Neues Gespräch", in der Mitte das Gespräch, rechts die Persona-Karte mit ihren Beiträgen im Feed und den Stellen, an denen der Bericht sie zitiert.

Zwei Arten: Einzelgespräch und Gruppenfrage (dieselbe Frage an mehrere Personas, Antworten nebeneinander). Jede Antwort trägt „SIM" und „Interview" und sieht anders aus als ein Beitrag im Feed, denn ein Interview ist eine nachträgliche Befragung und war nie Teil der Diskussion. Am Eingabefeld stehen das Modell und ein Kostenhinweis.

#### B2: Bibliothek → Graphen und der Graph-Editor

Die Bibliotheksansicht mit Kacheln je Graph (Name, Quelle, Zahl der Entitäten und Beziehungen, verwendet in n Läufen, Zustand bearbeitbar oder gesperrt).

Dann der geöffnete Graph im **Tabellenmodus** und bearbeitbar: Reiter Entitäten | Beziehungen, sortierbar, Mehrfachauswahl mit den Aktionen „Zusammenführen" und „Löschen", Knöpfe „+ Entität" und „+ Beziehung", Bearbeiten in der Detailspalte. Zeig zwei Dubletten („Kreistag" und „Der Kreistag") ausgewählt mit der Aktion „Zusammenführen".

Von Hand angelegte oder geänderte Einträge tragen die Marke **„manuell"** und in der Herkunftszeile „manuell, Datum". Im Netz sind manuelle Kanten gestrichelt. Zeig das einmal im Netzmodus.

Ein Graph ist nur bearbeitbar, solange kein Lauf darauf gestartet wurde. Zeig den gesperrten Zustand mit der Erklärung und dem Knopf „Duplizieren".

#### B3: Bibliothek → Personasätze und der Persona-Editor

Die Bibliotheksansicht mit Kacheln je Satz. Dann ein geöffneter Satz als Raster aus Persona-Karten: Avatar, Name, Rolle, Haltung in einem Satz, Art (Einzelperson oder Kollektiv), Freigabestatus und eine Herkunftsmarke: aus Graph erzeugt, von Hand, KI-Entwurf oder **Fallback**. Filter nach Typ, Haltung, Freigabe und Herkunft.

Der **Editor** ist ein Fenster im Aufbau der Screens-5-Einstellungen: links die Abschnitte Identität, Haltung und Ziele, Sprache und Ton, Aktivität, Bezug zum Graphen; rechts gruppierte Felder.

KI-Hilfe an drei Stellen: „Entwurf aus Stichworten" (ein Feld für zwei Sätze, daraus entsteht ein Vorschlag für alle Felder), „Feld vorschlagen" an einzelnen Feldern und „Aus Entität ableiten". Jeder Vorschlag ist erkennbar ein Entwurf, den man annimmt oder verwirft. Am Knopf stehen Modell und Kostenhinweis.

Unten im Editor ein Beispielbeitrag in der Stimme der Persona, mit „SIM" markiert.

#### B4: Einstellungsfenster

Ein Fenster über der Anwendung, links Symbolliste mit farbigen runden Plaketten, rechts gruppierte Zeilen mit Schaltern und Auswahlfeldern, wie in den Screens-5-Einstellungen. Neun Abschnitte:

Allgemein · Aussehen · Anbieter · Profile · Embedding · Pipeline · Budgets · Zugang · System

Ausgestaltet werden drei:

- **Anbieter:** je KI-Anbieter eine Karte mit Verbindung, Zustand, hinterlegtem Schlüssel (nie im Klartext, nur Länge und Anfang) und den verfügbaren Modellen.
- **Profile:** eine Liste der Modell-Profile, eines als Standard markiert. Ein geöffnetes Profil zeigt vier Zeilen (Graph, Personas, Simulation, Bericht) mit je einer Modellwahl.
- **System:** Zustand von Neo4j, Redis und PostgreSQL, die Version und ein Sprung zur Konsole.

Für die übrigen sechs genügt die Symbolliste.

#### B5: Werkzeuge → Aktivität

Zwei Reiter: **Jobs** (Tabelle mit Art, Lauf, Zustand, Dauer, Abbrechen) und **Protokoll** (die Konsole in voller Größe).

#### B6: Zustände

Je ein Bild für: einen Fehlerzustand mit verständlicher Ursache und einem Ausweg; einen Ladezustand in einer Dreispalter-Ansicht; den Graph-Reiter eines Laufs, der ohne Graph angelegt wurde (eine Erklärung, kein Fehler).

### Was ich von dir bekomme

1. Den klickbaren Prototyp der Kernstrecke aus Teil A in Dunkel.
2. Die Einzelbilder aus Teil A und Teil B in Dunkel; den Bericht zusätzlich in Hell.
3. Das ergänzte Bausteinblatt mit allem, was neu hinzugekommen ist: Beitragskarte Twitter, Beitragskarte Reddit, Kommentar im Baum, Persona-Karte, Claim-Marke, Beleg-Eintrag, Gesprächsblase Interview, Graph-Knoten und -Kante (belegt und manuell), Rundenregler.
4. Eine kurze Liste der Stellen, an denen du von dieser Beschreibung abgewichen bist, mit je einem Satz Begründung.

Breite 1440 Pixel. Die Dreispalter zusätzlich bei 1024 Pixeln, mit einem Vorschlag, welche Spalte dort einklappt.

---

## Abnahme durch den Maintainer

Nach Durchgang 1:

- Ist auf einen Blick erkennbar, welcher Lauf läuft, fertig ist, unvollständig ist oder Aufmerksamkeit braucht?
- Sieht ein gewöhnlicher Knopf nie wie eine Warnung aus?
- Ist das Modell je Stufe als Stellschraube erkennbar?
- Wirkt es ruhig, ohne leer zu sein?

Nach Durchgang 2:

- Vom Claim zum Beitrag: höchstens zwei Klicks, und man landet an der richtigen Stelle?
- Versteht man im Feed ohne Erklärung, wer wem antwortet?
- Sind Feed-Beitrag und Interview-Antwort nicht zu verwechseln?
- Sind „SIM", „manuell", „Fallback" und „unvollständig" überall da, wo sie hingehören?

Die abgenommenen Entwürfe werden zur Vorlage für die Etappen 1 bis 8 in [`frontend-umbau.md`](frontend-umbau.md). Das Bausteinblatt wird in Etappe 1 zu den Tokens in `frontend/src/assets/styles/`.
