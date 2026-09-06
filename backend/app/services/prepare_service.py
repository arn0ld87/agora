"""Prepare-Service für Simulationen.

Issue #43 (EPIC-06-ST-03): Aus ``SimulationManager.prepare_simulation`` (244
LOC) in drei klare Phasen-Funktionen plus Top-Level-Orchestrator extrahiert.
Funktionen nehmen einen ``SimulationManager`` als ersten Parameter — gleiches
Muster wie ``branching_service``, vermeidet zirkuläre Importe.

Phasen:

* :func:`_phase_read_entities` — Graph anbinden, Entities filtern, optional
  ``max_agents``-Cap.
* :func:`_phase_generate_profiles` — OASIS-Profiles generieren (parallel,
  Realtime-Save), für Reddit als JSON, für Twitter als CSV speichern.
* :func:`_phase_generate_config` — Simulation-Config per LLM generieren,
  atomar in den ``ArtifactStore`` schreiben.

Der Orchestrator :func:`prepare_simulation` setzt FSM-Status PREPARING/READY
um die Phasen herum und routet Fehler ins FAILED.
"""

from __future__ import annotations

import json
import os
import traceback
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from ..contracts import (
    PersonaQuotaActual,
    PersonaQuotaPlan,
    PersonaTargetContract,
)
from ..contracts.llm_routing_contract import ResolvedRoute
from ..contracts.provider_types import PROVIDER_CODEX_CLI
from ..utils.logger import get_logger
from .degradation_collector import DegradationCollector
from .entity_reader import EntityReader
from .settings_layer import get_default_service as _get_settings
from .llm_routing_seed import resolve_route_api_key
from .llm_runtime import RuntimeLlmConfig
from .oasis_profile_generator import OasisAgentProfile, OasisProfileGenerator
from .persona_eligibility import filter_eligible_entities
from .persona_quota_defaults import default_dach_industry_quota
from .report_agent import MIN_PERSONA_TABLE_ROWS
from .simulation_config_generator import SimulationConfigGenerator

if TYPE_CHECKING:
    from .entity_reader import EntityNode
    from .simulation_manager import SimulationManager, SimulationState

logger = get_logger("agora.prepare")

LlmRuntimeInput = RuntimeLlmConfig | ResolvedRoute


def _resolve_llm_connection(
    llm_runtime: Optional[LlmRuntimeInput],
    *,
    require: bool = True,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Loest Key, Endpoint und Provider-Typ aus der Route — oder bricht ab.

    Fruehere Fassung gab bei nicht aufloesbarer Route ``(None, None)`` zurueck.
    Das sah harmlos aus, war aber der Ausloeser einer stillen Provider-
    Vertauschung: ``OasisProfileGenerator.__init__`` fuellt fehlende Werte aus
    ``Config.LLM_BASE_URL``/``Config.LLM_API_KEY`` auf, waehrend ``model_name``
    aus der Route weitergereicht wird. Ergebnis war eine Halb-Uebergabe —
    Modell aus der UI-Route, Endpoint und Key aus der ``.env`` — die das Modell
    an einen fremden Provider schickte (beobachtet: ``deepseek-v4-flash:0731``
    an ``https://api.minimax.io/v1`` → HTTP 401). Nach aussen meldete der Lauf
    trotzdem "30 Personas erfolgreich generiert", weil jeder Einzelfehler still
    auf ``rule-based generation`` zurueckfiel.

    Der ``#778``-Schutz in ``OasisProfileGenerator`` greift hier nicht: er
    verhindert nur, dass der ``.env``-Key zu einer *uebergebenen* Fremd-URL
    einspringt. Wird gar keine URL uebergeben, sind beide aus der ``.env`` —
    formal "dieselbe Quelle", sachlich die falsche.

    Issue #1418: ``codex_cli`` (transport="cli", #1405) hat by design weder
    ``base_url`` noch ``api_key`` — die dritte Rueckgabe traegt den
    Provider-Typ deshalb explizit weiter, statt ihn wie bisher stillschweigend
    zu verlieren. Ohne sie las ``OasisProfileGenerator`` ein fehlendes
    ``base_url`` als "nicht aufgeloest" und fuellte ``Config.LLM_BASE_URL``
    auf — das Modell aus der codex_cli-Route ging an den .env-HTTP-Endpoint
    (beobachtet: ``gpt-5.6-luna`` an ``https://api.minimax.io/v1`` → HTTP 400).

    Args:
        llm_runtime: Aufgeloeste Route oder Legacy-Runtime-Override.
        require: Wenn ``True`` (Default), ist eine nicht aufloesbare Route ein
            Fehler. ``False`` nur fuer Pfade, die bewusst ohne LLM laufen
            (``use_llm_for_profiles=False``) — dort ist regelbasiert das
            gewollte Ergebnis und kein Notbehelf.

    Raises:
        ValueError: ``require`` ist gesetzt und weder eine ``ResolvedRoute``
            noch ein aktiver Runtime-Override liegt vor, oder die
            ``ResolvedRoute`` selbst keine aufloesbare ``base_url_sanitized``
            traegt und ihr Provider keinen CLI-Transport nutzt (#1104: zweite
            Verteidigungslinie gegen die Halb-Uebergabe, falls der
            Store-Lookup in ``StageModelRouter`` keine Base-URL findet — z. B.
            eine deaktivierte oder geloeschte Connection).
    """
    if isinstance(llm_runtime, ResolvedRoute):
        base_url = llm_runtime.base_url_sanitized
        from .llm_provider_registry import LlmProviderRegistry

        definition = LlmProviderRegistry.connection_definition(llm_runtime.provider_id)
        provider_type = definition.provider_kind if definition else None
        is_cli_transport = definition is not None and definition.transport == "cli"
        if require and not base_url and not is_cli_transport:
            raise ValueError(
                f"kein Endpoint für Provider '{llm_runtime.provider_id}' aufgelöst: die "
                "Route nennt Modell und Provider, aber keine Basis-URL. Ohne Endpoint "
                "würde die Anfrage an die .env-Konfiguration statt an die konfigurierte "
                "Verbindung gehen, während Modell und Schlüssel aus der Route stammen — "
                "diese Mischung erreicht den falschen Provider. Bitte unter Einstellungen "
                f"→ LLM-Anbieter die Verbindung '{llm_runtime.provider_id}' prüfen."
            )
        return resolve_route_api_key(llm_runtime), base_url, provider_type
    if llm_runtime and llm_runtime.enabled:
        provider_type = PROVIDER_CODEX_CLI if llm_runtime.provider == PROVIDER_CODEX_CLI else None
        return llm_runtime.api_key, llm_runtime.base_url, provider_type
    if require:
        raise ValueError(
            "kein LLM-Provider aufgelöst: die Vorbereitung erwartet eine "
            "aufgelöste Route oder einen aktiven Runtime-Override. Ohne beides "
            "würden Endpoint und Schlüssel aus der .env stammen, während das "
            "Modell aus der Route kommt — diese Mischung erreicht den falschen "
            "Provider. Bitte unter Einstellungen → LLM-Anbieter eine aktive "
            "Verbindung wählen."
        )
    return None, None, None


# Bestimmte und unbestimmte Artikel, die einer Entitaetsbezeichnung
# voranstehen koennen ("der digitale Zwilling", "die Lernplattform"). Nur das
# erste Token wird geprueft — Artikel mitten im Namen ("KI-Version der
# Lehrkraft") sind Teil der Bezeichnung und werden nicht angetastet.
_LEADING_ARTICLES = frozenset(
    {
        "der", "die", "das", "den", "dem", "des",
        "ein", "eine", "einen", "einem", "einer", "eines",
    }
)

# Schwache/starke Adjektivendungen, absteigend nach Laenge geprueft, damit
# "digitalen" auf "en" statt versehentlich auf ein kuerzeres Suffix trifft.
_ADJECTIVE_SUFFIXES = ("er", "es", "em", "en", "e")

# Mindestlaenge des verbleibenden Stamms nach Endungs-Abzug. Bewusst auf 4
# gesetzt statt z. B. 3: bei 3 wuerde "ohne" (Praeposition, kein Adjektiv) zu
# "ohn" verstuemmelt. Ein zu kurzer Stamm ist ein Indiz, dass das Wort gar
# kein flektiertes Adjektiv ist — dann lieber nicht anfassen.
_MIN_ADJECTIVE_STEM_LENGTH = 4


def _strip_leading_article(tokens: list[str]) -> list[str]:
    """Entfernt fuehrende Artikel, falls danach noch ein Namensrest bleibt."""
    while len(tokens) > 1 and tokens[0].casefold() in _LEADING_ARTICLES:
        tokens = tokens[1:]
    return tokens


def _normalize_adjective_endings(tokens: list[str]) -> list[str]:
    """Gleicht einfache Adjektivflexion an ("digitaler"/"digitale"/"digitalen"
    -> "digital").

    Bewusst konservativ in zwei Punkten:

    1. Nur nicht-letzte Tokens werden angefasst. In deutschen Nominalphrasen
       steht das attributive Adjektiv vor dem Kopf-Nomen; das letzte Token
       einer Bezeichnung ist damit fast immer das Nomen selbst und wird nie
       gestemmt. Das schuetzt Paare wie "Lehrkraft" vs.
       "Lehrkraeftevertretung" oder "Lernplattform" vs. "Lernender" — das
       sind einwortige Namen, bei denen das einzige Token immer das letzte
       ist und daher unveraendert bleibt.
    2. Der verbleibende Stamm muss mindestens
       ``_MIN_ADJECTIVE_STEM_LENGTH`` Zeichen lang sein, sonst wird nicht
       gestrippt (siehe Kommentar dort).

    Kein Nomen-Stemmer, kein Fremdbibliotheks-Ansatz — nur eine kleine feste
    Endungsliste auf Wortebene.
    """
    if len(tokens) < 2:
        return tokens
    normalized = list(tokens)
    for index in range(len(normalized) - 1):
        lower = normalized[index].casefold()
        for suffix in _ADJECTIVE_SUFFIXES:
            stem_length = len(lower) - len(suffix)
            if lower.endswith(suffix) and stem_length >= _MIN_ADJECTIVE_STEM_LENGTH:
                normalized[index] = lower[: -len(suffix)]
                break
    return normalized


def _entity_identity_key(entity: "EntityNode") -> tuple[str, str]:
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
    tokens = (entity.name or "").split()
    tokens = _strip_leading_article(tokens)
    tokens = _normalize_adjective_endings(tokens)
    name = " ".join(tokens).casefold()
    entity_type = " ".join((entity.get_entity_type() or "Entity").split()).casefold()
    return name, entity_type


def _dedupe_entities(
    entities: "List[EntityNode]",
) -> "tuple[List[EntityNode], int]":
    """Entfernt Mehrfachnennungen; erste Nennung gewinnt.

    Gibt die bereinigte Liste und die Zahl entfernter Dubletten zurueck.
    """
    seen: set[tuple[str, str]] = set()
    unique: List[EntityNode] = []
    for entity in entities:
        key = _entity_identity_key(entity)
        if key in seen:
            continue
        seen.add(key)
        unique.append(entity)
    return unique, len(entities) - len(unique)


def _cap_entities_across_types(
    entities: "List[EntityNode]", max_agents: int
) -> "List[EntityNode]":
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
    if max_agents <= 0 or len(entities) <= max_agents:
        return list(entities)

    by_type: Dict[str, List[EntityNode]] = {}
    for entity in entities:
        by_type.setdefault(entity.get_entity_type() or "Entity", []).append(entity)

    selected: List[EntityNode] = []
    round_index = 0
    # Typen in Erstauftrittsreihenfolge — deterministisch und ohne stille
    # Bevorzugung alphabetisch frueher Bezeichnungen.
    while len(selected) < max_agents:
        added_this_round = False
        for bucket in by_type.values():
            if round_index >= len(bucket):
                continue
            selected.append(bucket[round_index])
            added_this_round = True
            if len(selected) >= max_agents:
                break
        if not added_this_round:
            break
        round_index += 1

    return selected


def _phase_read_entities(
    state: SimulationState,
    storage: Any,
    defined_entity_types: Optional[List[str]],
    max_agents: Optional[int],
    progress_callback: Optional[Callable] = None,
    degradations: Optional[DegradationCollector] = None,
):
    """Phase 1: Entities aus dem Graphen lesen + filtern + cappen.

    Aktualisiert ``state.entities_count`` und ``state.entity_types`` als
    Seiteneffekt; gibt das ``FilteredEntities``-Objekt zurück.
    """
    if progress_callback:
        progress_callback("reading", 0, "Connecting to graph...")

    if not storage:
        raise ValueError("storage (GraphStorage) is required for prepare_simulation")
    reader = EntityReader(storage)

    if progress_callback:
        progress_callback("reading", 30, "Reading node data...")

    filtered = reader.filter_defined_entities(
        graph_id=state.graph_id,
        defined_entity_types=defined_entity_types,
        enrich_with_edges=True,
    )

    # Issue #1034: entity_type-Filter (label-technisch) findet auch
    # Entitäten ohne menschlichen Träger — "USA" (Country), "Agora"
    # (Product) usw. Der Eignungsfilter schließt sie vor dem
    # max_agents-Cap aus, damit sie weder zählen noch generiert werden.
    eligibility = filter_eligible_entities(filtered.entities, degradations=degradations)
    if eligibility.exclusions:
        filtered.entities = eligibility.eligible
        filtered.filtered_count = len(filtered.entities)
        filtered.entity_types = {
            entity.get_entity_type() or "Entity" for entity in filtered.entities
        }

    # Issue #1177: Vor dem Cap deduplizieren. Mehrfachnennungen derselben
    # Stakeholdergruppe belegten sonst die begrenzten Persona-Plaetze und
    # verdraengten tatsaechlich verschiedene Gruppen.
    deduped, duplicate_count = _dedupe_entities(filtered.entities)
    if duplicate_count:
        logger.info(
            "Persona-Kandidaten: %d Dublette(n) vor dem Cap entfernt "
            "(%d → %d Entitaeten)",
            duplicate_count,
            len(filtered.entities),
            len(deduped),
        )
        filtered.entities = deduped
        filtered.filtered_count = len(deduped)

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
        and max_agents > 0
        and len(filtered.entities) > max_agents
    ):
        logger.info(
            f"Capping agent count at {max_agents} "
            f"(originally {len(filtered.entities)} entities)"
        )
        capped = _cap_entities_across_types(filtered.entities, max_agents)
        # Issue #1247: Was der Cap wegschneidet, ist die Reserve. Die
        # typunabhaengige Eignungspruefung faellt erst im
        # Persona-Generierungsaufruf, also *nach* dem Cap — ohne Reservepool
        # bliebe jeder dort abgelehnte Platz ersatzlos leer und der
        # konfigurierte max_agents-Wert wuerde unterschritten.
        selected_uuids = {entity.uuid for entity in capped}
        filtered.reserve_entities = [
            entity for entity in filtered.entities if entity.uuid not in selected_uuids
        ]
        filtered.entities = capped
        filtered.filtered_count = len(filtered.entities)
        filtered.entity_types = {
            entity.get_entity_type() or "Entity" for entity in filtered.entities
        }

    state.entities_count = filtered.filtered_count
    state.entity_types = list(filtered.entity_types)

    if progress_callback:
        progress_callback(
            "reading", 100,
            f"Completed, total {filtered.filtered_count} entities",
            current=filtered.filtered_count,
            total=filtered.filtered_count,
        )

    return filtered


def _phase_generate_profiles(
    state: SimulationState,
    storage: Any,
    filtered,
    sim_dir: str,
    *,
    llm_model: Optional[str],
    llm_runtime: Optional[LlmRuntimeInput] = None,
    language: Optional[str],
    run_id: Optional[str] = None,
    use_llm_for_profiles: bool,
    parallel_profile_count: int,
    progress_callback: Optional[Callable] = None,
    quota_plan: Optional[PersonaQuotaPlan] = None,
    persona_floor: int = MIN_PERSONA_TABLE_ROWS,
    max_agents: Optional[int] = None,
    degradations: Optional[DegradationCollector] = None,
) -> Tuple[List[Any], List[Any]]:
    """Phase 2: OASIS-Profiles generieren und im Sim-Dir ablegen.

    Aktualisiert ``state.profiles_count`` als Seiteneffekt und gibt ein
    Tuple ``(profiles, expanded_entities)`` zurück: die Liste der
    generierten Profile sowie die auf die Quota expandierte
    Entity-Liste, die Phase 3 weiterverarbeitet.

    Sub-Slice 20b — Quota-Erzwingung: wenn ``quota_plan`` gesetzt ist,
    wird ``filtered.entities`` vor der Generation per
    ``_expand_entities_for_quota`` auf die Quota expandiert (Round-Robin
    auf zu kleinen Pools). Ohne Plan bleibt das Verhalten "1 Persona pro
    Entity" unverändert.
    """
    entities = _expand_entities_for_quota(filtered.entities, quota_plan)
    if quota_plan is None:
        entities = _apply_persona_floor_to_entities(entities, minimum=persona_floor)
    # Issue #1034: Der Nenner des Fortschrittszählers kommt aus derselben
    # Funktion, die auch die Preview-Antwort füllt. Vorher stand hier
    # ``len(entities)`` — richtig, aber eben nur hier: die UI bekam den
    # Vor-Floor-Wert aus einer zweiten Berechnung und zeigte „22 / 7“.
    total_entities = compute_persona_target(
        len(filtered.entities),
        max_agents=max_agents,
        quota_plan=quota_plan,
        floor=persona_floor,
    ).persona_target_count

    if progress_callback:
        progress_callback(
            "generating_profiles", 0,
            "Starting generation...",
            current=0,
            total=total_entities,
        )

    # Pass graph_id to enable graph retrieval functionality, get richer context.
    # Per-simulation overrides for model + language come from API request.
    # Issue #215: Branchenverteilung-Plan für LLM-Prompt — Default Destatis WZ 2008
    # (IT-Cap ≤ 12 %). total_entities als Pool-Größe für proportionale Verteilung.
    industry_plan = default_dach_industry_quota(max(total_entities, 1))

    # ``require`` folgt dem expliziten Nutzerwunsch: nur wenn LLM-Personas
    # verlangt sind, ist eine fehlende Route ein Fehler. Bei
    # ``use_llm_for_profiles=False`` ist regelbasiert das gewollte Ergebnis.
    api_key, base_url, provider_type = _resolve_llm_connection(
        llm_runtime, require=use_llm_for_profiles
    )

    generator = OasisProfileGenerator(
        api_key=api_key,
        base_url=base_url,
        provider_type=provider_type,
        storage=storage,
        graph_id=state.graph_id,
        model_name=llm_model,
        language=language,
        industry_quota_plan=industry_plan,
        # Budget-Enforcement (#984): run-gebundene LLM-Calls statt budgetfrei.
        run_id=run_id,
    )

    def profile_progress(current, total, msg):
        if progress_callback:
            progress_callback(
                "generating_profiles",
                int(current / total * 100),
                msg,
                current=current,
                total=total,
                item_name=msg,
            )

    # Set real-time save file path (prefer Reddit JSON format)
    realtime_output_path: Optional[str] = None
    realtime_platform = "reddit"
    if state.enable_reddit:
        realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
        realtime_platform = "reddit"
    elif state.enable_twitter:
        realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
        realtime_platform = "twitter"

    profiles = generator.generate_profiles_from_entities(
        entities=entities,
        use_llm=use_llm_for_profiles,
        progress_callback=profile_progress,
        graph_id=state.graph_id,
        parallel_count=parallel_profile_count,
        realtime_output_path=realtime_output_path,
        output_platform=realtime_platform,
        # Issue #1034: Der Parameter existiert seit #1029 (Slice 12,
        # regelbasierte Fallback-Profile), wurde aus dem produktiven
        # Prepare-Pfad aber nie gefüllt — ``_report_persona_degradation``
        # lief damit nie. Ohne diese Zeile bleibt die Meldung dort tot.
        degradations=degradations,
        # Issue #1247: Nachrücker für Kandidaten, die der Generator als nicht
        # personenfähig zurückweist.
        reserve_entities=getattr(filtered, "reserve_entities", None),
    )

    state.profiles_count = len(profiles)

    # Save Profile files (Note: Twitter uses CSV format, Reddit uses JSON format)
    # Reddit has been saved in real-time during generation, save once more here to ensure completeness
    if progress_callback:
        progress_callback(
            "generating_profiles", 95,
            "Saving Profile files...",
            current=total_entities,
            total=total_entities,
        )

    if state.enable_reddit:
        generator.save_profiles(
            profiles=profiles,
            file_path=os.path.join(sim_dir, "reddit_profiles.json"),
            platform="reddit",
        )

    if state.enable_twitter:
        # Twitter uses CSV format! This is OASIS requirement
        generator.save_profiles(
            profiles=profiles,
            file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
            platform="twitter",
        )

    if progress_callback:
        progress_callback(
            "generating_profiles", 100,
            f"Completed, total {len(profiles)} Profiles",
            current=len(profiles),
            total=len(profiles),
        )

    return profiles, entities


def _phase_generate_config(
    manager: SimulationManager,
    state: SimulationState,
    simulation_id: str,
    simulation_requirement: str,
    document_text: str,
    *,
    expanded_entities: List[Any],
    llm_model: Optional[str],
    llm_runtime: Optional[LlmRuntimeInput] = None,
    language: Optional[str],
    run_id: Optional[str] = None,
    use_llm: bool = True,
    progress_callback: Optional[Callable] = None,
    quota_plan: Optional[PersonaQuotaPlan] = None,
) -> None:
    """Phase 3: Simulation-Config per LLM erzeugen + atomar persistieren.

    Aktualisiert ``state.config_generated`` und ``state.config_reasoning``
    als Seiteneffekt; speichert die Config über den ``ArtifactStore``.

    Sub-Slice 22 (Gemini-Followup auf 20a): wenn ``quota_plan`` gesetzt
    ist, wird er als Top-Level-Key ``quota_plan`` in
    ``simulation_config.json`` mitgeschrieben — der Restart-Pfad in
    ``runs.py`` liest ihn von dort über ``_parse_quota_plan(config)``
    wieder ein. Ohne Persistenz war der Plan beim Restart immer ``None``.
    """
    if progress_callback:
        progress_callback(
            "generating_config", 0,
            "Analyzing simulation requirements...",
            current=0,
            total=3,
        )

    api_key, base_url, provider_type = _resolve_llm_connection(llm_runtime, require=use_llm)

    config_generator = SimulationConfigGenerator(
        api_key=api_key,
        base_url=base_url,
        provider_type=provider_type,
        model_name=llm_model,
        language=language,
        # Budget-Enforcement (#984): run-gebundene LLM-Calls statt budgetfrei.
        run_id=run_id,
    )

    if progress_callback:
        progress_callback(
            "generating_config", 30,
            "Calling LLM to generate config...",
            current=1,
            total=3,
        )

    sim_params = config_generator.generate_config(
        simulation_id=simulation_id,
        project_id=state.project_id,
        graph_id=state.graph_id,
        simulation_requirement=simulation_requirement,
        document_text=document_text,
        entities=expanded_entities,
        enable_twitter=state.enable_twitter,
        enable_reddit=state.enable_reddit,
    )

    if progress_callback:
        progress_callback(
            "generating_config", 70,
            "Saving config files...",
            current=2,
            total=3,
        )

    # Save config files (atomic via store — fixes prior non-atomic write).
    config_payload = json.loads(sim_params.to_json())
    if quota_plan is not None:
        config_payload["quota_plan"] = quota_plan.model_dump()
    manager._store.write_json(
        simulation_id,
        "simulation_config",
        config_payload,
    )

    state.config_generated = True
    state.config_reasoning = sim_params.generation_reasoning

    if progress_callback:
        progress_callback(
            "generating_config", 100,
            "Config generation completed",
            current=3,
            total=3,
        )


def _expand_entities_for_quota(
    entities: List[Any],
    plan: Optional[PersonaQuotaPlan],
) -> List[Any]:
    """Sub-Slice 20b — Generator-Erzwingung.

    Mappt einen Entity-Pool auf den Soll-Plan: pro ``plan.targets[seg]``
    werden so viele Entities zurückgegeben, wie die Quote vorgibt.
    Round-Robin durch den Segment-Pool, wenn der Pool kleiner ist als
    die Quote — keine Synth-Entities (würde semantische KG-Verankerung
    aufgeben). Wenn ein Plan-Segment im Pool nicht existiert, wird ein
    klarer ``ValueError`` geworfen, statt heimlich zu reduzieren.

    Backwards-Compat: ``plan=None`` → Pool wird durchgereicht.

    Hinweis zur Persona-Identität: Bei Replikation derselben Entity
    bekommt jede Persona einen eigenen ``user_id`` (durch Position in
    der Generator-Loop) und nutzt die bestehende Display-Name-/User-Name-
    Dedup-Logik im Generator (s. ``oasis_profile_generator.py`` Z. 1269+),
    die LLM-Name-Kollisionen abfängt.
    """
    if plan is None:
        return entities

    by_segment: Dict[str, List[Any]] = {}
    for e in entities:
        seg = e.get_entity_type() or "Entity"
        by_segment.setdefault(seg, []).append(e)

    expanded: List[Any] = []
    for segment, target in plan.targets.items():
        pool = by_segment.get(segment, [])
        if not pool:
            available = sorted(by_segment.keys())
            raise ValueError(
                f"PersonaQuotaPlan verlangt {target} Personas im Segment "
                f"'{segment}', aber der Entity-Pool enthält keine Entity "
                f"mit entity_type='{segment}'. Verfügbare Segmente: "
                f"{available or '(leer)'}. Entweder Plan anpassen oder "
                f"Ontologie um den fehlenden Type erweitern."
            )
        for i in range(target):
            expanded.append(pool[i % len(pool)])

    return expanded


def _apply_persona_floor_to_entities(
    entities: List[Any],
    *,
    minimum: int = MIN_PERSONA_TABLE_ROWS,
) -> List[Any]:
    """Ensure the generation pool can yield the report persona-table floor.

    The generator creates a distinct profile per input position. When the graph
    has fewer entities than the output contract requires, repeat the existing
    entity pool in deterministic round-robin order instead of inventing
    synthetic entities.
    """
    if not entities or len(entities) >= minimum:
        return entities

    logger.info(
        "persona-floor angewendet: generation_pool=%s floor=%s",
        len(entities),
        minimum,
    )
    return [entities[i % len(entities)] for i in range(minimum)]


def _apply_persona_floor_to_quota_plan(
    plan: Optional[PersonaQuotaPlan],
    *,
    minimum: int = MIN_PERSONA_TABLE_ROWS,
) -> Optional[PersonaQuotaPlan]:
    """Raise an explicit quota plan to the report persona floor.

    Segment proportions are preserved via largest-remainder allocation. The
    adjusted plan is used consistently for generation, validation and persisted
    config, so downstream quota checks stay exact.
    """
    if plan is None or plan.total >= minimum:
        return plan

    raw_targets = {
        segment: (target / plan.total) * minimum
        for segment, target in plan.targets.items()
    }
    targets = {
        segment: max(1, int(raw_value))
        for segment, raw_value in raw_targets.items()
    }
    remaining = minimum - sum(targets.values())
    if remaining > 0:
        ranked_segments = sorted(
            raw_targets,
            key=lambda segment: (
                raw_targets[segment] - int(raw_targets[segment]),
                plan.targets[segment],
                segment,
            ),
            reverse=True,
        )
        for segment in ranked_segments[:remaining]:
            targets[segment] += 1

    logger.info(
        "persona-floor angewendet: quota_total=%s floor=%s targets=%s",
        plan.total,
        minimum,
        targets,
    )
    return PersonaQuotaPlan(targets=targets, total=minimum)


def compute_persona_target(
    entity_count: int,
    *,
    max_agents: Optional[int] = None,
    quota_plan: Optional[PersonaQuotaPlan] = None,
    floor: Optional[int] = None,
) -> PersonaTargetContract:
    """Bestimmt das Persona-Generierungsziel — eine Quelle für beide Pfade.

    ``entity_count`` ist die Entitätenzahl nach Eignungsfilter und
    ``max_agents``-Cap. Der wirksame Floor ist ``MIN_PERSONA_TABLE_ROWS``,
    gedeckelt durch ein gesetztes ``max_agents > 0`` (Nutzer-Wunsch schlägt
    Contract). Wer den Floor bereits aufgelöst hat — der Orchestrator tut
    das für die Generierung —, reicht ihn als ``floor`` herein, statt ihn
    hier ein zweites Mal berechnen zu lassen.

    Mit ``quota_plan`` ist das Ziel dessen ``total`` nach
    ``_apply_persona_floor_to_quota_plan``; ohne Plan ist es
    ``max(entity_count, floor)`` — dasselbe, was
    ``_apply_persona_floor_to_entities`` auf den Entity-Pool anwendet.

    Ein leerer Pool bleibt leer: ``_apply_persona_floor_to_entities``
    skaliert nichts hoch, wenn es nichts zu wiederholen gibt. Ein Ziel von
    50 bei null Entitäten wäre genau die Divergenz zwischen Zähler und
    Nenner, die dieser Contract beseitigen soll.

    ``api/simulation_prepare.py`` (Preview) und ``_phase_generate_profiles``
    (Laufpfad) rufen exakt diese Funktion.
    """
    effective_floor = MIN_PERSONA_TABLE_ROWS if floor is None else floor
    if floor is None and max_agents is not None and max_agents > 0:
        effective_floor = min(effective_floor, max_agents)

    if entity_count == 0:
        # Vor dem Quota-Zweig, nicht dahinter: auch mit Plan gibt es nichts
        # zu wiederholen. `_expand_entities_for_quota` wirft hier ohnehin,
        # und der Orchestrator bricht bei `filtered_count == 0` ab — ein
        # Nenner von 50 wäre eine Zahl, die nie erreicht werden kann.
        target = 0
        floor_applied = False
    elif quota_plan is not None:
        adjusted_plan = _apply_persona_floor_to_quota_plan(
            quota_plan, minimum=effective_floor
        )
        target = adjusted_plan.total if adjusted_plan is not None else quota_plan.total
        # Mit Plan sagt ein Vergleich gegen `entity_count` nichts über den
        # Floor aus: 80 Entitäten mit einer Quota von 6 werden angehoben,
        # lägen aber unter der Entitätenzahl. Maßgeblich ist allein, ob der
        # Plan unter dem Floor lag.
        floor_applied = quota_plan.total < effective_floor
    else:
        target = max(entity_count, effective_floor)
        floor_applied = entity_count < effective_floor

    return PersonaTargetContract(
        entity_count=entity_count,
        persona_target_count=target,
        floor_applied=floor_applied,
        floor=effective_floor,
    )


def _validate_persona_quota(
    plan: PersonaQuotaPlan,
    profiles: List[OasisAgentProfile],
) -> None:
    """Validate actual persona segment counts against ``plan``.

    Raises ``pydantic.ValidationError`` (propagates to caller) when:
    - A required segment is missing or has wrong count (tolerance=0).
    - Profiles contain segments not declared in the plan.
    """
    actual_counts: Dict[str, int] = {}
    for p in profiles:
        seg = getattr(p, "segment", None)
        if seg:
            actual_counts[seg] = actual_counts.get(seg, 0) + 1
    PersonaQuotaActual.model_validate(
        {
            "plan": plan.model_dump(),
            "actual_counts": actual_counts,
            "tolerance": 0,
        }
    )


class PrepareCancelledError(Exception):
    """Signalisiert kooperativen Abbruch während ``prepare_simulation()``.

    Issue B2 (PLAN.md „Abbrechen & Pause“): das Cancel-Flag wird an den
    Phasengrenzen geprüft (analog ``report_agent/workflow.py::_is_cancel_requested``
    an den Stage-Boundaries). Anders als ``BudgetExceededError`` ist ein
    Nutzerabbruch kein Fehler — deshalb eine eigene Exception statt eines
    ``ValueError``, damit der generische ``except Exception``-Zweig unten
    (FSM → FAILED) sie nicht mit einem echten Fehlschlag verwechselt.

    Trägt den zuletzt gespeicherten ``SimulationState``, damit der Aufrufer
    (``api/simulation_prepare.py::_make_prepare_job``) den Abbruch-Endzustand
    bauen kann, ohne die Simulation erneut zu laden.
    """

    def __init__(self, state: "SimulationState") -> None:
        super().__init__(f"prepare_simulation cancelled for {state.simulation_id}")
        self.state = state


def prepare_simulation(
    manager: SimulationManager,
    simulation_id: str,
    simulation_requirement: str,
    document_text: str,
    *,
    defined_entity_types: Optional[List[str]] = None,
    use_llm_for_profiles: bool = True,
    progress_callback: Optional[Callable] = None,
    parallel_profile_count: Optional[int] = None,
    storage: Any = None,
    llm_model: Optional[str] = None,
    llm_runtime: Optional[LlmRuntimeInput] = None,
    language: Optional[str] = None,
    max_agents: Optional[int] = None,
    quota_plan: Optional[PersonaQuotaPlan] = None,
    run_id: Optional[str] = None,
    degradations: Optional[DegradationCollector] = None,
) -> SimulationState:
    """Orchestrator für die drei Prepare-Phasen.

    Setzt FSM-Status PREPARING vor Phase 1, READY nach Phase 3, FAILED bei
    jeder Exception. ``state.error`` wird im Fehlerfall mit der Exception-
    Message gesetzt; die Exception wird nach State-Update weiter geworfen.

    Zwischen den drei Phasen wird das Cancel-Flag geprüft (``run_id``,
    ``services/sim/cancel_flag.py``) — kooperativer Abbruch analog
    ``report_agent/workflow.py``. Bereits geschriebene Artefakte (Profildatei
    aus Phase 2, Entity-Zählung aus Phase 1) bleiben unangetastet stehen;
    nur der FSM-Status wechselt auf ``CANCELLED_PARTIAL`` statt ``READY``.
    """
    from .simulation_manager import SimulationStatus
    from .sim.cancel_flag import is_cancel_requested

    state = manager._load_simulation_state(simulation_id)
    if not state:
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    def _raise_if_cancelled() -> None:
        if run_id and is_cancel_requested(run_id):
            manager._set_status(state, SimulationStatus.CANCELLED_PARTIAL)
            raise PrepareCancelledError(state)

    try:
        manager._set_status(state, SimulationStatus.PREPARING)

        sim_dir = manager._get_simulation_dir(simulation_id)

        _raise_if_cancelled()

        # Phase 1: Read & filter entities
        filtered = _phase_read_entities(
            state,
            storage,
            defined_entity_types,
            max_agents,
            progress_callback=progress_callback,
            degradations=degradations,
        )

        if filtered.filtered_count == 0:
            raise ValueError(
                "No entities matching criteria found, "
                "check if graph is correctly constructed"
            )

        # Resolve parallel_profile_count: None → env AGORA_PARALLEL_PERSONA_COUNT → 10.
        # Auflösung hier (einmalig), damit _phase_generate_profiles ein konkretes int erhält.
        if parallel_profile_count is None:
            parallel_profile_count = int(
                _get_settings().effective_value('AGORA_PARALLEL_PERSONA_COUNT')
            )

        # Effektiver Persona-Floor (Task: 50-Personas-Minimum dynamisch):
        # Der Report-Contract verlangt MIN_PERSONA_TABLE_ROWS, aber ein
        # explizit kleineres max_agents gewinnt (Nutzer-Wunsch schlägt
        # Contract). Der Wert wird im State persistiert, damit das
        # Report-Gate in workflow.py denselben Floor prüft.
        persona_floor = MIN_PERSONA_TABLE_ROWS
        if max_agents is not None and max_agents > 0:
            persona_floor = min(persona_floor, max_agents)
        state.persona_floor = persona_floor
        manager._save_simulation_state(state)

        quota_plan = _apply_persona_floor_to_quota_plan(
            quota_plan, minimum=persona_floor
        )

        _raise_if_cancelled()

        # Phase 2: Generate Agent Profiles
        profiles, expanded_entities = _phase_generate_profiles(
            state,
            storage,
            filtered,
            sim_dir,
            llm_model=llm_model,
            llm_runtime=llm_runtime,
            language=language,
            use_llm_for_profiles=use_llm_for_profiles,
            parallel_profile_count=parallel_profile_count,
            progress_callback=progress_callback,
            quota_plan=quota_plan,
            persona_floor=persona_floor,
            max_agents=max_agents,
            run_id=run_id,
            degradations=degradations,
        )

        # Review-Finding (PR #1371, Befund 2): der Cancel-Check MUSS vor der
        # Quota-Validierung laufen. Bricht die Persona-Generierung
        # kooperativ mitten in der as_completed-Schleife ab
        # (oasis_profile_generator.py), liefert sie eine gekürzte
        # Profilliste zurück — bei gesetztem quota_plan (tolerance=0)
        # scheitert ``_validate_persona_quota`` daran zwangsläufig mit
        # ``ValidationError``. Lief die Prüfung zuerst, landete genau der
        # Fall, für den dieses Feature existiert, im generischen
        # except-Zweig unten und endete als FAILED statt als der
        # kooperative Abbruch, den der Nutzer angefordert hat.
        _raise_if_cancelled()

        # Optional quota check: ValidationError propagates → FAILED state.
        if quota_plan is not None:
            _validate_persona_quota(quota_plan, profiles)

        # Phase 3: LLM-driven config generation
        _phase_generate_config(
            manager,
            state,
            simulation_id,
            simulation_requirement,
            document_text,
            expanded_entities=expanded_entities,
            llm_model=llm_model,
            llm_runtime=llm_runtime,
            language=language,
            use_llm=use_llm_for_profiles,
            progress_callback=progress_callback,
            quota_plan=quota_plan,
            run_id=run_id,
        )

        # Run scripts remain in backend/scripts/ directory, no longer copy to
        # simulation directory. When starting simulation, simulation_runner
        # runs scripts from scripts/ directory.

        # Issue #1419: ``BLOCKING`` heisst laut
        # ``pipeline_degradation_contract`` woertlich, dass der Schritt den
        # Zustand "bereit" nicht erreichen darf, auch wenn technisch kein
        # Fehler aufgetreten ist. Ohne dieses Gate war das eine
        # Absichtserklaerung: eine Vorbereitung, in der keine einzige Persona
        # vom Modell kam, ging als READY hinaus und war regulaer startbar.
        # Der Collector bleibt im Task-Ergebnis erhalten — dort steht die
        # Begruendung, die die Oberflaeche anzeigt.
        blocking = (
            [event for event in degradations.report().events if event.is_blocking]
            if degradations is not None
            else []
        )
        if blocking:
            state.error = " ".join(event.detail for event in blocking)
            manager._set_status(state, SimulationStatus.FAILED)
            logger.error(
                "Simulation preparation blocked by degradation: %s, kinds=%s",
                simulation_id,
                ", ".join(event.kind.value for event in blocking),
            )
            return state

        manager._set_status(state, SimulationStatus.READY)

        logger.info(
            f"Simulation preparation completed: {simulation_id}, "
            f"entities={state.entities_count}, profiles={state.profiles_count}"
        )

        return state

    except PrepareCancelledError:
        # FSM steht bereits auf CANCELLED_PARTIAL (in _raise_if_cancelled
        # gesetzt) — kein Fehlschlag, also nicht in den FAILED-Zweig unten.
        logger.info(
            "Simulation preparation cancelled by user: %s (run_id=%s)",
            simulation_id,
            run_id,
        )
        raise
    except Exception as exc:
        logger.error(
            f"Simulation preparation failed: {simulation_id}, error={exc}"
        )
        logger.error(traceback.format_exc())
        state.error = str(exc)
        manager._set_status(state, SimulationStatus.FAILED)
        raise


__all__ = [
    "prepare_simulation",
    "PrepareCancelledError",
    "compute_persona_target",
    "_apply_persona_floor_to_entities",
    "_apply_persona_floor_to_quota_plan",
    "_validate_persona_quota",
]
