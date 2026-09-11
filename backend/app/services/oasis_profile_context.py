"""Implementation helpers extracted from OasisProfileGenerator.

The public compatibility surface remains app.services.oasis_profile_generator.
"""

from __future__ import annotations

from typing import Any

from . import oasis_profile_generator as _legacy
import re
from typing import Dict, List, Optional
from .entity_reader import EntityNode
from .persona_domain_coherence import coherence_findings, is_collective_entity_type

def _search_graph_for_entity (self: Any ,entity :EntityNode )->Dict [str ,Any ]:
    """
    Use GraphStorage hybrid search to obtain rich information related to entity

    Uses storage.search() (hybrid vector + BM25) for both edges and nodes.

    Args:
        entity: Entity node object

    Returns:
        Dictionary containing facts, node_summaries, context
    """
    if not self .storage :
        return {"facts":[],"node_summaries":[],"context":""}

    entity_name =entity .name 

    results ={
    "facts":[],
    "node_summaries":[],
    "context":""
    }

    if not self .graph_id :
        _legacy .logger .debug ("Skip knowledge graph search: graph_id not set")
        return results 

    comprehensive_query =f"All information, activities, events, relationships and background about {entity_name }"

    try :
    # Search edges (facts)
        edge_results =self .storage .search (
        graph_id =self .graph_id ,
        query =comprehensive_query ,
        limit =30 ,
        scope ="edges"
        )

        all_facts =set ()
        if isinstance (edge_results ,dict )and 'edges'in edge_results :
            for edge in edge_results ['edges']:
                fact =edge .get ('fact','')
                if fact :
                    all_facts .add (fact )
        results ["facts"]=list (all_facts )

        # Search nodes (entity summaries)
        node_results =self .storage .search (
        graph_id =self .graph_id ,
        query =comprehensive_query ,
        limit =20 ,
        scope ="nodes"
        )

        all_summaries =set ()
        if isinstance (node_results ,dict )and 'nodes'in node_results :
            for node in node_results ['nodes']:
                summary =node .get ('summary','')
                if summary :
                    all_summaries .add (summary )
                name =node .get ('name','')
                if name and name !=entity_name :
                    all_summaries .add (f"Related Entity: {name }")
        results ["node_summaries"]=list (all_summaries )

        # Build combined context
        context_parts =[]
        if results ["facts"]:
            context_parts .append ("Fact Information:\n"+"\n".join (f"- {f }"for f in results ["facts"][:20 ]))
        if results ["node_summaries"]:
            context_parts .append ("Related Entities:\n"+"\n".join (f"- {s }"for s in results ["node_summaries"][:10 ]))
        results ["context"]="\n\n".join (context_parts )

        _legacy .logger .info (f"Knowledge graph hybrid search completed: {entity_name }, retrieved {len (results ['facts'])} facts, {len (results ['node_summaries'])} related nodes")

    except Exception as e :# noqa: BLE001 — exception is logged; swallowed intentionally
        _legacy .logger .warning (f"Knowledge graph search failed ({entity_name }): {e }")

    return results


def _build_entity_context (self: Any ,entity :EntityNode )->str :
    """
    Build complete context information for entity

    Includes:
    1. Edge information of the entity itself (facts)
    2. Detailed information of associated nodes
    3. Rich information retrieved from knowledge graph hybrid search
    """
    context_parts =[]

    # 1. Add entity attribute information
    if entity .attributes :
        attrs =[]
        for key ,value in entity .attributes .items ():
            if value and str (value ).strip ():
                attrs .append (f"- {key }: {value }")
        if attrs :
            context_parts .append ("### Entity Attributes\n"+"\n".join (attrs ))

            # 2. Add related edge information (facts/relationships)
    existing_facts =set ()
    if entity .related_edges :
        relationships =[]
        for edge in entity .related_edges :# No limit on quantity
            fact =edge .get ("fact","")
            edge_name =edge .get ("edge_name","")
            direction =edge .get ("direction","")

            if fact :
                relationships .append (f"- {fact }")
                existing_facts .add (fact )
            elif edge_name :
                if direction =="outgoing":
                    relationships .append (f"- {entity .name } --[{edge_name }]--> (Related Entity)")
                else :
                    relationships .append (f"- (Related Entity) --[{edge_name }]--> {entity .name }")

        if relationships :
            context_parts .append ("### Related Facts and Relationships\n"+"\n".join (relationships ))

            # 3. Add detailed information of related nodes
    if entity .related_nodes :
        related_info =[]
        for node in entity .related_nodes :# No limit on quantity
            node_name =node .get ("name","")
            node_labels =node .get ("labels",[])
            node_summary =node .get ("summary","")

            # Filter out default labels
            custom_labels =[lbl for lbl in node_labels if lbl not in ["Entity","Node"]]
            label_str =f" ({', '.join (custom_labels )})"if custom_labels else ""

            if node_summary :
                related_info .append (f"- **{node_name }**{label_str }: {node_summary }")
            else :
                related_info .append (f"- **{node_name }**{label_str }")

        if related_info :
            context_parts .append ("### Related Entity Information\n"+"\n".join (related_info ))

            # 4. Use knowledge graph hybrid search to get richer information
    graph_results =self ._search_graph_for_entity (entity )

    if graph_results .get ("facts"):
    # Deduplication: exclude existing facts
        new_facts =[f for f in graph_results ["facts"]if f not in existing_facts ]
        if new_facts :
            context_parts .append ("### Facts Retrieved from Knowledge Graph\n"+"\n".join (f"- {f }"for f in new_facts [:15 ]))

    if graph_results .get ("node_summaries"):
        context_parts .append ("### Related Nodes Retrieved from Knowledge Graph\n"+"\n".join (f"- {s }"for s in graph_results ["node_summaries"][:10 ]))

    return "\n\n".join (context_parts )


def _align_persona_identity (cls: Any ,persona :str ,display_name :str )->str :
    """Zieht den Namen im Persona-Freitext auf den Anzeigenamen (#1246).

    Der Generator liefert ``display_name`` und ``persona`` als getrennte
    Felder, und in 50 bis 81 Prozent der messbaren Faelle beschrieben sie
    verschiedene Menschen — haeufig mit abweichendem Geschlecht. Der
    Interview-Systemprompt setzt beides zusammen ("Du bist <label>" plus
    Profiltext), die Persona bekommt damit zwei Identitaeten in derselben
    Nachricht. Das ist die plausibelste Erklaerung fuer die beobachtete
    Rollenuebernahme in den Interview-Antworten.

    Die Reparatur ist bewusst deterministisch statt ein weiterer
    Prompt-Appell: der Prompt enthielt bereits eine Rollentreue-Regel, das
    Modell verletzte also eine vorhandene Regel, keine fehlende.

    Ersetzt werden der vollstaendige Eroeffnungsname und seine einzelnen
    Bestandteile, damit auch spaetere Erwaehnungen ("Sabine schaetzt…",
    "Frau Krueger meldet…") mitgezogen werden. Findet sich kein
    Eroeffnungsname oder stimmt er bereits, bleibt der Text unangetastet.
    """
    if not persona or not display_name :
        return persona 

    match =cls ._LEADING_NAME_RE .match (persona )
    if not match :
        return persona 

    found =match .group (1 ).strip ()
    if found ==display_name :
        return persona 

    found_parts =found .split ()
    target_parts =display_name .split ()

    # Laengste Zeichenketten zuerst, sonst zerlegt die Teilersetzung den
    # Vollnamen, bevor er als Ganzes getroffen wird.
    replacements :List [tuple [str ,str ]]=[(found ,display_name )]
    for idx ,part in enumerate (found_parts ):
        if len (part )<3 :
            continue 
        target =target_parts [idx ]if idx <len (target_parts )else target_parts [-1 ]
        replacements .append ((part ,target ))

    aligned =persona 
    for source ,target in sorted (replacements ,key =lambda p :-len (p [0 ])):
        aligned =re .sub (rf"\b{re .escape (source )}\b",target ,aligned )
    return aligned


def _profession_after_coherence_check (
*,
entity_type :str ,
entity_name :str ,
persona_kind :str ,
profession :Optional [str ],
persona_text :str ,
entity_summary :Optional [str ],
entity_context :Optional [str ],
)->Optional [str ]:
    """Prueft Domaenen-Kohaerenz und leert einen fachfremden Beruf.

    Im Referenzlauf report_cc2ef45da5e9 wurde aus einer EmployeeGroup eines
    Klinik-Rollouts eine "Sachbearbeiterin in der Fertigungsplanung" und aus
    einem PatientAdvisoryCouncil ein "Schichtleiter Maschinenbau" —
    plausible Vitae aus einem Fach, das in keiner Quelle vorkam.

    Bereinigt wird nur der Beruf und nur bei eindeutigem Drift: dieselbe
    Linie wie beim nicht ableitbaren Beruf (#1246) — lieber leer als
    erfunden. Der Freitext bleibt stehen; ihn zu beschneiden wuerde mehr
    zerstoeren als retten, und der Befund steht im Log.
    """
    source_text =" ".join (
    part for part in (entity_summary or "",entity_context or "")if part 
    )
    findings =coherence_findings (
    entity_type =entity_type ,
    entity_name =entity_name ,
    persona_kind =persona_kind ,
    profession =profession or "",
    persona_text =persona_text ,
    source_text =source_text ,
    )
    if not findings :
        return profession 
        # Der Entitaetsname bleibt draussen: er traegt einen Personen- oder
        # Organisationsnamen, und Logs verlassen den Prozess (dieselbe Linie
        # wie beim producer_key, CodeRabbit PR #1151). Typ und Befundart
        # reichen zur Diagnose — sie sagen, *was* nicht stimmt, ohne zu sagen,
        # *wer* betroffen ist.
    _legacy .logger .warning (
    "persona coherence: type=%r befunde=%s",
    entity_type ,
    "; ".join (finding ["kind"]for finding in findings ),
    )
    if profession and any (
    finding ["kind"]=="domain_drift"for finding in findings 
    ):
        return None 
    return profession


def _is_individual_entity (self: Any ,entity_type :str )->bool :
    """Determine if entity is an individual type"""
    return entity_type .lower ()in self .INDIVIDUAL_ENTITY_TYPES


def _is_group_entity (self: Any ,entity_type :str )->bool :
    """Determine if entity is a group/institutional type.

    Die Liste bleibt die erste Instanz — sie ist gepflegt und trennt Fälle,
    die morphologisch nicht auffallen ("NGO"). Danach entscheidet das
    Grundwort des Typs. Im Referenzlauf ``report_cc2ef45da5e9`` fielen
    ``HospitalNetwork``, ``EmployeeGroup`` und ``PatientAdvisoryCouncil``
    durch die Liste und wurden zu erfundenen Einzelpersonen mit Alter,
    Geschlecht und Biografie. Eine Ontologie bringt solche Typen laufend
    hervor; die Liste hinterherzupflegen ist kein Verfahren.
    """
    return (
    entity_type .lower ()in self .GROUP_ENTITY_TYPES 
    or is_collective_entity_type (entity_type )
    )


def _build_eligibility_prompt_block (self: Any ,entity_name :str ,entity_type :str )->str :
        """Erlaubt dem Modell, die Entitaet abzulehnen statt sie zu erfinden (#1247).

        Die Blockliste in ``persona_eligibility`` haengt am ``entity_type`` und
        kann diesen Fall strukturell nicht fangen: 28 von 29 beobachteten
        Nicht-Stakeholdern trugen den Typ ``Organization`` — ``Moodle``,
        ``ChatGPT``, ``Magdeburg``, ``AZAV-Zulassung``, ``Kursstart Februar
        2027``. ``organization`` kann nicht auf die Blockliste, weil
        Bildungstraeger, Betriebe und Behoerden legitime Stakeholder sind.

        Ein enger gefasstes Typvokabular hilft ebenfalls nicht: In einem Lauf
        lieferte das Modell ausschliesslich kanonische Typen — und trotzdem
        landeten 16 von 16 Nicht-Stakeholdern in ``Organization``. Der Typ ist
        gleichzeitig legitimes Label und Auffangtopf fuer alles Unklare.

        Die Frage wird deshalb am Namen und am Kontext beantwortet, nicht am
        Label, und in den ohnehin stattfindenden Generierungsaufruf gefaltet.
        """
        if self .language =="de":
            return f"""### Eignungsprüfung (vor allem anderen zu beantworten)

Prüfe zuerst, ob „{entity_name }“ überhaupt einen menschlichen Träger haben kann — also ob es Menschen gibt, die für diese Entität sprechen und im Szenario eine eigene Interessenlage vertreten.

Setze `ineligible: true` und begründe knapp in `ineligible_reason`, wenn „{entity_name }“ eines der folgenden ist:
- eine Software, ein Modell, ein Werkzeug oder ein technisches System (auch wenn der Typ „{entity_type }“ etwas anderes nahelegt)
- ein Ort, eine Stadt, ein Bundesland oder eine Region
- ein Datum, ein Termin, ein Zeitraum oder ein Meilenstein
- ein Dokument, ein Abschnitt, eine Zulassung, ein Verfahren oder ein Regelwerk
- ein Gerät, eine Infrastruktur oder eine Systemkomponente
- ein abstrakter Begriff, ein Sammelbegriff oder das Analysewerkzeug selbst

Der Entitätstyp ist dabei nur ein Hinweis, keine Antwort — er trägt in der Praxis häufig „Organization“, auch wenn die Entität eine Software oder eine Stadt ist. Entscheide nach dem Namen und dem Kontext.

Bei `ineligible: true` sind alle übrigen Felder bedeutungslos, müssen aber weiterhin schemagültig sein — sonst wird die Antwort verworfen, drei Versuche scheitern und die Entität landet über den regelbasierten Pfad doch als Persona im Lauf. Verwende genau: display_name und handle je ein Minuszeichen, age 30, gender other, mbti ISTJ, country DE, voice_register neutral-de, leere Strings für bio, persona und profession, leere Liste für interested_topics. Erfinde in diesem Fall KEINE Persona.

Bei `ineligible: false` beantworte die Aufgabe oben wie beschrieben."""

        return f"""### Eligibility check (answer this first)

First decide whether "{entity_name }" can have a human bearer at all — that is, whether there are people who speak for this entity and hold their own stake in the scenario.

Set `ineligible: true` and give a short `ineligible_reason` if "{entity_name }" is any of:
- a piece of software, a model, a tool, or a technical system (even if the type "{entity_type }" suggests otherwise)
- a place, city, state, or region
- a date, deadline, period, or milestone
- a document, section, accreditation, procedure, or set of rules
- a device, infrastructure, or system component
- an abstract concept, an umbrella term, or the analysis tool itself

The entity type is a hint, not an answer — in practice it often reads "Organization" even when the entity is software or a city. Decide from the name and the context.

When `ineligible: true`, all other fields are meaningless but must still be schema-valid — otherwise the response is rejected, three attempts fail and the entity becomes a persona anyway via the rule-based path. Use exactly: display_name and handle each a single hyphen, age 30, gender other, mbti ISTJ, country DE, voice_register neutral-de, empty strings for bio, persona and profession, empty list for interested_topics. Do NOT invent a persona in that case.

When `ineligible: false`, answer the task above as described."""
