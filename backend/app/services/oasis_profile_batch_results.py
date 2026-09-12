"""Implementation helpers extracted from OasisProfileGenerator.

The public compatibility surface remains app.services.oasis_profile_generator.
"""

from __future__ import annotations

from typing import Any

from . import oasis_profile_generator as _legacy
from typing import List, Optional
from .entity_reader import EntityNode
from .oasis_profile_models import OasisAgentProfile, PersonaIneligible
from .run_budget import BudgetExceededError

def _backfill_rejected_slots (
self: Any ,
*,
profiles :List [Optional [OasisAgentProfile ]],
entities :List [EntityNode ],
reserve_entities :List [EntityNode ],
use_llm :bool ,
rejected :List ["PersonaIneligible"],
)->None :
    """Besetzt abgelehnte Persona-Slots aus dem Reservepool nach (#1247).

    Der Eignungsfilter ueber die Blockliste laeuft vor dem ``max_agents``-Cap
    und ist damit unproblematisch. Die typunabhaengige Pruefung faellt aber
    erst im Generierungsaufruf, also *nach* dem Cap — eine Ablehnung dort
    liess den Platz bisher ersatzlos leer.

    Sequentiell und nicht parallel: die Reserve ist klein (die Differenz
    zwischen Kandidatenpool und Cap), und jeder Nachrücker kann selbst
    abgelehnt werden, was einen weiteren Zug aus derselben Liste erfordert.
    Ein Parallelisieren brauchte eine Koordination, die den Aufwand nicht
    rechtfertigt.

    Mutiert ``profiles`` **und** ``entities`` in place. Beides ist noetig:
    ``_phase_generate_profiles`` reicht seine Entity-Liste an
    ``SimulationConfigGenerator.generate_config`` weiter. Ohne den Tausch
    bekaeme das nachbesetzte Profil den ``AgentConfig`` und die
    Initial-Post-Klassifikation der abgelehnten Entitaet — eine
    Honorarkraft liefe dann mit UUID, Name, Typ und Aktivitaetsprofil von
    Moodle (CodeRabbit PR #1258).
    """
    slot_types ={
    idx :(entity .get_entity_type ()or "Entity")
    for idx ,entity in enumerate (entities )
    }
    open_slots =[idx for idx ,profile in enumerate (profiles )if profile is None ]
    if not open_slots :
        return

    reserve_slots =self ._build_demographic_slots (reserve_entities )
    used :set [int ]=set ()
    filled =0

    def _next_candidate (preferred_type :Optional [str ])->Optional [int ]:
        """Naechster unverbrauchter Reserve-Index, Typgleichheit bevorzugt.

        Issue #1247 (CodeRabbit PR #1258): Ohne Typpraeferenz verbraucht die
        Nachbesetzung stur den naechsten Eintrag. Gehoert der einer anderen
        Rollenfamilie, faellt ein aktiver ``PersonaQuotaPlan`` anschliessend
        durch ``_validate_persona_quota`` — und auch ohne Plan verschwindet
        die Typvertretung, die das Round-Robin des Caps gerade gesichert
        hat, obwohl weiter hinten ein gleichartiger Kandidat steht.
        """
        if preferred_type :
            for idx ,entity in enumerate (reserve_entities ):
                if idx in used :
                    continue
                if (entity .get_entity_type ()or "Entity")==preferred_type :
                    return idx
        for idx in range (len (reserve_entities )):
            if idx not in used :
                return idx
        return None

    for slot_idx in open_slots :
        preferred =slot_types .get (slot_idx )if slot_types else None
        while True :
            reserve_index =_next_candidate (preferred )
            if reserve_index is None :
                break
            candidate =reserve_entities [reserve_index ]
            candidate_slot =reserve_slots [reserve_index ]
            used .add (reserve_index )
            try :
                profiles [slot_idx ]=self .generate_profile_from_entity (
                entity =candidate ,
                user_id =slot_idx ,
                use_llm =use_llm ,
                demographic_slot =candidate_slot ,
                )
            except PersonaIneligible as rejection :
                rejected .append (rejection )
                continue
            except BudgetExceededError :
            # Ausnahme von "Nachruecker duerfen den Lauf nicht kippen":
            # ein erschoepftes Hartbudget soll ihn genau das.
                raise
            except Exception as exc :# noqa: BLE001 — Nachrücker duerfen den Lauf nicht kippen
                _legacy .logger .warning (
                "Nachbesetzung fuer Slot %d fehlgeschlagen (%s): %r",
                slot_idx ,
                candidate .name ,
                exc ,
                )
                continue
                # Die Entity am selben Index mittauschen, damit die
                # Config-Generierung den Nachruecker beschreibt und nicht die
                # abgelehnte Entitaet.
            if slot_idx <len (entities ):
                entities [slot_idx ]=candidate
            filled +=1
            break

    _legacy .logger .info (
    "Persona-Eligibility: %d Kandidat(en) abgelehnt, %d von %d freien "
    "Plaetzen aus der Reserve nachbesetzt (Reserve: %d Kandidaten). "
    "Abgelehnt: %s",
    len (rejected ),
    filled ,
    len (open_slots ),
    len (reserve_entities ),
    ", ".join (f"{r .entity_name } ({r .entity_type })"for r in rejected [:10 ]),
    )


def _consume_gevent_results (
self: Any ,pool ,worker_wrapper ,entities ,process_result ,completed_count ,total
)->bool :
    """Issue B2: Gevent-Verbrauchsschleife, ausgelagert wegen radon-Gate.

    Rueckgabe True, wenn der Nutzer abgebrochen hat. Gevent kennt keine
    Trennung "nur Wartende abbrechen" wie
    ThreadPoolExecutor.shutdown(cancel_futures=True) — pool.kill()
    beendet auch bereits laufende Greenlets. Groeberer Schnitt als im
    Thread-Pfad, aber der einzige verfuegbare Weg, neue LLM-Calls
    sofort zu stoppen (best effort).
    """
    cancel_requested =False
    # Der ``imap_unordered``-Produzent ist selbst ein Greenlet und *kein*
    # Pool-Mitglied. ``pool.kill()`` allein stoppt ihn deshalb nicht: er legt
    # sofort das naechste Greenlet in den frei gewordenen Pool-Slot. Der
    # Produzent wird darum als Erstes gestoppt, erst danach der Pool.
    results =pool .imap_unordered (worker_wrapper ,enumerate (entities ))

    def _stop_pool ()->None :
        results .kill ()
        pool .kill ()

    # Consume results inside try/finally so the pool is joined on success
    # and on exceptions — no orphaned greenlets outlive the loop.
    try :
        for result_idx ,profile ,error in results :
            process_result (result_idx ,profile ,error )
            if self ._cancel_checkpoint (completed_count [0 ],total ,"gevent"):
                cancel_requested =True
                _stop_pool ()
                break
    except BudgetExceededError :
    # Hartes Budget: wartende Greenlets duerfen keinen weiteren LLM-Call
    # mehr starten. Ohne diesen Stopp liefen sie im ``finally``-``join()``
    # weiter — und ueberlebten den Funktionsaustritt sogar, weil der
    # Produzent den Pool waehrend des Joins immer wieder nachfuellte.
    # Kein Retry: das Budget ist erschoepft, nicht gestoert.
        _stop_pool ()
        raise
    finally :
        pool .join ()
    return cancel_requested


def _consume_thread_results (
self: Any ,generate_single_profile ,entities ,parallel_count ,process_result ,completed_count ,total
)->bool :
    """Issue B2: Thread-Verbrauchsschleife, ausgelagert wegen radon-Gate.

    Rueckgabe True, wenn der Nutzer abgebrochen hat. Bereits laufende
    Persona-Generierungen duerfen auslaufen — das ist akzeptiert.
    shutdown(cancel_futures=True) verwirft nur Futures, die noch nicht
    gestartet sind; angelaufene Worker schreiben ihr Ergebnis fertig
    (der with-Block wartet beim Verlassen darauf, s.
    ThreadPoolExecutor.__exit__ -> shutdown(wait=True)).

    Consume as_completed futures *inside* the with block so the executor
    is not shut down before results are processed — otherwise real-time
    progress and incremental file writes regress to 0% until the slowest
    persona completes.
    """
    import concurrent .futures

    cancel_requested =False
    with concurrent .futures .ThreadPoolExecutor (max_workers =parallel_count )as executor :
        future_to_entity ={
        executor .submit (generate_single_profile ,idx ,entity ):(idx ,entity )
        for idx ,entity in enumerate (entities )
        }

        for future in concurrent .futures .as_completed (future_to_entity ):
            idx ,entity =future_to_entity [future ]
            entity_type =entity .get_entity_type ()or "Entity"
            try :
                result_idx ,profile ,error =future .result ()
            except BudgetExceededError :
            # Hartes Budget: noch nicht gestartete Futures verwerfen, bevor
            # der Fehler den ``with``-Block verlaesst. ``__exit__`` ruft
            # ``shutdown(wait=True)`` *ohne* ``cancel_futures`` — jede
            # eingereihte Persona haette sonst trotzdem ihre LLM-Calls
            # abgesetzt. Bereits laufende Worker duerfen wie bisher
            # auslaufen (bestehende Semantik), kein Retry.
                executor .shutdown (wait =False ,cancel_futures =True )
                raise
            except Exception as e :# noqa: BLE001
                _legacy .logger .error (f"Thread execution failed unexpectedly for entity {entity .name }: {str (e )}")
                profile =OasisAgentProfile (
                user_id =idx ,
                user_name =self ._generate_username (entity .name ),
                name =entity .name ,
                bio =f"{entity_type }: {entity .name }",
                persona =entity .summary or "A participant in social discussions.",
                source_entity_uuid =entity .uuid ,
                source_entity_type =entity_type ,
                )
                result_idx ,error =idx ,str (e )
            process_result (result_idx ,profile ,error )
            if self ._cancel_checkpoint (completed_count [0 ],total ,"Thread-Pfad"):
                cancel_requested =True
                executor .shutdown (wait =False ,cancel_futures =True )
                break
    return cancel_requested


def _cancel_checkpoint (self: Any ,completed :int ,total :int ,path :str )->bool :
    """Issue B2: prueft das kooperative Cancel-Flag und loggt den Abbruch.

    Buendelt den identischen Check aus Gevent- und Thread-Pfad, damit
    ``generate_profiles_from_entities`` unter der radon-Allowlist-
    Obergrenze bleibt (cc<=40) — die Funktion ist ein Bestands-Hotspot,
    der nicht weiter wachsen darf.
    """
    from .sim .cancel_flag import is_cancel_requested

    if not (self .run_id and is_cancel_requested (self .run_id )):
        return False
    _legacy .logger .info (
    "Persona-Generierung kooperativ abgebrochen (%s): "
    "run_id=%s, %d/%d Personas fertig",
    path ,self .run_id ,completed ,total ,
    )
    return True
