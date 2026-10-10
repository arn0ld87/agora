---
name: gsd-agora-run-quality
description: Triagiert Agora-Laufartefakte, plant und behebt Persona-, Simulations- und Berichtsfehler als GitHub-Epic mit GSD-Verifikation und stageweisem Modellvergleich.
---

# Agora Run-Qualität

Verwende diesen Skill für die Diagnose und Beseitigung zusammenhängender Qualitätsfehler eines Agora-Laufs. Er ersetzt keinen allgemeinen GSD-Projektstart. Antworte auf Deutsch. Lies [references/case-1831.md](references/case-1831.md) nur für den Hollerau-Referenzfall; der kopierbare Startauftrag steht in [references/execution-prompt.md](references/execution-prompt.md).

## Eingang und Grenzen

Erfasse Repository, Host, Projekt-/Simulations-/Report-ID, Deployment-SHA, aktuelle Arbeitsbasis und autorisierten Umfang. Fehlende IDs aus jüngsten Artefakten ermitteln. Unterscheide aktuelle Konfiguration von historischen Route-/Prompt-Snapshots. Konfiguration ist kein Beweis, welches Modell eine frühere Stage tatsächlich ausgeführt hat.

Originalartefakte lesend sichern; Inputs/Prompts/Outputs mit Hashes und tatsächlichen Stage-Routen dokumentieren. Secrets, vollständige Umgebungen und Auth-Dateien nicht in Auditmaterial kopieren. Keine Originalruns umschreiben, keine Stage-Overrides still ändern. Paid Evals nur innerhalb eines vorhandenen oder konkret freigegebenen Kostenrahmens starten; fehlt er, Harness und Reviewmaterial fertigstellen und Kostenrahmen als offene Ausführungsvoraussetzung ausweisen.

## 1. Epic und Triage

Vor Neuanlage verwandte offene Issues/PRs suchen. Existierendes Epic aktualisieren, andernfalls innerhalb des Userauftrags anlegen; Child-Issues mit Parent, Abhängigkeiten und überprüfbarer Abnahme verknüpfen. Bestehende Aufgaben wiederverwenden statt duplizieren.

Für jeden Befund festhalten: Priorität, Nutzerwirkung, Reproduktion, Artefaktbeleg, Codepfad, Ursache oder Hypothese, Gegenbeleg, Fix-Scope, Regression und Status. Zulässige Belegurteile: `PASS`, `FAIL`, `NICHT BELEGT`, `NICHT BETROFFEN`. Niedrige Aktivität oder fehlender Dissens ist zunächst eine Beobachtung, kein bewiesener Defekt.

Trenne diese Fehlerklassen:

- **Betrieb/Transport:** Session, Schreibrechte, Mount, Timeout, Providerstart. Ein nicht gestartetes Modell erhält keinen Qualitäts-Score.
- **Vertrag/Verarbeitung:** abgewiesene freie Outline, Ersatzschema, verlorenes Replyziel, falsche Status-/Fehlerpersistenz.
- **Prompt/Kontext:** verbindliche Zufallsdemografie, überschriebene Quellenrolle, abgeschnittener Feed, vorgegebene Konfliktentwicklung.
- **Modellqualität:** erst nach Isolation obiger Confounds beurteilbar.

Rechtefehler zuerst lokalisieren, nicht durch pauschale Freigaben oder Modellwechsel verdecken. Quellenfehler nicht allein aus einer Namensanzeige schließen: Quell-UUID, Profil, komprimierte Runtime-Agent-ID und DB-Autor gemeinsam prüfen.

## 2. GSD-Planung

Entdecke die tatsächlich installierten GSD-Skills/Workflows; lies die passenden Einstiegspunkte für Plan, Execute und Verify. Keine erfundenen Slash-Commands, Phasennummern oder Runtimepfade. Bestehenden GSD-State/ROADMAP verwenden und keine unabhängige Produktplanung überschreiben. Falls noch kein GSD-State existiert, den Epic-Scope mit dem unterstützten Import-/Milestone-Workflow anbinden; keine vollständige Neuplanung des Produkts erzwingen. Ohne ausführbare GSD-Runtime dieselben Artefakte/Prüfrollen erstellen und die Einschränkung ausdrücklich nennen.

Pro atomarem Slice ein ausführbares `PLAN.md` mit Goal, Requirements/Issue, Abhängigkeiten, owned files, konkreten Tasks, Verifikation und `must_haves`. Der erste Slice muss den Fehler bis zum persistierten Nutzerzustand beheben. Planprüfung vor Code; offene Blocker korrigieren. Autorisierte eigene Routineentscheidungen dokumentieren, keine erneute Freigabe für bereits beauftragte Arbeit einholen.

Bevorzugte Reihenfolge: ehrlicher Outline-/Fehlerpfad → betriebsfähige Report-Route → Quellenidentität → Dialog-/Kontextmechanik → vergleichbare Stage-Evals → neuer Referenzlauf. Unabhängige Slices können parallel laufen, wenn Dateieigentum und GSD-Isolation geklärt sind.

## 3. Fachliche Invarianten

- **Persona:** Quellenname, belegte aktuelle Funktion und Kollektivstatus bewahren. Erfundenes Alter/Beruf darf Quellenfakten nicht ersetzen. Synthetische Ergänzung ausdrücklich von Quellenperson unterscheiden. Gleiche Domäne bedeutet nicht gleiche Rolle. Aliase fachlich prüfen, nicht bloß ähnliche Namen verschmelzen.
- **Simulation:** CREATE_POST und verschachtelte Replies im tatsächlich aktiven Pfad prüfen. Original-ID und Runtime-ID unterscheiden. Stimmen nicht aus Likes ableiten. Bezugnahme, Rollenunterschiede, neue Argumente und semantische Wiederholung messen; keine Mindestquoten für Streit, Posts oder Positionswechsel erzwingen.
- **Outline:** Modell plant aus Fragestellung und verfügbaren Daten. Exakte Titel nur bei expliziter Nutzervorgabe; Presets höchstens Orientierung. Nichtleere eindeutige Titel, sinnvolle Begrenzung und inhaltliche Vollständigkeit weiter validieren. Keine feste Ersatzgliederung bei Provider-/Planungsfehlern. Originalursache persistieren; `planning_complete` erst nach validierter erfolgreicher Planung. Historische Fallbacks lesbar halten und beim Resume neu planen.
- **Bericht:** Quellenfakten, vorgegebene Seeds, neue Simulationsbeobachtungen und Interviews trennen. Inhalts-/Evidence-Gates und ADR-0002-Hartanker erhalten. Keine erfundenen Top-10-Listen oder zwingenden Koalitionen. Nutzbaren Inhalt und ehrlichen Status gemeinsam verifizieren.

## 4. Ausführen und prüfen

Repository-Regeln haben Vorrang: eigener Branch/Worktree, Contracts-first, Regression pro Verhaltensfix, passende Schema-/Test-Gates, Changelog-Fragment und STATUS-Synchronisation; Upgrade-Runbook bei Persistenz/Env/Compose. Keine fremden Änderungen zurücksetzen. Pro Slice `SUMMARY.md` und `VERIFICATION.md` mit Commit, ausgeführten Checks, Ergebnissen und Grenzen; nach lokalem Commit unabhängiges Issue-Review gemäß Repository-Routing. Keine Auto-Fix-Schleife oder abgeschwächten Tests.

Epic-Checks erst abhaken, wenn die jeweilige Abnahme belegt ist. PRs verknüpfen; Tests oder ein Merge allein ersetzen den Live-Nachweis nicht. Deployment/Merge nach vorhandener Autorisierung behandeln, nicht aus einer Skill-Invocation pauschal ableiten.

## 5. Modellvergleich

Jeweils nur das Modell einer Stage variieren: Persona, Simulation, Outline, Abschnittsgenerierung. Vergleiche Luna mit einer nachweislich verfügbaren stärkeren Route. Identische Quellen/Snapshots, System-/Userprompts, Verträge, Feeds, Tools, Aktivierungsplan und vergleichbare Output-/Kontextbudgets; Reasoning-Aufwand explizit erfassen. Unterschiedlicher Transport ist eine zusätzliche Variable und muss als solche ausgewiesen werden. GSD-Agentmodell nicht mit Agora-Produktmodell verwechseln.

Mindestens drei Wiederholungen je kritischer Bedingung sind ein Pilot, keine statistische Kalibrierung. Verblindete Paarbewertung mit dokumentierter Rubrik und deterministischen Contract-/Identitätschecks verbinden. Rohoutputs, Fehlerklassen, Token, Kosten und Latenz erhalten. Quellenidentität, Rollenplausibilität, korrekte Zahlen, gültige Bezugnahmen, Neuheitswert, gültige Evidence und Antwort auf die Fragestellung bewerten. Eine Single-Prompt-/Persona-Baseline ohne Simulation auf denselben Quellen mitführen; erwartete Antworten dürfen nicht in Modellinputs gelangen.

Urteil je Stage: ausreichend, bedingt ausreichend, ungeeignet für den geprüften Scope oder `NICHT BELEGT`. Keine Aussage „Luna generell zu schwach“ aus einem Lauf; keine Umschaltung ohne nachvollziehbare Verbesserung.

## Abschluss

Berichte knapp Epic-/PR-Links, behobene versus offene Ursachen, Test-/Live-Nachweis und Stage-Modellurteil. Bei einer externen Voraussetzung präzise benennen, was vorbereitet wurde und was noch nicht ausgeführt ist. Keinen Abschluss behaupten, solange erforderliche Abnahme fehlt.
