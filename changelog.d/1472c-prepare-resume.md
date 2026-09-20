# Slice 1.4 — Prepare-Interrupted/Resume

Beendet sich der Webprozess während `simulation_prepare` mitten in der
Persona-Generierung, endet die Vorbereitung nicht mehr zwangsläufig als
endgültiges `failed/process_restart` (Slice 1.1). Liegt ein Checkpoint mit
mindestens einem bereits generierten Profil vor, landet der `SimulationState`
stattdessen auf dem neuen Status `interrupted` und bietet einen Resume an:
ein erneuter `prepare`-Aufruf setzt die Persona-Generierung fort statt sie
komplett neu zu starten. Ohne verwertbaren Zwischenstand bleibt es beim
bisherigen `failed` — kein Resume-Angebot ohne Deckung durch echte
Teilergebnisse.

## Der Befund, der den Ansatz bestimmt

Der Graph-Lesepfad für Phase 1 (`prepare_entities.py::_cap_entities_across_types`)
hat kein `ORDER BY` — das steht bereits im Docstring dort. Ein erneuter Read
beim Resume kann deshalb eine andere Typ-Verteilung liefern als der
unterbrochene Versuch: derselbe `max_agents`-Cap wählt dann andere
Vertreter je Typ aus, und Quote/Typ-Mix driften zwischen dem ursprünglichen
und dem fortgesetzten Lauf auseinander. Ein Resume, der Phase 1 einfach
erneut ausführt, würde diesen Fehler exakt reproduzieren.

Der neue Checkpoint (`backend/app/contracts/prepare_checkpoint_contract.py`,
`backend/app/services/prepare_checkpoint.py`) fixiert deshalb die beim
Original-Versuch getroffene Cap-/Quota-Auswahl als Entity-UUID-Listen
(`primary_entity_uuids`, `reserve_entity_uuids`, `expanded_entity_uuids`).
Ein Resume berechnet diese Auswahl **nicht neu** — er liest die fixierten
UUIDs aus dem aktuellen Graphen nur noch nach. Ein Regressionstest
(`backend/tests/services/test_prepare_resume.py`) belegt das direkt: zwei
Läufe mit identischen Parametern, aber unterschiedlicher Knoten-
Lesereihenfolge (simuliert den fehlenden `ORDER BY`), liefern nach dem
Resume exakt dieselbe Generierungsliste wie der ununterbrochene Lauf.

## Warum die Profile per Index, nicht per UUID gecheckpointet werden

Quota-Expansion (`_expand_entities_for_quota`) und der Persona-Floor können
dieselbe Entity mehrfach in die Generierungsliste aufnehmen — jede
Wiederholung bekommt bewusst einen eigenen demografischen Slot
(unterschiedliches Alter, Geschlecht, …). Der Checkpoint schlüsselt
generierte Profile deshalb per Generierungs-Index, nicht per Entity-UUID:
eine UUID-Zuordnung hätte allen Wiederholungen derselben Entity dasselbe
Profil aufgezwungen und die demografische Streuung der Wiederholungen
zerstört.

## Was der Checkpoint bewusst NICHT abdeckt

Checkpointet wird die parallele Hauptgenerierung (`_process_result` in
`oasis_profile_batch.py`, unter demselben Lock wie der Fortschrittszähler).
Die sequenzielle Reject-Backfill-Nachbesetzung (`_backfill_rejected_slots`,
läuft nach der Hauptschleife) checkpointet nicht inkrementell — wird der
Prozess mitten in der Backfill-Phase beendet, generiert ein Resume die
offenen Slots erneut. Das ist eine bewusste Scope-Grenze (Backfill ist
klein gegenüber der Hauptgenerierung), keine Lücke im Kernszenario.

Die finale Namens-Dedup (`generate_profiles_from_entities`, Ende der
Funktion) läuft nach jedem Resume unverändert über die **gesamte**
Profilliste — Checkpoint-Profile tragen ihren Vor-Dedup-Namen (der
Checkpoint-Hook feuert vor der Dedup-Passage), wodurch ein Resume dieselbe
Dedup-Entscheidung trifft wie ein ununterbrochener Lauf mit identischer
Indexreihenfolge.

## FSM

Neuer Status `INTERRUPTED` (`SimulationStatus`): `PREPARING → INTERRUPTED`
bei Unterbrechung mit Checkpoint, `INTERRUPTED → PREPARING` als Retry-Pfad
(symmetrisch zu `FAILED → PREPARING`). `INTERRUPTED` ist kein Terminalzustand.
Der Status ist nicht vertraglich ausgeliefert (`SimulationState.to_dict()`
gibt ihn als losen String zurück, wie alle anderen Statuswerte auch) — kein
Schema-Update nötig.

Sowohl der SIGTERM/atexit-Shutdown-Hook (Slice 1.1,
`simulation_runner.register_cleanup`) als auch die Startup-Reconciliation
für Prozesse ohne ordentlichen Shutdown (`sim/reconciliation.py`) treffen
dieselbe Entscheidung über eine gemeinsame Funktion
(`prepare_checkpoint.resolve_interruption_status`).

## Offen

Die Reject-Backfill-Phase checkpointet nicht inkrementell (siehe oben).
Heartbeat/Lease-Mechanik (Slice 1.5, #1472d) und #1472 als Ganzes (Job-Queue
mit eigenen Out-of-Process-Workern) bleiben offen.
