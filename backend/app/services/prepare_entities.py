"""Entity selection and graph-read phase for simulation preparation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from . import prepare_service as _legacy
from .degradation_collector import DegradationCollector

if TYPE_CHECKING:
    from .entity_reader import EntityNode
    from .simulation_manager import SimulationState

def _strip_leading_article (tokens :list [str ])->list [str ]:
    """Entfernt fuehrende Artikel, falls danach noch ein Namensrest bleibt."""
    while len (tokens )>1 and tokens [0 ].casefold ()in _legacy ._LEADING_ARTICLES :
        tokens =tokens [1 :]
    return tokens


def _normalize_adjective_endings (tokens :list [str ])->list [str ]:
    """Gleicht einfache Adjektivflexion an ("digitaler"/"digitale"/"digitalen"
    -> "digital").

    Bewusst konservativ in drei Punkten:

    1. Nur das Token unmittelbar vor dem letzten (dem Kopf-Nomen) kommt
       ueberhaupt infrage. In deutschen Nominalphrasen steht das attributive
       Adjektiv direkt vor seinem Kopf-Nomen, ohne trennendes Wort dazwischen
       ("digitaler Zwilling", "junge Familien"). Ein Token, das *nicht*
       unmittelbar vor dem letzten steht, ist damit strukturell kein
       attributives Adjektiv des Kopf-Nomens, selbst wenn es zufaellig auf
       eine Adjektivendung endet. Das ist bewusst enger als "irgendein
       nicht-letztes Token": geprueft an einer Grossschreibungs-Heuristik
       ("Nomen werden grossgeschrieben") zeigte sich, dass sie am
       Phrasenanfang nicht traegt — "Junge Familien" (bestehender Testfall)
       braucht die Normalisierung genau am ersten, grossgeschriebenen Token,
       weil dort auch attributive Adjektive phrasenanfangs grossgeschrieben
       auftreten. Grossschreibung allein trennt Nomen und Adjektiv also
       nicht zuverlaessig; die Wortstellung tut es. Sie schuetzt zugleich
       "Unternehmen der Region" vs. "Unternehmer der Region" (Codex-Finding
       auf PR #1453): "Unternehmen"/"Unternehmer" stehen dort nicht
       unmittelbar vor dem Kopf-Nomen "Region" — dazwischen steht "der" —,
       werden also nie angefasst, obwohl beide Nomen zufaellig auf eine
       Adjektivendung ("-en"/"-er") enden. Einwortige Namen ("Lehrkraft",
       "Lernplattform") sind ueberhaupt nie betroffen, weil ihr einziges
       Token immer das letzte ist.
    2. Der verbleibende Stamm muss mindestens
       ``_MIN_ADJECTIVE_STEM_LENGTH`` Zeichen lang sein, sonst wird nicht
       gestrippt (siehe Kommentar dort). Das schuetzt z. B. "der" in
       "Unternehmen der Region" zusaetzlich, falls die Phrase kuerzer waere.
    3. Trifft keine der beiden Bedingungen zu, bleibt das Token unveraendert
       stehen. Im Zweifel wird nicht gestemmt — ein verpasster Treffer ist
       billig, eine falsche Fusion verfaelscht die Persona-Menge.

    Grenze: bei mehreren attributiven Adjektiven vor dem Kopf-Nomen ("die
    grosse digitale Lernplattform") wird nur das unmittelbar vorangehende
    Adjektiv normalisiert; weiter vorne stehende Adjektive bleiben
    unveraendert. Das ist ein verpasster Treffer, keine falsche Fusion, und
    damit im Sinne des Auftrags die sicherere Seite.

    Kein Nomen-Stemmer, kein Fremdbibliotheks-Ansatz — nur eine kleine feste
    Endungsliste auf Wortebene.
    """
    if len (tokens )<2 :
        return tokens
    normalized =list (tokens )
    index =len (normalized )-2
    lower =normalized [index ].casefold ()
    for suffix in _legacy ._ADJECTIVE_SUFFIXES :
        stem_length =len (lower )-len (suffix )
        if lower .endswith (suffix )and stem_length >=_legacy ._MIN_ADJECTIVE_STEM_LENGTH :
            normalized [index ]=lower [:-len (suffix )]
            break
    return normalized


def _entity_identity_key (entity :"EntityNode")->tuple [str ,str ]:
    """Vergleichsschluessel fuer Persona-Kandidaten (Issue #1177, #1177-Folge).

    Normalisiert wie ``report_contract._stakeholder_group_key``: casefold plus
    Whitespace-Kollaps. Die Ontologie liefert denselben Stakeholder mehrfach in
    leicht abweichender Schreibweise; roh verglichen zaehlt jede Variante als
    eigene Gruppe. Zusaetzlich werden fuehrende Artikel entfernt und einfache
    Adjektivendungen angeglichen (siehe ``_strip_leading_article`` und
    ``_normalize_adjective_endings``), damit z. B. "digitaler Zwilling", "der
    digitale Zwilling" und "digitale Zwilling" als eine Gruppe zaehlen.

    Der Typ gehoert in den Schluessel: derselbe Name unter zwei Typen ist
    fachlich nicht dasselbe — der Bildungstraeger als ``Traeger`` und als
    ``Kostentraeger`` sind zwei Rollen, auch wenn der Typfehler selbst
    (zweiter Befund in #1177) hier nicht behoben wird.
    """
    tokens =(entity .name or "").split ()
    tokens =_strip_leading_article (tokens )
    tokens =_normalize_adjective_endings (tokens )
    name =" ".join (tokens ).casefold ()
    entity_type =" ".join ((entity .get_entity_type ()or "Entity").split ()).casefold ()
    return name ,entity_type


def _dedupe_entities (
entities :"List[EntityNode]",
)->"tuple[List[EntityNode], int]":
    """Entfernt Mehrfachnennungen; erste Nennung gewinnt.

    Gibt die bereinigte Liste und die Zahl entfernter Dubletten zurueck.
    """
    seen :set [tuple [str ,str ]]=set ()
    unique :List [EntityNode ]=[]
    for entity in entities :
        key =_entity_identity_key (entity )
        if key in seen :
            continue
        seen .add (key )
        unique .append (entity )
    return unique ,len (entities )-len (unique )


def _cap_entities_across_types (
entities :"List[EntityNode]",max_agents :int
)->"List[EntityNode]":
    """Kappt auf ``max_agents`` und sichert dabei jedem Typ einen Platz.

    Issue #1177: ``entities[:max_agents]`` liess eine ueberrepraesentierte
    Gruppe alle Plaetze belegen — kleine, aber fachlich wichtige Gruppen
    (``Betriebsrat``, ``Honorarkraft``) fielen komplett heraus. Die Auswahl
    geht deshalb reihum durch die Typen: erst je ein Vertreter pro Typ, dann
    der zweite und so weiter, bis das Limit erreicht ist.

    Innerhalb eines Typs bleibt die Reihenfolge der Quelle erhalten. Sie ist
    unsortiert — der Lesepfad kennt kein ``ORDER BY``; welcher Vertreter eines
    Typs gewinnt, ist damit weiterhin willkuerlich. Was diese Funktion
    aendert, ist nur, dass *jeder* Typ vertreten ist, solange Plaetze
    reichen. Eine Sortierung nach Grad oder Zentralitaet waere der naechste
    Schritt und braucht eine Aenderung im Reader.
    """
    if max_agents <=0 or len (entities )<=max_agents :
        return list (entities )

    by_type :Dict [str ,List [EntityNode ]]={}
    for entity in entities :
        by_type .setdefault (entity .get_entity_type ()or "Entity",[]).append (entity )

    selected :List [EntityNode ]=[]
    round_index =0
    # Typen in Erstauftrittsreihenfolge — deterministisch und ohne stille
    # Bevorzugung alphabetisch frueher Bezeichnungen.
    while len (selected )<max_agents :
        added_this_round =False
        for bucket in by_type .values ():
            if round_index >=len (bucket ):
                continue
            selected .append (bucket [round_index ])
            added_this_round =True
            if len (selected )>=max_agents :
                break
        if not added_this_round :
            break
        round_index +=1

    return selected


def _phase_read_entities (
state :SimulationState ,
storage :Any ,
defined_entity_types :Optional [List [str ]],
max_agents :Optional [int ],
progress_callback :Optional [Callable ]=None ,
degradations :Optional [DegradationCollector ]=None ,
):
    """Phase 1: Entities aus dem Graphen lesen + filtern + cappen.

    Aktualisiert ``state.entities_count`` und ``state.entity_types`` als
    Seiteneffekt; gibt das ``FilteredEntities``-Objekt zurück.
    """
    if progress_callback :
        progress_callback ("reading",0 ,"Connecting to graph...")

    if not storage :
        raise ValueError ("storage (GraphStorage) is required for prepare_simulation")
    reader =_legacy .EntityReader (storage )

    if progress_callback :
        progress_callback ("reading",30 ,"Reading node data...")

    filtered =reader .filter_defined_entities (
    graph_id =state .graph_id ,
    defined_entity_types =defined_entity_types ,
    enrich_with_edges =True ,
    )

    # Issue #1034: entity_type-Filter (label-technisch) findet auch
    # Entitäten ohne menschlichen Träger — "USA" (Country), "Agora"
    # (Product) usw. Der Eignungsfilter schließt sie vor dem
    # max_agents-Cap aus, damit sie weder zählen noch generiert werden.
    eligibility =_legacy .filter_eligible_entities (filtered .entities ,degradations =degradations )
    if eligibility .exclusions :
        filtered .entities =eligibility .eligible
        filtered .filtered_count =len (filtered .entities )
        filtered .entity_types ={
        entity .get_entity_type ()or "Entity"for entity in filtered .entities
        }

        # Issue #1177: Vor dem Cap deduplizieren. Mehrfachnennungen derselben
        # Stakeholdergruppe belegten sonst die begrenzten Persona-Plaetze und
        # verdraengten tatsaechlich verschiedene Gruppen.
    deduped ,duplicate_count =_dedupe_entities (filtered .entities )
    if duplicate_count :
        _legacy .logger .info (
        "Persona-Kandidaten: %d Dublette(n) vor dem Cap entfernt "
        "(%d → %d Entitaeten)",
        duplicate_count ,
        len (filtered .entities ),
        len (deduped ),
        )
        filtered .entities =deduped
        filtered .filtered_count =len (deduped )

        # User-controlled cap on number of agents (optional).
        #
        # Issue #1177: Frueher ``entities[:max_agents]`` mit der Begruendung, der
        # Reader sortiere nach Grad/Wichtigkeit. Diese Annahme stimmt nicht —
        # weder ``filter_defined_entities`` noch der Neo4j-Lesepfad enthalten ein
        # ``ORDER BY``. Die Auswahl war damit die unsortierte
        # Rueckgabereihenfolge der Query, also willkuerlich, und eine
        # ueberrepraesentierte Gruppe konnte alle Plaetze belegen.
    if (
    max_agents is not None
    and max_agents >0
    and len (filtered .entities )>max_agents
    ):
        _legacy .logger .info (
        f"Capping agent count at {max_agents } "
        f"(originally {len (filtered .entities )} entities)"
        )
        capped =_cap_entities_across_types (filtered .entities ,max_agents )
        # Issue #1247: Was der Cap wegschneidet, ist die Reserve. Die
        # typunabhaengige Eignungspruefung faellt erst im
        # Persona-Generierungsaufruf, also *nach* dem Cap — ohne Reservepool
        # bliebe jeder dort abgelehnte Platz ersatzlos leer und der
        # konfigurierte max_agents-Wert wuerde unterschritten.
        selected_uuids ={entity .uuid for entity in capped }
        filtered .reserve_entities =[
        entity for entity in filtered .entities if entity .uuid not in selected_uuids
        ]
        filtered .entities =capped
        filtered .filtered_count =len (filtered .entities )
        filtered .entity_types ={
        entity .get_entity_type ()or "Entity"for entity in filtered .entities
        }

    state .entities_count =filtered .filtered_count
    state .entity_types =list (filtered .entity_types )

    if progress_callback :
        progress_callback (
        "reading",100 ,
        f"Completed, total {filtered .filtered_count } entities",
        current =filtered .filtered_count ,
        total =filtered .filtered_count ,
        )

    return filtered
