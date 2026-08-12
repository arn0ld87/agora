# KI-Azubi-Match Dortmund — Machbarkeitsstudie

## 1. Ausgangslage

Die Industrie- und Handelskammer (IHK) Dortmund meldet für das Ausbildungsjahr 2025/2026
insgesamt **2.847 unbesetzte Ausbildungsplätze** bei **1.203 registrierten Bewerbern**,
die noch keinen Vertrag haben. Das entspricht einer **Passungsquote von lediglich 38 %**.
Besonders betroffen sind die Branchen Gastgewerbe (412 unbesetzte Plätze), Einzelhandel
(338) und IT/Softwareentwicklung (291). Auf Bewerberseite konzentrieren sich die
meisten unversorgten Jugendlichen auf die kaufmännischen Berufe (487) und die
Lagerlogistik (312).

Die Stadt Dortmund fördert seit 2023 das Programm „Ausbildungsoffensive 2025" mit einem
jährlichen Budget von **1,8 Mio. EUR**. Zusätzlich stellt das Land NRW **450.000 EUR**
für Digitalisierungsprojekte in der Berufsorientierung bereit.

## 2. Der Vorschlag: KI-Azubi-Match

Die Stabsstelle Digitalisierung der Stadt Dortmund (Leitung: Dr. Sarah Kling, 42 J.,
zuvor CDO der Stadt Köln) schlägt ein KI-gestütztes Matching-Portal vor. Kernidee:

- Bewerber erstellen ein **Kompetenzprofil** über einen Chatbot (schulische Leistungen,
  Praktika, Soft Skills, räumliche Präferenz)
- Betriebe hinterlegen **Anforderungsprofile** mit bis zu 20 Kriterien
- Ein **GPT-basierter Matching-Algorithmus** berechnet Ähnlichkeitsscores
- Das System schlägt beidseitig die **Top-5-Matches** vor
- Die IHK moderiert den Prozess und stellt **Ausbildungscoaches**

Geplante Kosten: **320.000 EUR** einmalige Entwicklung, **95.000 EUR** jährlicher
Betrieb (Hosting, Wartung, Support). Zielquote: **Steigerung der Passungsquote auf 65 %
innerhalb von 3 Jahren**.

## 3. Stakeholder und Positionen

### 3.1 IHK Dortmund (Hauptgeschäftsführer Thomas Bergmann, 58 J.)

Befürwortet das Projekt grundsätzlich, fordert aber:

- Rechtsverbindliche **Datenschutz-Folgenabschätzung** vor Produktivstart
- Klärung der **Haftungsfrage** bei Fehlvermittlung („Wer haftet, wenn ein Bewerber
  aufgrund eines Algorithmus-Fehlers keinen Platz bekommt?")
- Integration in bestehende **IHK-Lehrstellenbörse** statt Parallelsystem
- Kostenbeteiligung der Stadt an den Coach-Stellen (3 VZÄ, je 65.000 EUR/Jahr)

Die IHK verweist auf eine Pilotstudie aus Stuttgart, wo ein ähnliches Portal die
Passungsquote um 11 Prozentpunkte steigerte, aber die **Abbruchquote um 7 % stieg**,
weil schwächer gematchte Bewerber früher aufgaben.

### 3.2 Stabsstelle Digitalisierung (Dr. Sarah Kling)

Dr. Kling argumentiert mit **Effizienzgewinnen**:

- „Ein Algorithmus kann in Sekunden das, wofür ein Berufsberater 45 Minuten braucht."
- Verweist auf das **österreichische AMS-Algorithmus-Projekt** (2019–2023), das zwar
  wegen Diskriminierungskritik eingestellt wurde, aber technisch valide Ergebnisse lieferte
- Schlägt externes **Bias-Audit** durch das „Algorithmenethik-Lab" der TU Dortmund vor
- Betont die **Skalierbarkeit**: Das System könne nach erfolgreichem Pilot auf ganz NRW
  übertragen werden

### 3.3 TU Dortmund — Lehrstuhl für Wirtschaftsinformatik (Prof. Dr. Markus Jensen, 45 J.)

Begleitet die Studie wissenschaftlich und liefert kritische Einordnung:

- „Die Aussagekraft von KI-basierten Matching-Scores ist stark von der Datenqualität
  abhängig. In einer Stichprobe von 50 Testprofilen ergaben sich bei 17 % der Fälle
  abweichende Ergebnisse, je nachdem ob der Bewerber sein Profil allein oder mit Hilfe
  erstellt hatte."
- Warnt vor **Automation Bias**: „Berufsberater neigen dazu, KI-Vorschläge ungeprüft zu
  übernehmen, wenn das System in 8 von 10 Fällen richtig liegt."
- Empfiehlt ein **zweistufiges Modell**: KI-Vorauswahl → menschliche Validierung

### 3.4 Dortmund Digital e. V. (Verein der Dortmunder Digitalwirtschaft, 47 Mitgliedsunternehmen)

Vorsitzende Elena Richter (36 J., CTO der codecultur GmbH) unterstützt, fordert aber:

- **Open-Source-Entwicklung** statt proprietärer Lösung („Sonst binden wir uns an einen
  Anbieter")
- **Datensouveränität**: Bewerber sollen ihre Daten löschen können (DSGVO-konform)
- Einbindung der **Ausbildungsbetriebe in die Testphase** („Wir wollen das System sehen,
  bevor wir unsere Anforderungsprofile eingeben")
- Keine **automatische Zuordnung**: Höchstens Vorschläge, keine Zuweisung

### 3.5 DGB-Jugend Dortmund (Jessica Nowak, 24 J., Gewerkschaftssekretärin)

Ablehnend bis skeptisch:

- „Schon jetzt werden benachteiligte Jugendliche systematisch aussortiert. Ein Algorithmus
  macht das nur schlimmer."
- Verweist auf Studien, wonach KI-Systeme bei gleicher Qualifikation **Bewerber mit
  türkischem Namen** seltener vorselektieren (um 23 % geringere Chance bei automatisierten
  Vorauswahlen)
- Fordert **Moratorium** bis zu einer unabhängigen Diskriminierungsprüfung
- Alternative: **48 zusätzliche Berufsberater** statt KI (Kosten: ca. 2,4 Mio. EUR/Jahr)
  und Ausbau der **ausbildungsbegleitenden Hilfen** (abH)

### 3.6 Berufskolleg 1 der Stadt Dortmund (Oberstudiendirektorin Martina Fuchs, 54 J.)

Sieht **Chancen und Risiken**:

- „Unsere Schülerinnen und Schüler haben sehr unterschiedliche digitale Kompetenzen.
  Ein reiner Chatbot-Zugang würde weniger privilegierte Jugendliche ausschließen."
- Fordert **mehrsprachigen Zugang** (Türkisch, Arabisch, Ukrainisch, Polnisch)
- Bietet an, das System im **Berufsorientierungsunterricht** der 12. Klassen zu testen
  (ca. 380 SuS pro Jahrgang)
- Möchte aber ein **Opt-out** für Schüler ohne Smartphone/Internetzugang zu Hause
  (laut eigener Erhebung haben 14 % der Schüler keinen ausreichenden Internetzugang)

## 4. Rechtliche Rahmenbedingungen

- **DSGVO**: Verarbeitung von Bewerberdaten (Noten, Gesundheitsdaten bei Schwerbehinderung,
  Migrationshintergrund) erfordert Rechtsgrundlage nach Art. 6 und 9 DSGVO
- **AGG**: Das Allgemeine Gleichbehandlungsgesetz verbietet Diskriminierung nach Alter,
  Herkunft, Geschlecht, Behinderung, Religion oder Weltanschauung — genau die Merkmale,
  die ein Algorithmus systematisch auswerten würde
- **BDSG**: § 37 BDSG regelt automatisierte Einzelentscheidungen
- **Berufsbildungsgesetz (BBiG)**: Die IHK ist für die Vermittlung nicht zuständig,
  nur für die Beratung — die Rechtsgrundlage für ein Matching-Portal müsste geschaffen werden

## 5. Internationale Erfahrungen

| Land | System | Ergebnis |
|---|---|---|
| Österreich | AMS-Algorithmus | 2023 eingestellt nach Diskriminierungsklage |
| Schweiz | NAVI (ZH) | 15 % höhere Passungsquote, 3 % höhere Abbruchquote |
| Niederlande | MijnKompas | 22 % höhere Vermittlungsquote, aber hohe Kosten (€ 1,2 Mio) |
| Dänemark | UddannelsesMatch | 18 % bessere Passung, von Gewerkschaften akzeptiert |

Schlüsselfaktor für Akzeptanz war in allen Fällen die **Transparenz des Algorithmus**
und die **Möglichkeit der manuellen Korrektur** durch Berater.

## 6. Zeitplan (geplant)

| Phase | Zeitraum | Meilenstein |
|---|---|---|
| Machbarkeitsstudie | Q2/2026 | Vorliegen dieser Studie |
| Prototypentwicklung | Q3/2026 – Q1/2027 | Funktionsfähiger Demo-Client |
| Pilotphase (3 Monate) | Q2/2027 – Q3/2027 | Test mit 20 Betrieben, 100 Bewerbern |
| Evaluierung | Q4/2027 | Entscheidung über Rollout |
| Produktivbetrieb | Q1/2028 (geplant) | Vollbetrieb |

## 7. Kritische Erfolgsfaktoren

- **Datenschutz** muss von Anfang an mitgedacht werden (Privacy by Design)
- **Bias-Prüfung** vor jedem Release
- **Transparenz** gegenüber Bewerbern (Recht auf Erklärung eines Matchings)
- **Menschliche Kontrolle** in jedem Vermittlungsschritt
- **Finanzierung** über die Pilotphase hinaus muss vor Produktivstart geklärt sein

---

*Dieses Dokument wurde erstellt von der Stabsstelle Digitalisierung der Stadt Dortmund,
Stand: 15.06.2026. Es dient als Grundlage für die Stakeholder-Analyse im Agora-Framework.*
