# Slice 01 — Modellgeplante Outline (#1832)

## Problem und Änderung

Die bisherige Planung erzwang feste Titel im Prompt, Contract und Workflow. Bei Providerfehlern lieferte sie eine englische Ersatzgliederung, die der Workflow als fehlenden Pflichtsatz verwarf und dennoch als abgeschlossene Planung loggte.

Der Fix erlaubt freie fragestellungsbezogene Titel, validiert Struktur und normalisierte Eindeutigkeit, hält explizite Titelvorgaben ein und propagiert Planungsfehler zum bestehenden FAILED-Handler. Inhaltliche Vollständigkeit, Evidence-Gates und Budgetabbruch bleiben erhalten. Historische Fallback-Outlines werden beim Resume neu geplant, gültige freie Outlines wiederverwendet. Frontend und generierte Schemas spiegeln den Vertrag.

## Betrieb getrennt vom Produktfix

Auf gns3 wurde ausschließlich der nicht geheime Mountpfad AGORA_CODEX_HOME von dem leeren root-owned /home/schneider-Verzeichnis auf /home/alex/.local/share/agora/codex korrigiert. Vor Recreation waren keine Simulations-/Reportjobs aktiv. Container gesund; readiness meldet binary_present=True, credentials=ok, ready=True. Ein echter isolierter codex_cli-Aufruf mit gpt-6-astra antwortete OK. Historische Laufartefakte wurden nicht umgeschrieben. Der Produktfix ist damit noch nicht auf gns3 ausgerollt.

## Offene Abnahme des Epics

Persona-Identitätsfehler (#1833), weitere Betriebs-/neuer Reportnachweis (#1834), Dialog-/Kontextpfad (#1835) und kontrollierte Stage-Evaluation (#1836) bleiben offen. Der Berichtfehler dieses Runs ist kein Nachweis gegen gpt-6-luna.

## Nachbesserung nach dem Review (2026-10-10)

Das Review zu PR #1838 (Codex) fand zwei Lücken im ersten Schnitt. Beide sind im selben PR nachgebessert:

- **Stabile Abschnitts-Semantik statt Titel-Matching.** Freie Titel brachen die Semantik-Erkennung nachgelagerter Consumer (`_section_schema_for`, `_section_expects_quotes`): strukturierte ReportV3-Felder wären leer geblieben, die Persona-Zitatprüfung wäre übersprungen worden. Der Outline-Vertrag trägt jetzt `ReportSectionKind` (`section_kind` am Abschnitt); DTO-Auswahl und Zitat-Validierung lesen den Kind, der Titel bleibt frei. Der Plan-Prompt wählt den Kind aus einer festen Liste (Test hält Prompt und Enum synchron). Bestandsdaten ohne Kind fallen in `section_kinds.py` auf die historische Preset-/Keyword-Heuristik zurück — exakt das Verhalten vor #1832. Regressionstests: `backend/tests/services/report_agent/test_section_kinds.py`.
- **Titel-Untergrenze vereinheitlicht.** Der erste Schnitt erlaubte Outline-Titel ab einem Zeichen, während `ReportSectionModel.section_title` weiter mindestens drei verlangt — ein Modelloutput wie „KI" wäre gültig geplant und später in der Evidenz-Persistenz FAILED geworden. Der Outline-Vertrag fordert jetzt ebenfalls mindestens drei Zeichen (Backend, Zod-Spiegel, generierte Schemas).
- **Alt-Test aktualisiert.** `test_plan_outline_falls_back_after_two_failures` erwartete noch die entfernte Ersatzgliederung; er asserted jetzt die Fehlerpropagation inklusive Retry-Zählung.
