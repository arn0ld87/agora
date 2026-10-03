"""Entity selection and graph-read phase for simulation preparation."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ..contracts.pipeline_degradation_contract import DegradationKind, DegradationSeverity
from . import prepare_service as _legacy
from .degradation_collector import DegradationCollector
from .entity_alias_resolution import _attach_aliases, _UnionFind, resolve_aliases
from .entity_reader import FilteredEntities
from .persona_domain_coherence import is_collective_entity_type

if TYPE_CHECKING:
    from .entity_reader import EntityNode, EntityReader
    from .prepare_checkpoint import PreparePersonaCheckpoint
    from .simulation_manager import SimulationState


# Issue #1713/#1470: Relationstyp, den der system-eigene Ontologie-
# Generator fuer "Person vertritt Organisation" vorsieht (siehe
# ontology_generator.py, Abschnitt "Relationship Type Reference": REPRESENTS).
# Bewusst eine feste Liste bestehender, vom
# System selbst erzeugbarer Relationstypen — keine Namensheuristik auf
# Personen- oder Organisationsnamen. Vergleich case-insensitiv, weil
# projektspezifische Ontologien den Relationsnamen leicht abweichend
# schreiben koennen (z. B. "works_for").
# REPRESENTS und LEADS belegen Vertretung (#1759 A4: der im Dokument genannte
# Vorsitzende fuehrt den Betriebsrat, der Graph hatte dafuer LEADS statt
# REPRESENTS — die Zusammenlegung griff deshalb nicht). WORKS_FOR/
# AFFILIATED_WITH belegen nur Zugehoerigkeit, keine Vertretung. Sonst wuerde
# z. B. eine Betriebsraetin, die fuer die Klinik arbeitet, die Klinik als
# Akteur ersetzen und "fuer sie sprechen".
_REPRESENTATION_RELATION_TYPES = frozenset({"REPRESENTS", "LEADS"})

# Issue #1759 (A4): Namensvarianten derselben Organisation belegten mehrere
# Persona-Plaetze. Die Vergleichsschluessel sind bewusst konservativ.
_logger = logging.getLogger("agora.prepare_entities")
_VARIANT_FUNCTION_WORDS = frozenset(
    {"der", "die", "das", "des", "dem", "den", "von", "vom", "fuer", "für",
     "im", "in", "am", "und", "zu", "zur", "zum"}
)
_VARIANT_LEGAL_FORMS = frozenset(
    {"gmbh", "ggmbh", "mbh", "ag", "kg", "ug", "gbr", "ohg", "se", "ev", "e.v"}
)
# Organe, die die Organisation nach aussen vertreten. Betriebsrat/Aufsichtsrat
# sind bewusst NICHT enthalten: Sie sind eigene Stakeholder.
_ORGAN_WORDS = frozenset(
    {"geschäftsführung", "geschäftsleitung", "vorstand", "leitung",
     "direktion", "präsidium"}
)
# Belegkanten, die ein Organ (ohne Organisationsnamen) an seine Organisation binden.
_ORGAN_RELATION_TYPES = frozenset(
    {"PART_OF", "ORGAN_OF", "BELONGS_TO", "LEADS", "MANAGES"}
)

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


def _is_organization_entity(entity: "EntityNode") -> bool:
    """Grundwort-Klassifikation (#1246) — dieselbe wie beim Kollektiv-Persona-Pfad."""
    return is_collective_entity_type(entity.get_entity_type() or "Entity")


def _is_representation_edge(edge: Dict[str, Any]) -> bool:
    """Zeigt diese ausgehende Kante auf eine belegte 'vertritt'-Relation?

    Vergleich case-insensitiv gegen ``_REPRESENTATION_RELATION_TYPES`` — keine
    Namensheuristik auf Personen-/Organisationsnamen.
    """
    if edge.get("direction") != "outgoing":
        return False
    edge_name = str(edge.get("edge_name") or "").strip().upper()
    return edge_name in _REPRESENTATION_RELATION_TYPES


def _representation_target(
    person: "EntityNode", edge: Dict[str, Any], by_uuid: Dict[str, "EntityNode"]
) -> Optional["EntityNode"]:
    """Liefert die Ziel-Organisation der Kante, falls sie eine ist."""
    target_uuid = edge.get("target_node_uuid")
    if not isinstance(target_uuid, str):
        return None
    target = by_uuid.get(target_uuid)
    if target is None or target.uuid == person.uuid:
        return None
    return target if _is_organization_entity(target) else None


def _find_representatives(
    persons: "List[EntityNode]", by_uuid: Dict[str, "EntityNode"]
) -> Dict[str, "List[EntityNode]"]:
    """Organisation-UUID -> Liste der sie laut Graph-Relation vertretenden Personen."""
    representatives: Dict[str, List["EntityNode"]] = {}
    for person in persons:
        for edge in person.related_edges or []:
            if not _is_representation_edge(edge):
                continue
            target = _representation_target(person, edge, by_uuid)
            if target is None:
                continue
            representatives.setdefault(target.uuid, []).append(person)
    return representatives


def _apply_single_representative_merge(
    person: "EntityNode",
    org: "EntityNode",
    degradations: Optional[DegradationCollector],
) -> None:
    """Regelfall (Issue #1713): genau eine Person vertritt die Organisation."""
    person.affiliation = org.name
    _legacy.logger.info(
        "Person-Organisation-Zusammenlegung (#1713): person=%s organisation=%s "
        "— ein Agent statt zwei",
        person.name,
        org.name,
    )
    if degradations is not None:
        degradations.record(
            DegradationKind.PERSON_REPRESENTS_ORGANIZATION_MERGED,
            DegradationSeverity.WARNING,
            f"{person.name} vertritt {org.name} laut Graph-Relation; "
            "Organisation wird nicht zusaetzlich als eigener Agent gefuehrt.",
            context={"person_uuid": person.uuid, "organization_uuid": org.uuid},
        )


def _apply_collective_affiliation(persons: "List[EntityNode]", org: "EntityNode") -> None:
    """Kollektiver Akteur (Issue #1713): Organisation bleibt eigener Agent."""
    for person in persons:
        person.affiliation = org.name
    _legacy.logger.info(
        "Organisation bleibt eigener Agent (#1713): organisation=%s wird von "
        "%d Personen vertreten (kollektiver Akteur)",
        org.name,
        len(persons),
    )


def _genitive_stem(token: str) -> str:
    """Streicht ein Genitiv-s/-es ("landkreises" -> "landkreis"), konservativ."""
    if token.endswith("es") and len(token) >= 7:
        return token[:-2]
    if len(token) >= 6 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _variant_tokens(name: str) -> tuple[str, ...]:
    """Vergleichstokens eines Organisationsnamens (#1759 A4).

    Casefold, Klammerinhalt, Satzzeichen, Artikel/Funktionswoerter und
    Rechtsformen entfallen, Genitiv-s wird angeglichen. Die Reihenfolge bleibt
    erhalten: das erste Token ist das Kopf-Nomen ("Hebammenverband, ...").
    """
    cleaned = re.sub(r"\([^)]*\)", " ", name or "")
    tokens: list[str] = []
    for raw in re.split(r"[\s,;/]+", cleaned):
        token = raw.strip(".:\"'()[]").casefold()
        if not token or token in _VARIANT_FUNCTION_WORDS or token in _VARIANT_LEGAL_FORMS:
            continue
        tokens.append(_genitive_stem(token))
    return tuple(tokens)


def _organ_split(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Trennt fuehrende Organ-Woerter ("Geschaeftsfuehrung ...") vom Rest."""
    organ_end = 0
    while organ_end < len(tokens) and tokens[organ_end] in _ORGAN_WORDS:
        organ_end += 1
    return tokens[:organ_end], tokens[organ_end:]


def _organ_target_index(
    organ: "EntityNode", org_indices: List[int], entities: "List[EntityNode]", self_index: int
) -> Optional[int]:
    """Index der einen Organisation, an die eine Belegkante das Organ bindet."""
    uuid_to_index = {entities[i].uuid: i for i in org_indices if i != self_index}
    targets: set[int] = set()
    for edge in organ.related_edges or []:
        if edge.get("direction") != "outgoing":
            continue
        if str(edge.get("edge_name") or "").strip().upper() not in _ORGAN_RELATION_TYPES:
            continue
        target_uuid = edge.get("target_node_uuid")
        if isinstance(target_uuid, str) and target_uuid in uuid_to_index:
            targets.add(uuid_to_index[target_uuid])
    return next(iter(targets)) if len(targets) == 1 else None


def _union_entity_variants(
    entities: "List[EntityNode]", org_indices: List[int]
) -> "tuple[_UnionFind, set[int]]":
    """Verbindet Organisations-Varianten; liefert Union-Find und aufgehende Organe."""
    tokens = {i: _variant_tokens(entities[i].name) for i in org_indices}
    uf = _UnionFind(len(entities))
    absorbed: set[int] = set()

    for pos, i in enumerate(org_indices):
        if not tokens[i]:
            continue
        # Namensvariante: gleiche Tokenmenge nach Normalisierung.
        for j in org_indices[pos + 1 :]:
            if tokens[j] and set(tokens[i]) == set(tokens[j]):
                uf.union(i, j)
        # Teilmenge/Obermenge: nur mit gleichem Kopf-Nomen und genau einer
        # Obermenge ("Betriebsrat Kliniken X" ist keine Variante von
        # "Kliniken X"); mehrdeutige Kurzformen bleiben getrennt.
        supersets = [
            j
            for j in org_indices
            if j != i
            and tokens[j]
            and tokens[j][0] == tokens[i][0]
            and set(tokens[i]) < set(tokens[j])
        ]
        if len(supersets) == 1:
            uf.union(i, supersets[0])

    for i in org_indices:
        organ_words, rest = _organ_split(tokens[i])
        if not organ_words:
            continue
        if rest:
            # Der Name enthaelt die Organisation eindeutig.
            bases = [
                j
                for j in org_indices
                if j != i and tokens[j] and set(tokens[j]) == set(rest) and not _organ_split(tokens[j])[0]
            ]
            target = bases[0] if len(bases) == 1 else None
        else:
            target = _organ_target_index(entities[i], org_indices, entities, i)
        if target is not None:
            uf.union(i, target)
            absorbed.add(i)
    return uf, absorbed


def _absorb_variants(survivor: "EntityNode", aliases: "List[EntityNode]") -> None:
    """Uebernimmt Aliase und Attribute in ``survivor`` (in place).

    Der Survivor behaelt bei Konflikten seinen Wert; jeder Konflikt wird
    protokolliert (Logger ``agora.prepare_entities``).
    """
    merged = _attach_aliases(survivor, aliases)
    attrs = merged.attributes
    carried = list(attrs.get("_agora_aliases", []))
    for alias in aliases:
        for earlier in alias.attributes.get("_agora_aliases", []):
            if earlier not in carried:
                carried.append(earlier)
        for key, value in alias.attributes.items():
            if key.startswith("_agora_"):
                continue
            if key not in attrs or attrs[key] in (None, "", [], {}):
                attrs[key] = value
            elif attrs[key] != value and value not in (None, "", [], {}):
                _logger.info(
                    "Entity-Merge-Attributkonflikt (#1759): survivor=%s verworfen_aus=%s "
                    "attribut=%s survivor_wert=%r verworfener_wert=%r",
                    survivor.name,
                    alias.name,
                    key,
                    attrs[key],
                    value,
                )
    attrs["_agora_aliases"] = carried
    if not survivor.summary:
        for alias in aliases:
            if alias.summary:
                survivor.summary = alias.summary
                summaries = attrs.get("_agora_alias_summaries", [])
                if alias.summary in summaries:
                    summaries.remove(alias.summary)
                if not summaries:
                    attrs.pop("_agora_alias_summaries", None)
                break
    survivor.attributes = attrs
    survivor.related_edges = merged.related_edges
    survivor.related_nodes = merged.related_nodes


def _pick_variant_survivor(
    cluster: List[int], absorbed: set[int], entities: "List[EntityNode]"
) -> int:
    """Informativster Name (meiste Tokens, dann laengster), Organe gehen auf."""
    candidates = [i for i in cluster if i not in absorbed] or cluster
    return max(
        candidates,
        key=lambda i: (len(_variant_tokens(entities[i].name)), len(entities[i].name), -i),
    )


def _remap_edge_targets(
    entities: "List[EntityNode]", remap: Dict[str, str]
) -> None:
    """Zeigt Kanten auf zusammengefuehrte UUIDs auf den Survivor um."""
    for entity in entities:
        edges = []
        for edge in entity.related_edges or []:
            target = edge.get("target_node_uuid")
            if isinstance(target, str) and target in remap:
                edge = {**edge, "target_node_uuid": remap[target]}
            if edge.get("target_node_uuid") == entity.uuid:
                continue
            edges.append(edge)
        entity.related_edges = edges


def _merge_entity_variants(entities: "List[EntityNode]") -> "List[EntityNode]":
    """Fuehrt Namensvarianten derselben Organisation vor der Persona-Auswahl zusammen.

    Issue #1759 (A4): "Hebammenverband" und "Hebammenverband, Kreisvertretung
    Hollerau", "Rettungsdienst des Landkreises" und "Rettungsdienst Landkreis
    Hollerau" oder "Kliniken Hollerau gGmbH" und deren "Geschaeftsfuehrung"
    belegten im Referenzlauf je zwei Persona-Plaetze. ``resolve_aliases``
    greift nicht, weil Kommata und Flexion die Tokenmengen verschieben.

    Regeln (nur Organisationen, nie Person+Organisation allein ueber den Namen):

    - gleiche Tokenmenge nach Normalisierung → eine Entitaet;
    - Teilmenge/Obermenge mit gleichem Kopf-Nomen und genau einer Obermenge;
    - Organ ("Geschaeftsfuehrung ...") geht in die Organisation auf, wenn der
      Name sie eindeutig enthaelt oder genau eine Belegkante sie bindet. Ein
      Organ ohne eindeutigen Bezug bleibt eigener Agent.

    Der Survivor behaelt seine Attribute, fehlende werden ergaenzt, Konflikte
    geloggt. Kanten anderer Entitaeten werden auf den Survivor umgezeigt.
    """
    org_indices = [i for i, e in enumerate(entities) if _is_organization_entity(e)]
    if len(org_indices) < 2:
        return entities

    uf, absorbed = _union_entity_variants(entities, org_indices)
    clusters = [c for c in uf.clusters(len(entities)).values() if len(c) > 1]
    if not clusters:
        return entities

    replacements: Dict[int, Optional["EntityNode"]] = {}
    remap: Dict[str, str] = {}
    for cluster in clusters:
        cluster = sorted(cluster)
        survivor_index = _pick_variant_survivor(cluster, absorbed, entities)
        survivor = entities[survivor_index]
        aliases = [entities[i] for i in cluster if i != survivor_index]
        _absorb_variants(survivor, aliases)
        _logger.info(
            "Entity-Varianten-Merge (#1759): %d Entitaeten zu '%s' zusammengefasst "
            "(Aliase=%s)",
            len(cluster),
            survivor.name,
            [a.name for a in aliases],
        )
        for alias in aliases:
            remap[alias.uuid] = survivor.uuid
        for i in cluster:
            replacements[i] = None
        replacements[cluster[0]] = survivor

    merged: "List[EntityNode]" = []
    for i, entity in enumerate(entities):
        kept = replacements.get(i, entity)
        if kept is not None:
            merged.append(kept)
    _remap_edge_targets(merged, remap)
    return merged


def _merge_persons_with_organizations(
    entities: "List[EntityNode]",
    degradations: Optional[DegradationCollector] = None,
) -> "List[EntityNode]":
    """Legt eine Person mit der Organisation zusammen, die sie laut Graph vertritt.

    Issue #1713/#1470: Eine Person und die Organisation, fuer die sie laut
    belegter Graph-Relation arbeitet/spricht (``_REPRESENTATION_RELATION_
    TYPES``), wurden bisher als zwei getrennte Agenten gefuehrt. Das fuehrte
    zur Role-Leakage-Folgemeldung ``unmatched_self_reference``, wenn die
    Person-Persona im Simulationstext "wir, <Organisation>" schrieb, ohne
    dass irgendeine Persona diese Organisation als eigene Rolle trug.

    Regel (Maintainer-Entscheidung, Issue #1713):
    - Vertritt genau eine Person die Organisation, bleibt die Person der
      Agent; die Organisation wird nicht zusaetzlich gefuehrt. Die Person
      traegt die Organisation fortan als ``affiliation``.
    - Vertreten mehrere Personen dieselbe Organisation (kollektiver Akteur)
      oder keine, bleibt die Organisation ein eigener Agent. Im
      Mehrfach-Fall tragen alle repraesentierenden Personen zusaetzlich die
      ``affiliation`` — sie sprechen weiterhin auch fuer sich selbst.

    Jede Zusammenlegung wird sichtbar protokolliert (strukturiertes Log +
    ``DegradationCollector``-Eintrag), nie still.
    """
    by_uuid = {entity.uuid: entity for entity in entities}
    if len(by_uuid) < 2:
        return entities

    persons = [entity for entity in entities if not _is_organization_entity(entity)]
    if not persons:
        return entities

    representatives = _find_representatives(persons, by_uuid)
    if not representatives:
        return entities

    merged_org_uuids: set[str] = set()
    for org_uuid, reps in representatives.items():
        org = by_uuid[org_uuid]
        # Dieselbe Person kann ueber mehrere Kanten (z. B. WORKS_FOR und
        # REPRESENTS) auf dieselbe Organisation zeigen — pro Person nur
        # einmal zaehlen.
        unique_reps = list({person.uuid: person for person in reps}.values())

        if len(unique_reps) == 1:
            _apply_single_representative_merge(unique_reps[0], org, degradations)
            merged_org_uuids.add(org_uuid)
        else:
            _apply_collective_affiliation(unique_reps, org)

    if not merged_org_uuids:
        return entities

    return [entity for entity in entities if entity.uuid not in merged_org_uuids]


def _replace_filtered_entities_if_reduced(
    filtered: "FilteredEntities", new_entities: "List[EntityNode]"
) -> bool:
    """Uebernimmt ``new_entities`` in ``filtered``, falls sie die Liste verkleinert.

    Gemeinsames Update-Muster fuer die drei Vorverarbeitungsschritte in
    ``_phase_read_entities`` (Eignungsfilter, Alias-Aufloesung,
    Person-Organisation-Zusammenlegung) — jeder verkleinert hoechstens die
    Kandidatenliste, nie erweitert er sie.
    """
    if len(new_entities) >= len(filtered.entities):
        return False
    filtered.entities = new_entities
    filtered.filtered_count = len(new_entities)
    filtered.entity_types = {
        entity.get_entity_type() or "Entity" for entity in new_entities
    }
    return True


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
    _replace_filtered_entities_if_reduced(filtered, eligibility.eligible)

    # Issue #1470 (Slice 4.2): Alias-Auflösung vor Dedupe/Cap.
    # Entitäten, die dieselbe Person/Organisation benennen (z. B. „BFW",
    # „BFW Leipzig", „Berufsförderungswerk Leipzig (BFW Leipzig)" oder
    # „Dr. Miriam Vogt"/„Vogt"), werden zu einem Cluster zusammengefasst.
    # Kein Merge über semantische Klassen hinweg; kein LLM-Aufruf. Der
    # Resume-Pfad liest die kanonischen UUIDs aus dem Checkpoint und muss
    # deshalb nicht erneut auflösen.
    entities_before_alias = len(filtered.entities)
    alias_resolved = resolve_aliases(filtered.entities)
    if _replace_filtered_entities_if_reduced(filtered, alias_resolved):
        _legacy.logger.info(
            "Alias-Aufloesung: %d → %d Entitaeten nach Cluster-Bildung",
            entities_before_alias,
            len(alias_resolved),
        )

    # Issue #1713/#1470: Person und die von ihr vertretene Organisation zu
    # einem Agenten zusammenlegen, bevor dedupliziert/gecappt wird — sonst
    # belegen beide getrennt Persona-Plaetze, obwohl sie im Bericht
    # dieselbe Stimme sind.
    #
    # Issue #1759 (A4): Vorher Namensvarianten derselben Organisation
    # (Teilmenge/Obermenge, Genitiv, Organ einer Organisation) zusammenfuehren
    # und Kanten auf den Survivor umzeigen, sonst geht eine Vertretungs-Kante
    # auf eine bereits aufgegangene UUID ins Leere.
    variant_merged = _merge_entity_variants(filtered.entities)
    _replace_filtered_entities_if_reduced(filtered, variant_merged)
    merged_entities = _merge_persons_with_organizations(
        filtered.entities, degradations=degradations
    )
    _replace_filtered_entities_if_reduced(filtered, merged_entities)

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


def _build_eligible_uuid_pool(
    reader: "EntityReader",
    graph_id: str,
    defined_entity_types: Optional[List[str]],
) -> Dict[str, "EntityNode"]:
    """Liest den aktuellen eignungsgefilterten Entity-Pool, geschlüsselt per UUID.

    Issue #1472c (Resume): anders als der normale Phase-1-Pfad wird hier
    NICHT dedupliziert und NICHT gecappt — der Aufrufer sucht ausschließlich
    per UUID nach, die Auswahl selbst kommt bereits fixiert aus dem
    Checkpoint (siehe Moduldocstring ``prepare_checkpoint_contract``).
    """
    filtered = reader.filter_defined_entities(
        graph_id=graph_id,
        defined_entity_types=defined_entity_types,
        enrich_with_edges=True,
    )
    eligibility = _legacy.filter_eligible_entities(filtered.entities, degradations=None)
    pool = eligibility.eligible if eligibility.exclusions else filtered.entities
    return {entity.uuid: entity for entity in pool}


def _lookup_entities_by_uuid(
    by_uuid: Dict[str, "EntityNode"], uuids: List[str]
) -> List[Optional["EntityNode"]]:
    """Bildet eine UUID-Liste (Reihenfolge und Wiederholungen erhalten) auf Entities ab.

    Liefert ``None`` an Positionen, deren UUID im aktuellen Pool nicht mehr
    existiert (z. B. Entity wurde zwischenzeitlich gelöscht) — der Aufrufer
    entscheidet, ob das den Checkpoint entwertet.
    """
    return [by_uuid.get(uuid) for uuid in uuids]


def _phase_read_entities_from_checkpoint(
    state: "SimulationState",
    storage: Any,
    checkpoint: "PreparePersonaCheckpoint",
    progress_callback: Optional[Callable] = None,
) -> Optional[FilteredEntities]:
    """Resume-Variante von Phase 1 (Issue #1472c).

    Berechnet die Cap-/Quota-Auswahl NICHT neu — der Graph-Lesepfad hat
    kein ``ORDER BY`` (siehe ``_cap_entities_across_types``), ein erneuter
    Read könnte eine andere Typ-Verteilung liefern. Stattdessen werden die
    im Checkpoint fixierten Entity-UUIDs (``primary_entity_uuids`` /
    ``reserve_entity_uuids``) nur noch nachgeschlagen.

    Gibt ``None`` zurück, wenn mindestens eine der primären, im Checkpoint
    fixierten Entitäten im Graphen nicht mehr gefunden wird — der Checkpoint
    gilt dann als entwertet, der Aufrufer fällt auf den regulären
    (Neu-)Startpfad zurück.
    """
    if progress_callback:
        progress_callback("reading", 0, "Resuming entity selection from checkpoint...")

    if not storage:
        raise ValueError("storage (GraphStorage) is required for prepare_simulation")
    reader = _legacy.EntityReader(storage)

    by_uuid = _build_eligible_uuid_pool(
        reader, checkpoint.graph_id, checkpoint.defined_entity_types
    )
    primary_raw = _lookup_entities_by_uuid(by_uuid, checkpoint.primary_entity_uuids)
    if any(entity is None for entity in primary_raw):
        _legacy.logger.warning(
            "Prepare-Resume: mindestens eine im Checkpoint fixierte "
            "Entitaet wurde im Graphen nicht mehr gefunden — Checkpoint "
            "gilt als entwertet, Auswahl wird neu berechnet."
        )
        return None
    # mypy kann den ``any()``-Check oben nicht auf den Listentyp durchreichen
    # (weiterhin ``List[EntityNode | None]``) — die Filter-Comprehension
    # narrowt explizit auf ``List[EntityNode]``; laufzeitseitig ein No-Op,
    # da oben bereits sichergestellt ist, dass kein Eintrag ``None`` ist.
    primary: List["EntityNode"] = [entity for entity in primary_raw if entity is not None]
    reserve = [
        entity
        for entity in _lookup_entities_by_uuid(by_uuid, checkpoint.reserve_entity_uuids)
        if entity is not None
    ]

    filtered = FilteredEntities(
        entities=list(primary),
        entity_types=set(checkpoint.entity_types),
        total_count=len(primary),
        filtered_count=len(primary),
        reserve_entities=reserve,
    )

    state.entities_count = checkpoint.entities_count
    state.entity_types = list(checkpoint.entity_types)

    if progress_callback:
        progress_callback(
            "reading",
            100,
            f"Resumed, total {filtered.filtered_count} entities",
            current=filtered.filtered_count,
            total=filtered.filtered_count,
        )

    return filtered


def _lookup_expanded_entities_from_checkpoint(
    storage: Any, checkpoint: "PreparePersonaCheckpoint"
) -> Optional[List["EntityNode"]]:
    """Rekonstruiert die eingefrorene, quota-expandierte Generierungsliste.

    Issue #1472c: das ist exakt die Liste, die der ursprüngliche Versuch
    an ``generate_profiles_from_entities`` übergeben hat (nach
    ``_expand_entities_for_quota``/``_apply_persona_floor_to_entities``) —
    inklusive Wiederholungen derselben Entity (Quota-Expansion dupliziert
    kleine Segmentpools per Round-Robin). Reihenfolge ist bedeutungstragend:
    der Index ist der ``user_id``/Generierungs-Index, den
    ``completed_profiles`` referenziert.

    Gibt ``None`` zurück, wenn eine der UUIDs nicht mehr auffindbar ist —
    der Checkpoint gilt dann als entwertet.
    """
    reader = _legacy.EntityReader(storage)
    by_uuid = _build_eligible_uuid_pool(
        reader, checkpoint.graph_id, checkpoint.defined_entity_types
    )
    expanded_raw = _lookup_entities_by_uuid(by_uuid, checkpoint.expanded_entity_uuids)
    if any(entity is None for entity in expanded_raw):
        _legacy.logger.warning(
            "Prepare-Resume: mindestens eine im Checkpoint fixierte "
            "Generierungs-Entitaet wurde im Graphen nicht mehr gefunden — "
            "Checkpoint gilt als entwertet, Auswahl wird neu berechnet."
        )
        return None
    # Narrowing-Comprehension wie in ``_phase_read_entities_from_checkpoint``.
    return [entity for entity in expanded_raw if entity is not None]
