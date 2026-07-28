# 🏛️ Agora — Vision

> **North-Star, keine Roadmap.** Diese Datei beschreibt das *Warum* und die Langzeitrichtung von Agora. Release-Stufen und ausführbare Kriterien bleiben in [`ROADMAP.md`](ROADMAP.md); der verifizierte Ist-Zustand in [`docs/STATUS.md`](docs/STATUS.md); der Produkteintritt in [`README.md`](README.md). Die Vision ist **nicht bindend für Einzelaufgaben** und enthält keine konkurrierenden Planungsdaten.

---

## These

Komplexe Entscheidungen — Kampagnen, Produkteinführungen, Stakeholder-Kommunikation — scheitern seltener an fehlenden Daten als an ungeprüften Annahmen über die Reaktionen anderer. Agora macht diese Annahmen sichtbar, bevor sie teuer werden: ein strukturierter Probe-Raum, in dem simulierte Zielgruppen und Stakeholder auf Dokumente und Entwürfe reagieren — mit Evidenzbindung, Confidence-Bewertung und ausgewiesenen Datenlücken statt glatter Behauptungen.

## Das Problem

- **Bestätigungsfehler:** Teams testen Botschaften gegen die eigene Blase.
- **Polarisierung unsichtbar:** Konfliktlinien zwischen DACH-Zielgruppen werden erst im Rollout spürbar.
- **Evidenzlose Aussagen:** Marketing- und Strategieaussagen halten einer Quellenprüfung nicht stand.
- **Kosten echter Marktforschung:** qualitative Interviews sind teuer, spät und selten iterativ.

Agora ersetzt keine echte Marktforschung. Es ist das billige, schnelle Vorspiel davor — um Hypothesen zu schärfen und gezielt in echte Befragungen, Tests und Fachreviews zu investieren.

## Was Agora ist

- Ein **Probe-Raum** für mögliche Reaktionen (Pre-Mortem, Varianten-Vergleich).
- **Evidenzorientiert:** jede Aussage im Report bindet sich an Graph-Evidenz mit Confidence und Provenance ([ADR-0002](docs/decisions/0002-evidence-gating.md), [ADR-0011](docs/decisions/0011-evidence-entailment-and-provenance.md)).
- **Single-User & kontrolliert:** lokal oder hybrid betreibbar, keine öffentliche Multi-Tenant-SaaS vor `1.0.0`.
- **DACH-fokussiert:** Tonalitäten, Personas und Sprache auf den deutschsprachigen Raum abgestimmt.
- **Eine kanonische Wahrheit:** ein produktives Frontend, eine Provider-/Routing-Registry, eine Contract-Ebene.

## Was Agora nicht ist

- **Keine Zukunftsvorhersage.** „Confidence" bewertet die interne Evidenzbindung im Graph, keine Welt-Wahrheit.
- **Kein Ersatz** für echte Interviews, Nutzertests oder Fachreviews.
- **Kein statistisch belastbares Sample** pro Einzellauf — belastbare Aussagen brauchen mehrere Varianten, Seeds und Reviews.
- **Kein öffentliches SaaS**, kein Team- oder Rollenmodell vor `1.0.0`.

## Grundprinzipien (nicht verhandelbar)

1. **Evidenz-Ehrlichkeit.** Keine dekorativen Fallbacks, keine abgeschwächten Assertions, keine Zukunftsvorhersagen. Datenlücken werden ausgewiesen, nicht geschönt. (ADR-0002-Hartanker.)
2. **Reproduzierbarkeit vor Features.** Ein Run muss mit Eingangs-Hash, Graph-Version, Modellen, Provider-/Routing-Snapshot, Prompt-Versionen und Seeds nachvollziehbar und wiederholbar sein.
3. **Single-User-Kontrolle.** Daten, Secrets und Modelle bleiben unter der Hoheit einer Person. Kein ungeschützter Internet-Betrieb.
4. **Eine kanonische Oberfläche und eine kanonische Provider-Wahrheit.** Keine parallelen Picker, Frontends oder lokalen Detection-Heuristiken.
5. **Verträge zuerst, Consumer danach.** Pydantic v2 als Single Source of Truth, Frontend-Spiegel generiert.

## Nordstern

> **Der reproduzierbare, evidenzehrliche Referenzlauf.**

Ein einzelner, vollständig nachvollziehbarer Lauf — vom Quelldokument über Graph, Personas und Simulation bis zum Report —, der gegen eine Single-Prompt-Baseline einen *messbaren* Mehrwert zeigt, mit kalibrierter Confidence und veröffentlichten Grenzen. Alles auf dem Weg zu `1.0.0` dient diesem Nordstern.

## Langzeitrichtung (nach `1.0.0`, nicht zugesagt)

- Team- und Rollenmodell
- Plugin-System und Branchenvorlagen
- Kubernetes/Helm und Federation mehrerer Instanzen
- optionale gehostete Betriebsmodelle

Diese Pfade erhalten erst nach dem stabilen Single-User-Release eigene Problemstatements und Architekturentscheidungen. Sie sind Vision, kein Versprechen.

## Bezüge

- Release-Stufen und Freigabekriterien: [`ROADMAP.md`](ROADMAP.md)
- verifizierter Ist-Zustand: [`docs/STATUS.md`](docs/STATUS.md)
- Produkteinstieg und Grenzen: [`README.md`](README.md)
- Architekturentscheidungen: [`docs/decisions/`](docs/decisions/)

---

*Entstanden aus MiroFish-Offline, grundlegend weiterentwickelt für professionelle DACH-Simulationen. Entwickelt von [Alexander Schneider](https://alexle135.de).*