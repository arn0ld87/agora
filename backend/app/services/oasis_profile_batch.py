"""Implementation helpers extracted from OasisProfileGenerator.

The public compatibility surface remains app.services.oasis_profile_generator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import oasis_profile_generator as _legacy

if TYPE_CHECKING:
    from .degradation_collector import DegradationCollector
import json
from typing import List, Optional
from .entity_reader import EntityNode
from .oasis_profile_models import OasisAgentProfile, PersonaIneligible
from .run_budget import BudgetExceededError
from .settings_layer import get_default_service as _get_settings

def generate_profiles_from_entities (
self: Any ,
entities :List [EntityNode ],
use_llm :bool =True ,
progress_callback :Optional [callable ]=None ,
graph_id :Optional [str ]=None ,
parallel_count :Optional [int ]=None ,
realtime_output_path :Optional [str ]=None ,
output_platform :str ="reddit",
degradations :Optional ["DegradationCollector"]=None ,
reserve_entities :Optional [List [EntityNode ]]=None ,
)->List [OasisAgentProfile ]:
    """
    Generate Agent Profiles in batch from entities (supports parallel generation)

    Args:
        entities: Entity list
        use_llm: Whether to use LLM to generate detailed personas
        progress_callback: Progress callback function (current, total, message)
        graph_id: Knowledge graph ID for knowledge graph search to get richer context
        parallel_count: Number of parallel LLM-Roundtrips. If None, falls back to
            env ``AGORA_PARALLEL_PERSONA_COUNT`` (default 10). Cloud-LLM-Setups
            (Ollama-Bridge gegen gemini-3-flash, qwen3-coder:cloud usw.) vertragen
            10–15 parallele Requests; lokales Ollama sollte auf 3–5 reduziert werden,
            um KV-Cache-Trashing zu vermeiden.
        realtime_output_path: Real-time output file path (if provided, write after each generation)
        output_platform: Output platform format ("reddit" or "twitter")
        degradations: optionaler Sammler für stille Teilausfälle
            (Issue #1029). Gemeldet wird einmal am Ende, mit der Anzahl
            der Platzhalterprofile — nicht pro Persona.

    Returns:
        List of Agent Profiles
    """
    from threading import Lock


    if parallel_count is None :
        parallel_count =int (
        _get_settings ().effective_value ('AGORA_PARALLEL_PERSONA_COUNT')
        )

        # Set graph_id for knowledge graph search
    if graph_id :
        self .graph_id =graph_id

    total =len (entities )
    profiles =[None ]*total # Pre-allocate list to maintain order
    completed_count =[0 ]# Use list for modification in closure
    lock =Lock ()
    demographic_slots =self ._build_demographic_slots (entities )
    # Issue #1247: abgelehnte Kandidaten, gesammelt fuer die Nachbesetzung.
    rejected :List [PersonaIneligible ]=[]

    # Helper function for real-time file writing
    def save_profiles_realtime ():
        """Real-time save generated profiles to file"""
        if not realtime_output_path :
            return

        with lock :
        # Filter generated profiles
            existing_profiles =[p for p in profiles if p is not None ]
            if not existing_profiles :
                return

            try :
                if output_platform =="reddit":
                # Reddit JSON format
                    profiles_data =[p .to_reddit_format ()for p in existing_profiles ]
                    with open (realtime_output_path ,'w',encoding ='utf-8')as f :
                        json .dump (profiles_data ,f ,ensure_ascii =False ,indent =2 )
                else :
                # Twitter CSV format
                    import csv
                    profiles_data =[p .to_twitter_format ()for p in existing_profiles ]
                    if profiles_data :
                    # Issue #1246 (CodeRabbit PR #1257): Spaltenmenge
                    # ueber ALLE Profile vereinigen. ``to_twitter_format``
                    # laesst nicht gesetzte Felder weg, und Kollektive
                    # haben garantiert kein Alter, Geschlecht oder MBTI.
                    # War das erste fertige Profil ein Kollektiv, warf
                    # jedes spaetere Individualprofil
                    # "dict contains fields not in fieldnames" — der
                    # Fehler wurde unten geschluckt und die
                    # Realtime-Datei blieb ab da veraltet.
                        fieldnames :List [str ]=[]
                        for row in profiles_data :
                            for key in row :
                                if key not in fieldnames :
                                    fieldnames .append (key )
                        with open (realtime_output_path ,'w',encoding ='utf-8',newline ='')as f :
                            writer =csv .DictWriter (f ,fieldnames =fieldnames ,restval ="")
                            writer .writeheader ()
                            writer .writerows (profiles_data )
            except Exception as e :# noqa: BLE001 — exception is logged; swallowed intentionally
                _legacy .logger .warning (f"Real-time profile save failed: {e }")

    def generate_single_profile (idx :int ,entity :EntityNode )->tuple :
        """Worker function to generate single profile"""
        entity_type =entity .get_entity_type ()or "Entity"

        try :
            profile =self .generate_profile_from_entity (
            entity =entity ,
            user_id =idx ,
            use_llm =use_llm ,
            demographic_slot =demographic_slots [idx ],
            )

            # Real-time output generated persona to console and log
            self ._print_generated_profile (entity .name ,entity_type ,profile )

            return idx ,profile ,None

        except PersonaIneligible as rejection :
        # Issue #1247: Ablehnung ist kein Fehlschlag. Der Slot bleibt
        # leer und wird aus dem Reservepool nachbesetzt — vor diesem
        # Slice bekam jede Entitaet, die den Generator erreichte, eine
        # Persona, auch "Moodle" und "Kursstart Februar 2027".
        #
        # Der Ablehnungsgrund wandert im dritten Tupelfeld mit, damit
        # ``_process_result`` unten eine wahrheitsgemaesse Meldung
        # loggen kann, statt "Successfully generated persona" fuer
        # eine Entitaet auszugeben, die gar kein Profil bekommen hat.
            with lock :
                rejected .append (rejection )
            return idx ,None ,rejection .reason

        except BudgetExceededError :
        # Kein Fallback-Profil bei erschoepftem Budget — der Abbruch
        # gehoert nach oben, sonst entstehen Platzhalterprofile fuer
        # Calls, die nie stattfinden durften (Codex-Finding P2 auf
        # PR #1461).
            raise
        except Exception as e :# noqa: BLE001 — exception is logged; swallowed intentionally
            _legacy .logger .error (f"Failed to generate persona for entity {entity .name }: {str (e )}")
            # Create a fallback profile
            fallback_profile =OasisAgentProfile (
            user_id =idx ,
            user_name =self ._generate_username (entity .name ),
            name =entity .name ,
            bio =f"{entity_type }: {entity .name }",
            persona =entity .summary or "A participant in social discussions.",
            source_entity_uuid =entity .uuid ,
            source_entity_type =entity_type ,
            # Issue #1029: Notprofil nach einem Ausfall — noch
            # dünner als das regelbasierte, also erst recht nicht
            # als echte Stimme zu behandeln.
            generation_source ="rule_based",
            generation_error =str (e )[:160 ],
            )
            return idx ,fallback_profile ,str (e )

    _legacy .logger .info (
    "Starting parallel generation of %d agent personas (parallel count: %d)",
    total ,
    parallel_count ,
    )

    # Detect active gevent monkey-patching so we can pick the cooperative Pool.
    # ``gevent.monkey.is_patched()`` (ohne Argument) liefert seit gevent 23.x
    # keinen "socket"-Status mehr — die öffentliche API ist
    # ``monkey.is_module_patched(name)``. Wir verwenden genau die, damit
    # der Import-Fallback eng bleibt und Programmierfehler nicht
    # verschluckt werden.
    try :
        from gevent import monkey
    except ImportError :
        is_gevent =False
    else :
        is_gevent =monkey .is_module_patched ("socket")

    def _process_result (result_idx :int ,profile :OasisAgentProfile ,error :str |None )->None :
        """Unified per-result handling: store profile, write realtime file, report progress, log."""
        entity =entities [result_idx ]
        entity_type =entity .get_entity_type ()or "Entity"
        profiles [result_idx ]=profile

        with lock :
            completed_count [0 ]+=1
            current =completed_count [0 ]

            # Real-time file writing
        save_profiles_realtime ()

        if progress_callback :
            progress_callback (
            current ,
            total ,
            f"Completed {current }/{total }: {entity .name } ({entity_type })"
            )

        if profile is None :
        # Issue: das Log widersprach sich selbst — eine als
        # "Persona-Eligibility (LLM): Entitaet abgelehnt" verworfene
        # Entitaet erschien in der naechsten Zeile trotzdem als
        # "Successfully generated persona", weil hier nur auf
        # ``error`` (Notprofil-Fall) unterschieden wurde, nicht
        # darauf, ob ueberhaupt ein Profil entstanden ist. Kein
        # Profil in dieser Liste heisst: der Slot bleibt vorerst
        # leer und wird — falls moeglich — aus dem Reservepool
        # nachbesetzt (``_backfill_rejected_slots``).
            reason =error or "kein Ablehnungsgrund protokolliert"
            _legacy .logger .info (
            f"[{current }/{total }] {entity .name } ({entity_type }) abgelehnt, "
            f"kein Profil erzeugt: {reason }"
            )
        elif error :
            _legacy .logger .warning (f"[{current }/{total }] {entity .name } using fallback persona: {error }")
        else :
            _legacy .logger .info (f"[{current }/{total }] Successfully generated persona: {entity .name } ({entity_type })")

            # Issue B2 (PLAN.md „Abbrechen & Pause“): kooperativer Abbruch der
            # Persona-Generierung. Bereits gestartete Persona-Generierungen
            # dürfen auslaufen — das ist akzeptiert (kein hartes Kill der
            # aktuell laufenden Anfrage). Nur das Nachlegen NEUER Arbeit stoppt
            # sofort. ``cancel_requested`` gated unten die Nachbesetzungsrunde
            # (``_backfill_rejected_slots``), die sonst weitere LLM-Calls
            # auslösen würde, obwohl der Nutzer bereits abgebrochen hat.
    cancel_requested =False

    # Codex-Finding PR #1452 (P1), Folgearbeit: dieselbe Budget-Race
    # trifft die parallele Persona-Generierung. Ohne Deckelung pruefen
    # alle Greenlets/Threads ``LLMClient._budget_check()`` gegen
    # denselben Vor-Aufruf-Stand, bevor eine Antwort ihre Nutzung
    # verbucht hat — ein hartes ``max_llm_calls``-Budget mit weniger
    # verbleibenden Calls als ``parallel_count`` kann dadurch
    # ueberschritten werden. Dispatch daher nie mit mehr gleichzeitig
    # gestarteten Workern, als noch Calls frei sind. ``max(1, ...)``
    # haelt die Poolgroesse bei erschoepftem Budget auf eins statt auf
    # null: der eine Worker laeuft in ``BudgetExceededError``, und weil
    # der jetzt bis nach oben durchschlaegt statt im breiten Handler zu
    # landen, bricht die Stufe ab, statt still leer durchzulaufen.
    #
    # Anders als ``SimulationConfigGenerator`` haelt diese Klasse keinen
    # ``LLMClient`` — ``generate_single_profile`` baut ihn pro Persona.
    # Der Enforcer wird deshalb direkt befragt; eine Wegwerf-Instanz nur
    # zum Auslesen wuerde Secret-Aufloesung, Client-Bau und eine
    # zusaetzliche Audit-Zeile ausloesen und ohne API-Key scheitern,
    # womit der Deckel ausgerechnet dann ausfiele, wenn er greifen soll.
    remaining_budget :Optional [int ]=None
    if self .run_id :
        try :
            from .run_budget import RunBudgetEnforcer

            enforcer =RunBudgetEnforcer .for_run (self .run_id )
            if enforcer is not None :
                remaining_budget =enforcer .remaining_hard_calls ()
        except Exception as exc :# noqa: BLE001 — Budget ist Zusatz, kein Hotpath-Risiko
            _legacy .logger .warning (
            "Persona-Generierung: verbleibendes Hartbudget nicht "
            "ermittelbar, Parallelitaet bleibt ungedeckelt: %s",exc
            )
    if remaining_budget is not None :
        parallel_count =min (parallel_count ,max (1 ,remaining_budget ))

    if is_gevent :
        _legacy .logger .info ("Gevent detected: using native cooperative Pool for parallel persona generation")
        from gevent .pool import Pool
        pool =Pool (parallel_count )

        def worker_wrapper (args ):
            idx ,entity =args
            try :
                return generate_single_profile (idx ,entity )
            except BudgetExceededError :
                raise
            except Exception as e :# noqa: BLE001
                _legacy .logger .error (f"Cooperative greenlet failed unexpectedly for entity {entity .name }: {str (e )}")
                entity_type =entity .get_entity_type ()or "Entity"
                fallback_profile =OasisAgentProfile (
                user_id =idx ,
                user_name =self ._generate_username (entity .name ),
                name =entity .name ,
                bio =f"{entity_type }: {entity .name }",
                persona =entity .summary or "A participant in social discussions.",
                source_entity_uuid =entity .uuid ,
                source_entity_type =entity_type ,
                # Issue #1029: Notprofil nach einem Ausfall — noch
                # dünner als das regelbasierte, also erst recht
                # nicht als echte Stimme zu behandeln.
                generation_source ="rule_based",
                generation_error =str (e )[:160 ],
                )
                return idx ,fallback_profile ,str (e )

        cancel_requested =self ._consume_gevent_results (
        pool ,worker_wrapper ,entities ,_process_result ,completed_count ,total
        )
    else :
        cancel_requested =self ._consume_thread_results (
        generate_single_profile ,entities ,parallel_count ,
        _process_result ,completed_count ,total
        )

        # Issue #1247: Abgelehnte Slots aus dem Reservepool nachbesetzen. Ohne
        # diesen Schritt unterschreitet jede Ablehnung den konfigurierten
        # max_agents-Wert — bei einem Cap von 30 (nach eigener Empfehlung der
        # Floor ohne Puffer) und einer beobachteten Ablehnungsquote von bis zu
        # 32 % waere das der Unterschied zwischen 30 und 20 Stimmen.
        # Bei einem Nutzerabbruch (cancel_requested) bleibt die Nachbesetzung
        # aus — sie würde weitere LLM-Calls auslösen, obwohl bereits
        # abgebrochen wurde.
    if rejected and not cancel_requested :
        self ._backfill_rejected_slots (
        profiles =profiles ,
        entities =entities ,
        reserve_entities =list (reserve_entities or []),
        use_llm =use_llm ,
        rejected =rejected ,
        )

        # Dedup display_name und user_name: LLM neigt dazu, dieselbe reale Person
        # mehrfach zu klonen wenn sie im Doc prominent ist. Bei Dubletten neuen
        # DACH-Namen aus dem Pool ziehen, Handle entsprechend neu bauen.
    seen_names :set =set ()
    seen_last_names :set =set ()
    seen_handles :set =set ()
    for p in profiles :
        if p is None :
            continue
            # Issue #1246 (CodeRabbit PR #1257): Kollektive nehmen an der
            # Personennamen-Dedup nicht teil. Zwei Organisationen mit gleichem
            # Schlusstoken — "… GmbH", "… e.V." — galten hier als doppelter
            # Nachname, und die zweite bekam einen zufaelligen DACH-Personen-
            # namen zugewiesen, waehrend ihr Personatext weiter die
            # Organisation beschreibt. Das ist exakt der Identitaetsbruch,
            # den dieser Slice schliesst.
        if p .persona_kind =="collective":
            continue
        norm_name =(p .name or "").strip ().lower ()
        last_name =self ._last_name (p .name or "")
        if norm_name and (
        norm_name in seen_names
        or (last_name is not None and last_name in seen_last_names )
        ):
            new_name =self ._pick_dach_name (p .gender )
            attempts =0
            while (
            new_name .lower ()in seen_names
            or (self ._last_name (new_name )or "")in seen_last_names
            )and attempts <30 :
                new_name =self ._pick_dach_name (p .gender )
                attempts +=1
            p .name =new_name
            p .user_name =self ._generate_username (new_name )
        seen_names .add ((p .name or "").strip ().lower ())
        last_name =self ._last_name (p .name or "")
        if last_name :
            seen_last_names .add (last_name )

        norm_handle =(p .user_name or "").strip ().lower ()
        if norm_handle and norm_handle in seen_handles :
        # Handle steht schon; hänge Suffix-Rotation an.
            base =norm_handle .rsplit ("_",1 )[0 ]if "_"in norm_handle else norm_handle
            p .user_name =self ._generate_username (base )
        seen_handles .add ((p .user_name or "").strip ().lower ())

        # Summenzeile: die einzelnen "[i/n]"-Meldungen oben genuegen nicht als
        # Bilanz, ohne sie nachzuzaehlen — genau daran ist heute eine
        # Fehlersuche vorbeigelaufen (23x "Successfully generated" im Log,
        # aber am Ende nur 15 Personas). ``rejected`` zaehlt jede Ablehnung
        # inklusive der beim Nachbesetzen aus dem Reservepool verbrauchten,
        # also darf "angetreten" nicht der primaere ``total`` allein sein —
        # sonst kann die Zeile eine rechnerisch unmoegliche Bilanz zeigen
        # (mehr Ablehnungen als Angetretene), sobald ein Reserve-Kandidat
        # selbst abgelehnt wird, bevor ein anderer den Slot fuellt. Aus
        # ``generated_count + len(rejected)`` folgt die Gleichung
        # angetreten = abgelehnt + erzeugt per Konstruktion und ist damit in
        # jeder Konstellation stimmig.
    generated_count =len ([p for p in profiles if p ])
    attempted_count =generated_count +len (rejected )
    _legacy .logger .info (
    "Persona generation complete: %d Kandidat(en) angetreten, %d abgelehnt, "
    "%d Personas erzeugt.",
    attempted_count ,
    len (rejected ),
    generated_count ,
    )

    if degradations is not None :
        self ._report_persona_degradation (profiles ,degradations )

        # Re-save after dedup to keep realtime file in sync with final state.
    save_profiles_realtime ()

    # Issue #1247 (CodeRabbit PR #1258): Leere Slots verdichten. Eine
    # Ablehnung ohne verfuegbaren Nachruecker liess bisher ``None`` in der
    # Liste stehen; ``save_profiles`` dereferenziert aber jeden Eintrag und
    # waere daran gescheitert — der bewusst unterstuetzte Fall "Platz bleibt
    # leer" haette die Vorbereitung abgebrochen statt einen kleineren, aber
    # gueltigen Personensatz zu liefern.
    return [profile for profile in profiles if profile is not None ]
