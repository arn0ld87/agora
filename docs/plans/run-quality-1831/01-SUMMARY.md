# Slice 01 — Modellgeplante Outline (#1832)

## Problem und Änderung

Die bisherige Planung erzwang feste Titel im Prompt, Contract und Workflow. Bei Providerfehlern lieferte sie eine englische Ersatzgliederung, die der Workflow als fehlenden Pflichtsatz verwarf und dennoch als abgeschlossene Planung loggte.

Der Fix erlaubt freie fragestellungsbezogene Titel, validiert Struktur und normalisierte Eindeutigkeit, hält explizite Titelvorgaben ein und propagiert Planungsfehler zum bestehenden FAILED-Handler. Inhaltliche Vollständigkeit, Evidence-Gates und Budgetabbruch bleiben erhalten. Historische Fallback-Outlines werden beim Resume neu geplant, gültige freie Outlines wiederverwendet. Frontend und generierte Schemas spiegeln den Vertrag.

## Betrieb getrennt vom Produktfix

Auf gns3 wurde ausschließlich der nicht geheime Mountpfad AGORA_CODEX_HOME von dem leeren root-owned /home/schneider-Verzeichnis auf /home/alex/.local/share/agora/codex korrigiert. Vor Recreation waren keine Simulations-/Reportjobs aktiv. Container gesund; readiness meldet binary_present=True, credentials=ok, ready=True. Ein echter isolierter codex_cli-Aufruf mit gpt-6-astra antwortete OK. Historische Laufartefakte wurden nicht umgeschrieben. Der Produktfix ist damit noch nicht auf gns3 ausgerollt.

## Offene Abnahme des Epics

Persona-Identitätsfehler (#1833), weitere Betriebs-/neuer Reportnachweis (#1834), Dialog-/Kontextpfad (#1835) und kontrollierte Stage-Evaluation (#1836) bleiben offen. Der Berichtfehler dieses Runs ist kein Nachweis gegen gpt-6-luna.
