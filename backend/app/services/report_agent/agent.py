import re
from contextlib import nullcontext
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional

from pydantic import ValidationError

from ...utils.llm_client import LLMClient
from ..confidence_calculator import compute_confidence
from ..evidence_binder import bind_evidence_to_claim, detect_contradiction_penalty
from ..evidence_identity import build_producer_key
from .evidence import (
    build_seed_document_anchor,
    degrade_sections_for_violations,
    has_agent_grounded_evidence,
    init_evidence_map,
    normalize_claims_for_contract,
    normalize_sections_for_contract,
    record_evidence_item,
    register_evidence_record,
    resolve_embedder,
)
from .evidence_candidates import EvidenceCandidatePool
from .manager import ReportManager
from .planning import plan_outline as plan_outline_impl
from .search_dedup import (
    EmptySearchRegistry,
    is_empty_result,
    is_search_tool,
    query_of,
    registry_for,
)
from .postprocess_timing import PostprocessPhaseTracker
from .schemas import CURRENT_SCHEMA_VERSION, EvidenceMapModel, normalize_persisted_evidence_map
from .sections import (
    attach_provenance,
    atomize_claim_chunk,
    build_source_id_anchor,
    is_atomic_claim,
    is_claim_candidate,
    sample_actions_timeseries,
    section_dedup_check,
    truncate_text,
)
from ..web_tools import WebToolsService
from ...utils.logger import get_logger
from ...models.report import (
    EvidenceItem,
    Report,
    ReportClaim,
    ReportOutline,
    ReportSection,
)
from ..report_logger import ReportLogger, ReportConsoleLogger
from ..tool_validation import VALID_TOOL_NAMES  # noqa: F401  # re-exported for backwards-compat
from .tools import (
    describe_tools,
    define_tools,
    execute_tool_call,
    get_openai_tools_schema,
    is_valid_tool_call,
    parse_tool_calls,
)
from .section_pipeline import SectionEvidenceOutcome
from .workflow import chat as chat_impl, generate_report as generate_report_impl, generate_section_react as generate_section_react_impl
from .prompts import (
    CHAT_OBSERVATION_SUFFIX,
    CHAT_SYSTEM_PROMPT_TEMPLATE,
    REACT_FORCE_FINAL_MSG,
    REACT_INSUFFICIENT_TOOLS_MSG,
    REACT_INSUFFICIENT_TOOLS_MSG_ALT,
    REACT_OBSERVATION_TEMPLATE,
    REACT_TOOL_LIMIT_MSG,
    REACT_UNUSED_TOOLS_HINT,
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    SECTION_USER_PROMPT_TEMPLATE,
)
from ..graph_tools import (
    GraphToolsService,
    SearchResult,
    InsightForgeResult,
    PanoramaResult,
    InterviewResult
)
# Issue #1152: Zugriff auf die positionsparallelen Provenance-Listen der
# Retrieval-DTOs. Der Helper toleriert leere Listen (Altgraphen), ein `zip`
# über eine leere Liste würde die Fakten still verschlucken.
from ..graph.graph_dtos import provenance_at

logger = get_logger('agora.report_agent')

# S5: diese Item-Typen sind Modell-Output, keine Evidence. Sie dürfen
# nicht im `evidence`-Array eines Claims stehen, sondern im separaten
# `audit_trail`-Feld.
FORBIDDEN_EVIDENCE_TYPES = frozenset({
    "model_generated_inference",
    "section_synthesis",
})

#: Platzhalter, den GraphToolsService für stumme Interview-Plattformen einsetzt
#: — ein Interview, das nur daraus besteht, ist fehlgeschlagen, keine Evidence.
_INTERVIEW_NO_RESPONSE = "(No response from this platform)"
_INTERVIEW_STRUCTURE_RE = re.compile(r"\[(?:Twitter|Reddit) Platform Response\]")


def _remap_claim_bindings(
    claims: List[Dict[str, Any]],
    id_remap: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Zieht Claim-Bindungen auf umgeschlüsselte Evidence-IDs nach (#1154).

    Zwei Bindungen, die danach auf dieselbe Quelle zeigen, werden zu einer
    zusammengeführt — sonst zählte die Confidence denselben Beleg doppelt.
    """
    remapped: List[Dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            remapped.append(claim)
            continue
        bindings = claim.get("evidence")
        if not isinstance(bindings, list):
            remapped.append(claim)
            continue
        merged: Dict[str, Dict[str, Any]] = {}
        others: List[Any] = []
        for binding in bindings:
            if not isinstance(binding, dict) or not binding.get("evidence_id"):
                others.append(binding)
                continue
            current = str(binding["evidence_id"])
            target = id_remap.get(current, current)
            binding["evidence_id"] = target
            merged.setdefault(target, binding)
        claim["evidence"] = others + list(merged.values())
        remapped.append(claim)
    return remapped


class ReportAgent:
    """Simulation report generation agent."""
    
    # Maximum tool call count (per section)
    MAX_TOOL_CALLS_PER_SECTION = 5

    # Maximum reflection rounds
    MAX_REFLECTION_ROUNDS = 3

    # Maximum tool call count in conversation
    MAX_TOOL_CALLS_PER_CHAT = 2

    ReportLogger = ReportLogger
    ReportConsoleLogger = ReportConsoleLogger

    SECTION_SYSTEM_PROMPT_TEMPLATE = SECTION_SYSTEM_PROMPT_TEMPLATE
    SECTION_USER_PROMPT_TEMPLATE = SECTION_USER_PROMPT_TEMPLATE
    REACT_OBSERVATION_TEMPLATE = REACT_OBSERVATION_TEMPLATE
    REACT_INSUFFICIENT_TOOLS_MSG = REACT_INSUFFICIENT_TOOLS_MSG
    REACT_INSUFFICIENT_TOOLS_MSG_ALT = REACT_INSUFFICIENT_TOOLS_MSG_ALT
    REACT_TOOL_LIMIT_MSG = REACT_TOOL_LIMIT_MSG
    REACT_UNUSED_TOOLS_HINT = REACT_UNUSED_TOOLS_HINT
    REACT_FORCE_FINAL_MSG = REACT_FORCE_FINAL_MSG
    CHAT_SYSTEM_PROMPT_TEMPLATE = CHAT_SYSTEM_PROMPT_TEMPLATE
    CHAT_OBSERVATION_SUFFIX = CHAT_OBSERVATION_SUFFIX
    
    def __init__(
        self,
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        graph_tools: Optional[GraphToolsService] = None,
        model_name: Optional[str] = None,
    ):
        """
        Initialize Report Agent

        Args:
            graph_id: Graph ID
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description
            llm_client: LLM client (optional — overrides model_name if given)
            graph_tools: Graph tools service (optional, requires external GraphStorage injection)
            model_name: per-report model override (e.g. "deepseek-v3.2:cloud")
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement

        if llm_client is not None:
            self.llm = llm_client
        else:
            self.llm = LLMClient(model=model_name) if model_name else LLMClient()

        # Optional live-web tools (Tavily). Disabled silently when no API key.
        self.web_tools = WebToolsService()
        if graph_tools is None:
            raise ValueError(
                "graph_tools (GraphToolsService) is required. "
                "Create it via GraphToolsService(storage=...) and pass it in."
            )
        self.graph_tools = graph_tools
        
        # Tool definitions
        self.tools = self._define_tools()

        # Logger (initialized in generate_report)
        self.report_logger: Optional[ReportLogger] = None
        # Console logger (initialized in generate_report)
        self.console_logger: Optional[ReportConsoleLogger] = None
        self.evidence_map: Optional[Dict[str, Any]] = None
        self._active_section_evidence: List[Dict[str, Any]] = []
        self._active_section_unresolved_evidence: List[Dict[str, Any]] = []
        self._current_section_index: Optional[int] = None

        logger.info(f"ReportAgent initialization complete: graph_id={graph_id}, simulation_id={simulation_id}")

    def _init_evidence_map(self, report_id: str) -> None:
        self.evidence_map = init_evidence_map(
            report_id=report_id,
            simulation_id=self.simulation_id,
            global_evidence=self._collect_simulation_evidence_items(),
        )

    def _truncate(self, text: str, limit: int = 300) -> str:
        return truncate_text(text, limit)

    def _record_evidence_item(self, item: Dict[str, Any]) -> None:
        enriched = attach_provenance(dict(item))
        if self.evidence_map is None:
            self._active_section_unresolved_evidence.append(enriched)
            return
        try:
            record = register_evidence_record(
                self.evidence_map,
                enriched,
                scope_id=self.simulation_id,
            )
        except ValidationError as exc:
            # Ein einzelnes defektes Tool-Item darf die Section nicht abbrechen;
            # es bleibt als unresolved sichtbar statt still zu verschwinden.
            # producer_key bewusst nicht loggen: web:-Keys tragen volle URLs,
            # die Query-Secrets enthalten können (CodeRabbit PR #1151, Major).
            logger.warning(
                "register_evidence_record: Item verworfen (type=%r, %d Validierungsfehler)",
                enriched.get("type"), len(exc.errors()),
            )
            self._active_section_unresolved_evidence.append(enriched)
            return
        if record is None:
            self._active_section_unresolved_evidence.append(enriched)
            return
        self._active_section_evidence = record_evidence_item(
            self._active_section_evidence,
            record,
        )

    def _try_get_embedder(self) -> Optional[Callable[[str], List[float]]]:
        cached = getattr(self, "_embed_cache", "missing")
        embed_fn = resolve_embedder(cached=cached, logger=logger)
        self._embed_cache = embed_fn
        return embed_fn

    @staticmethod
    def _sample_actions_timeseries(
        actions: List[Dict[str, Any]], k: int = 8
    ) -> List[Dict[str, Any]]:
        return sample_actions_timeseries(actions, k)

    def _collect_simulation_evidence_items(self) -> List[Dict[str, Any]]:
        """Collect reusable evidence from existing metrics and simulation actions."""
        try:
            from ..network_analytics import NetworkAnalyticsService
            from ..simulation_runner import SimulationRunner

            actions = SimulationRunner.get_all_actions(self.simulation_id)
            action_dicts = [action.to_dict() for action in actions]
            if not action_dicts:
                return []

            metrics = NetworkAnalyticsService().compute_metrics(
                action_dicts,
                simulation_id=self.simulation_id,
            ).to_dict()
            items: List[Dict[str, Any]] = []
            # S2b: Wenn der Snapshot keinen "ok"-Status hat (z. B. Broadcast-
            # only-Run ohne pairwise Interactions), keine 0er Pseudo-Metriken
            # als Evidence ausweisen. Stattdessen ein einzelnes Status-Item
            # mit klarer Aussage anhängen, damit der Audit-Trail nicht ganz
            # leer ist.
            if metrics.get("status") != "ok":
                items.append(EvidenceItem(
                    type="graph_metric_status",
                    source="simulation_metrics",
                    value=f"status={metrics.get('status')}",
                    snippet=(
                        f"Polarization-Metriken nicht verfügbar "
                        f"(Status: {metrics.get('status')})"
                    ),
                    raw={"metrics": metrics},
                ).to_dict())
                items[-1]["producer_key"] = "simulation-metric:status"
            else:
                metric_fields = (
                    "echo_chamber_index",
                    "cluster_count",
                    "total_interactions",
                    "bridge_agents",
                )
                for field in metric_fields:
                    value = metrics.get(field)
                    if value in (None, [], ""):
                        continue
                    items.append(EvidenceItem(
                        type="graph_metric",
                        source="simulation_metrics",
                        value=f"{field}={value}",
                        snippet=f"{field}: {value}",
                        raw={"metric": field, "value": value, "metrics": metrics},
                    ).to_dict())
                    items[-1]["producer_key"] = f"simulation-metric:{field}"

            sampled_actions = self._sample_actions_timeseries(action_dicts, k=8)
            for action in sampled_actions:
                action_type = action.get("action_type") or "action"
                agent = action.get("agent_name") or f"Agent {action.get('agent_id')}"
                platform = action.get("platform") or "unknown"
                round_num = action.get("round_num")
                items.append(EvidenceItem(
                    type="agent_action",
                    source="simulation_actions",
                    value=action_type,
                    snippet=f"{agent} {action_type} on {platform} in round {round_num}",
                    raw=action,
                ).to_dict())
                action_identity = (
                    action.get("platform"),
                    action.get("round_num"),
                    action.get("agent_id"),
                    action.get("action_type"),
                    action.get("timestamp"),
                )
                if all(value is not None and str(value).strip() for value in action_identity):
                    items[-1]["producer_key"] = "simulation-action:" + ":".join(
                        str(value) for value in action_identity
                    )
            return items
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.warning(f"Failed to collect simulation evidence: {exc}")
            return []

    def _record_tool_evidence(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        structured_result: Any,
        rendered_result: str,
        section_index: int,
    ) -> None:
        # Issue #1191: der einzige Ort, an dem das strukturierte Ergebnis
        # anfaellt — die ReACT-Schleife sieht nur den gerenderten Text. Ein
        # Leertreffer wird hier gemerkt, damit dieselbe Suche im selben
        # Abschnitt nicht mit einem anderen Werkzeug wiederholt wird.
        if is_search_tool(tool_name) and is_empty_result(structured_result):
            registry_for(self).record_empty(query_of(parameters))
        # Kanonische Identität für Fakten aus dem Graphen: der Fakt-Text selbst
        # ist die deterministische Quelle (kein freier LLM-Text), die Query
        # bleibt außen vor — derselbe Fakt über verschiedene Queries ist
        # dieselbe Evidence. Ohne producer_key verwirft
        # register_evidence_record das Item still (report_06f654800817:
        # 0 von ~40 Interview-/Fakten-Items im evidence_index).
        def _graph_fact_item(
            fact: str,
            item_type: str,
            query: str,
            key_prefix: str,
            provenance: Optional[Dict[str, Any]] = None,
        ) -> Optional[Dict[str, Any]]:
            snippet = self._truncate(fact)
            if not snippet:
                return None
            item = {
                "type": item_type,
                "tool_name": tool_name,
                "query": query,
                "snippet": snippet,
                "raw": fact,
                "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                "producer_key": build_producer_key(key_prefix, str(fact).strip()),
            }
            # ADR-0013 / #1154: Trägt der Fakt eine verifizierte Dokumentherkunft
            # (aus #1152), wird er zum Dokumentfakt statt zur Graph-Relation.
            # Identität dann aus der Doc-Herkunft — derselbe Chunk ist dieselbe
            # Quelle, unabhängig vom LLM-formulierten Fakt-Text. Ohne Herkunft
            # bleibt es bei ``graph_relation``: nicht raten (Akzeptanzkriterium 3).
            anchor = build_seed_document_anchor(provenance)
            if anchor:
                item["type"] = "seed_document"
                item["source_id_anchor"] = anchor
                item["producer_key"] = build_producer_key(
                    "seed-doc",
                    str(provenance["document_id"]).strip(),
                    str(provenance.get("chunk_id")),
                )
            return item

        items: List[Dict[str, Any]] = []
        if isinstance(structured_result, InsightForgeResult):
            for position, fact in enumerate(structured_result.semantic_facts[:10]):
                item = _graph_fact_item(
                    fact,
                    "graph_fact",
                    structured_result.query,
                    "graph-fact",
                    provenance_at(structured_result.semantic_facts_provenance, position),
                )
                if item:
                    items.append(item)
            for entity in structured_result.entity_insights[:8]:
                item = {
                    "type": "entity_summary",
                    "tool_name": tool_name,
                    "query": structured_result.query,
                    "snippet": self._truncate(entity.get("summary") or entity.get("name")),
                    "raw": entity,
                    "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                }
                if entity.get("uuid"):
                    item["producer_key"] = f"graph-node:{entity['uuid']}"
                items.append(item)
            for chain in structured_result.relationship_chains[:8]:
                item = _graph_fact_item(chain, "relationship_chain", structured_result.query, "graph-chain")
                if item:
                    items.append(item)
        elif isinstance(structured_result, PanoramaResult):
            for position, fact in enumerate(structured_result.active_facts[:10]):
                item = _graph_fact_item(
                    fact,
                    "graph_fact",
                    structured_result.query,
                    "graph-fact",
                    provenance_at(structured_result.active_facts_provenance, position),
                )
                if item:
                    items.append(item)
            for position, fact in enumerate(structured_result.historical_facts[:6]):
                item = _graph_fact_item(
                    fact,
                    "graph_fact",
                    structured_result.query,
                    "graph-fact",
                    provenance_at(structured_result.historical_facts_provenance, position),
                )
                if item:
                    items.append(item)
        elif isinstance(structured_result, SearchResult):
            for position, fact in enumerate(structured_result.facts[:10]):
                item = _graph_fact_item(
                    fact,
                    "graph_fact",
                    structured_result.query,
                    "graph-fact",
                    provenance_at(structured_result.fact_provenance, position),
                )
                if item:
                    items.append(item)
        elif isinstance(structured_result, InterviewResult):
            # Jede erfolgreiche Interviewantwort wird ein eigenständig
            # referenzierbares Evidence-Item. Identitätsbasis: Section, Topic,
            # Agent, Frage UND Antwort-Hash — gleicher Text verschiedener
            # Agenten kollabiert nicht, zwei Fragen an denselben Agenten
            # bleiben unterscheidbar. source_kind wird via Typ-Mapping
            # agent_quote (simulierte Stakeholder-Stimme, ADR-0002) —
            # deshalb sind quote und persona_stakeholder_group Pflicht.
            topic = (structured_result.interview_topic or "").strip()
            for interview in structured_result.interviews[:10]:
                response = (interview.response or "").strip()
                # GraphToolsService liefert bei stummen Plattformen einen
                # strukturierten Platzhalter-Text — der ist kein Interview
                # und darf nicht als agent_quote-Evidence persistieren
                # (Codex-Review PR #1151, P2).
                substance = _INTERVIEW_STRUCTURE_RE.sub("", response)
                substance = substance.replace(_INTERVIEW_NO_RESPONSE, "").strip()
                if not substance:
                    continue
                # Whitespace-only Werte sind truthy — erst normalisieren, dann
                # Fallback, sonst wirft build_producer_key ValueError.
                agent_name = (interview.agent_name or "").strip() or "unknown-agent"
                question = (interview.question or "").strip() or "no-question"
                stakeholder_group = (
                    (interview.agent_role or "").strip()
                    or (interview.agent_name or "").strip()
                    or "unbekannt"
                )
                quote_source = next(
                    (q.strip() for q in interview.key_quotes if q and q.strip()),
                    response,
                )
                role_family = (
                    getattr(interview, "agent_role_family", None) or ""
                ).strip() or None
                item: Dict[str, Any] = {
                    "type": "agent_interview",
                    "tool_name": tool_name,
                    "query": topic,
                    "snippet": self._truncate(response),
                    "raw": interview.to_dict(),
                    "quote": quote_source[:500],
                    "persona_stakeholder_group": stakeholder_group[:200],
                    "persona_role_family": role_family[:120] if role_family else None,
                    "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                    "producer_key": build_producer_key(
                        f"interview:s{section_index}",
                        topic or "no-topic",
                        agent_name,
                        question,
                        response,
                    ),
                }
                items.append(item)
        elif isinstance(structured_result, dict) and "results" in structured_result:
            for result in (structured_result.get("results") or [])[:8]:
                item = {
                    "type": "web_search_result",
                    "tool_name": tool_name,
                    "query": structured_result.get("query") or parameters.get("query"),
                    "snippet": self._truncate(result.get("content") or result.get("title")),
                    "raw": result,
                    "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                }
                result_url = result.get("url") or result.get("source_url")
                if result_url:
                    item["producer_key"] = f"web:{result_url}"
                items.append(item)
        elif isinstance(structured_result, dict) and "url" in structured_result:
            items.append({
                "type": "web_fetch",
                "tool_name": tool_name,
                "query": structured_result.get("url"),
                "snippet": self._truncate(structured_result.get("content") or structured_result.get("title")),
                "raw": structured_result,
                "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                "producer_key": f"web:{structured_result['url']}",
            })

        if not items and rendered_result:
            items.append({
                "type": "model_generated_inference",
                "source": "report_tool",
                "tool_name": tool_name,
                "query": parameters.get("query") or parameters.get("url") or parameters.get("interview_topic"),
                "snippet": self._truncate(rendered_result),
                "raw": rendered_result,
                "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
            })

        for item in items:
            item.setdefault("source", "report_tool")
            self._record_evidence_item(item)

    @staticmethod
    def _atomize_claim_chunk(chunk: str) -> List[str]:
        return atomize_claim_chunk(chunk)

    @staticmethod
    def _is_atomic_claim(text: str) -> bool:
        return is_atomic_claim(text)

    @staticmethod
    def _is_claim_candidate(text: str) -> bool:
        return is_claim_candidate(text)

    @staticmethod
    def _build_source_id_anchor(item: Dict[str, Any]) -> Optional[str]:
        return build_source_id_anchor(item)

    @property
    def empty_searches(self) -> EmptySearchRegistry:
        """Merkliste ergebnisloser Suchen des laufenden Abschnitts (#1191).

        Lazy angelegt statt in ``__init__``: zahlreiche Tests bauen den Agent
        ueber ``ReportAgent.__new__`` ohne Konstruktor, und die Merkliste darf
        dort nicht fehlen.
        """
        return registry_for(self)

    @staticmethod
    def _attach_provenance(item: Dict[str, Any]) -> Dict[str, Any]:
        return attach_provenance(item)

    def _build_claims_for_section(
        self,
        content: str,
        heartbeat: Optional[Callable[[str], None]] = None,
    ) -> List[Dict[str, Any]]:
        raw_chunks = [part.strip() for part in re.split(r"\n\s*\n", (content or "").strip()) if part.strip()]
        # S3a: Strukturmarkup (Header, Bold-Section-Titel) verwerfen.
        chunks = [c for c in raw_chunks if self._is_claim_candidate(c)]
        # S3b: Mehrsatz-Chunks in atomare Aussagen splitten und Übergangs-
        # sätze ohne prüfbare Substanz verwerfen. Fallback: wenn nichts den
        # Atom-Filter passiert, behält der Chunk einen Eintrag (sonst gehen
        # legitime Single-Sentence-Sections verloren).
        atomic_chunks: List[str] = []
        for chunk in chunks:
            atoms = [a for a in self._atomize_claim_chunk(chunk) if self._is_atomic_claim(a)]
            atomic_chunks.extend(atoms or [chunk])
        chunks = atomic_chunks
        claims = []
        evidence_index = (self.evidence_map or {}).get("evidence_index") or {}
        global_items = [
            deepcopy(evidence_index[evidence_id])
            for evidence_id in (self.evidence_map or {}).get("global_evidence_refs", [])
            if evidence_id in evidence_index
        ]
        # #1217: die Kandidatenliste wird einmal pro Section aufgebaut, nicht
        # pro Claim zugeschnitten. Vorher standen hier
        # ``_active_section_evidence[:10]`` und ``global_evidence_refs[:6]`` —
        # eine Kappung nach Erhebungsreihenfolge. Ein einziger
        # ``insight_forge``-Call liefert bis zu 26 Items, das Fenster war also
        # nach dem ersten Tool-Call voll und die spaeter erhobenen
        # Persona-Zitate und Seed-Treffer waren fuer die Bindung unerreichbar.
        direct_items = [
            deepcopy(item) for item in self._active_section_evidence
            if item.get("type") not in FORBIDDEN_EVIDENCE_TYPES
        ]
        # S4b: claim-spezifisches Binding wenn ein Embedder verfügbar ist.
        # S5: model_generated_inference und section_synthesis sind keine
        # Evidence — sie sind Modell-Output. Sie wandern in das separate
        # `audit_trail`-Feld der Claim-Dataclass, nicht ins `evidence`-Array.
        embedder = self._try_get_embedder()
        pool = (
            EvidenceCandidatePool(direct_items + global_items, embedder)
            if embedder is not None
            else None
        )
        for index, chunk in enumerate(chunks, 1):
            # Issue #1187: dies ist die im gemessenen Lauf bestaetigte
            # lange Nachbearbeitungsschleife (Claim-Extraktion +
            # Evidence-Binding, 178-347s ohne jedes Signal). Ein
            # zeitgesteuerter Heartbeat haelt progress.json waehrend der
            # Schleife in Bewegung, ohne bei jedem Claim zu schreiben.
            if heartbeat is not None:
                heartbeat(f"Claim {index}/{len(chunks)}")
            audit_trail = [
                EvidenceItem(
                    type="model_generated_inference",
                    source="section_synthesis",
                    tool_name="section_synthesis",
                    snippet=self._truncate(chunk),
                    raw={"content": chunk},
                ).to_dict()
            ]
            for unresolved in getattr(self, "_active_section_unresolved_evidence", [])[:10]:
                audit_trail.append({
                    "type": "unresolved_evidence",
                    "source": str(unresolved.get("source") or "report_tool"),
                    "snippet": self._truncate(str(unresolved.get("snippet") or "")),
                    "raw": {"reason": "missing_producer_key"},
                })

            bound: List[Dict[str, Any]] = []
            embedder_ok = False
            if embedder is not None and pool is not None:
                try:
                    # Erst nach Relevanz auswaehlen, dann binden. Der Pool
                    # reicht seinen memoisierten Embedder weiter, damit die
                    # zweite Stufe dieselben Vektoren benutzt statt sie je
                    # Claim neu zu berechnen (#1187).
                    bound = bind_evidence_to_claim(
                        chunk,
                        pool.select(chunk),
                        pool.embed,
                        threshold=0.55,
                        top_k=5,
                    )
                    embedder_ok = True
                except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
                    logger.warning(
                        f"EvidenceBinder failed, falling back to generic pool: {exc!r}"
                    )
                    self._embed_cache = None
                    embedder = None
                    pool = None
            if embedder_ok:
                evidence_items = bound
                direct_count = len(bound)
            else:
                evidence_items = [
                    {"evidence_id": item["evidence_id"]}
                    for item in direct_items
                    if item.get("evidence_id")
                ]
                direct_count = len(direct_items)

            resolved_evidence = []
            current_index = (self.evidence_map or {}).get("evidence_index") or {}
            for binding in evidence_items:
                record = current_index.get(binding.get("evidence_id"))
                if record:
                    resolved_evidence.append(dict(record) | dict(binding))

            # S6: formelbasierte Confidence statt linear-in-N. Berechnet
            # aus relevance (mean match_score), source_quality (Typ-
            # Gewichtung), specificity (top match_score), consistency
            # (Anzahl unique Quellen). Verified-Label nur bei Top-
            # Match-Score >= 0.85.
            penalty = detect_contradiction_penalty(resolved_evidence)
            confidence_score, confidence_label = compute_confidence(
                resolved_evidence,
                contradiction_penalty=penalty,
            )
            if penalty > 0.0:
                audit_trail.append({
                    "type": "contradiction_penalty_applied",
                    "value": penalty,
                    "source": "evidence_binder.detect_contradiction_penalty",
                })
            # Anti-Dekorations-Guard: kein Evidence → ehrliches speculative-Label
            # und Audit-Eintrag statt dekorativem global_items-Fallback.
            if not resolved_evidence:
                confidence_score, confidence_label = 0.15, "speculative"
                audit_trail.append({
                    "type": "model_generated_inference",
                    "source": "validator",
                    "tool_name": "evidence_validator",
                    "snippet": "no_direct_evidence_bound",
                    "raw": {"reason": "no_direct_evidence_bound"},
                })
            # Hinweis fürs Test-Backwards-Compat: support_count wird nicht
            # mehr genutzt, bleibt aber lokal für ggf. Logging.
            support_count = direct_count + len(global_items)  # noqa: F841
            claim_dict = ReportClaim(
                claim_id=f"claim_{index:02d}",
                claim_text=chunk,
                evidence=evidence_items,
                confidence_score=confidence_score,
                confidence_label=confidence_label,
                notes="Section-chunk level evidence mapping (schema_version 3).",
            ).to_dict()
            claim_dict["audit_trail"] = audit_trail
            claims.append(claim_dict)
        if not claims:
            claims.append(ReportClaim(
                claim_id="claim_01",
                claim_text="No claim candidate extracted from this section.",
                evidence=[],
                confidence_score=0.0,
                confidence_label="speculative",
                notes="No section content captured.",
            ).to_dict())
        return claims

    @staticmethod
    def _suggested_evidence_from_claim_audit(claim: Dict[str, Any]) -> List[str]:
        suggestions: List[str] = []
        for entry in claim.get("audit_trail") or []:
            if not isinstance(entry, dict):
                continue
            reason = entry.get("snippet") or entry.get("source") or entry.get("type")
            if reason == "no_direct_evidence_bound":
                suggestions.append("Direkte Evidence per Graph- oder Agent-Tool nachreichen.")
            elif reason:
                suggestions.append(str(reason)[:200])
        return suggestions[:5] or ["Direkte Evidence per Graph- oder Agent-Tool nachreichen."]

    def _finalize_section_claims(
        self,
        claims: List[Dict[str, Any]],
    ) -> tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
    ]:
        finalized_claims: List[Dict[str, Any]] = []
        hypotheses: List[Dict[str, Any]] = []
        data_gaps: List[Dict[str, Any]] = []
        # Slice 7 (Audit Trail): jede Routing-Entscheidung des Evidence-Gates
        # wird als EvidenceDegradationModel-Eintrag protokolliert —
        # section_index ergänzt der Caller (_save_evidence_section).
        gate_decisions: List[Dict[str, Any]] = []

        for claim in normalize_claims_for_contract(claims):
            evidence = claim.get("evidence") or []
            label = str(claim.get("confidence_label") or "").lower()

            # P0-5: Gezählt wird nur, was den Claim tatsächlich stützt
            # (``supports_claim is True``, gesetzt von der Entailment-Stufe).
            # Vorher zählte jedes thematisch ähnliche Item mit — dadurch
            # erreichten Interpretationen den Claim-Floor, obwohl kein
            # einziges Item sie belegte.
            evidence_ids = {
                str(item["evidence_id"])
                for item in evidence
                if isinstance(item, dict) and item.get("evidence_id")
            }
            supporting_ids = {
                str(item["evidence_id"])
                for item in evidence
                if isinstance(item, dict)
                and item.get("evidence_id")
                and item.get("supports_claim") is True
            }
            unkeyed_related = sum(
                1
                for item in evidence
                if not isinstance(item, dict) or not item.get("evidence_id")
            )
            related_only = len(evidence_ids - supporting_ids) + unkeyed_related
            # P0-5: Ohne eine einzige stützende Quelle ist die Aussage eine
            # Hypothese — auch dann, wenn thematisch verwandte Evidence
            # anhängt. Vorher griff dieser Zweig nur bei komplett leerer
            # Evidence-Liste und niedrigem Score; Interpretationen mit
            # dekorativer Evidence liefen als Claims durch.
            if not supporting_ids:
                index = len(hypotheses) + 1
                claim_text = (
                    str(claim.get("claim_text") or claim.get("claim") or "").strip()
                    or "No evidence-bound claim text available."
                )
                claim_text = self._truncate(claim_text, 1000)
                suggestions = self._suggested_evidence_from_claim_audit(claim)
                if related_only:
                    rationale = (
                        f"{related_only} Quelle(n) sind thematisch verwandt, "
                        "belegen die Aussage aber nicht (kein SUPPORTED-Urteil) "
                        "— deshalb als Hypothese geführt."
                    )
                else:
                    rationale = (
                        "Keine direkte Evidence gebunden; deshalb nicht als "
                        "validierter Claim persistiert."
                    )
                hypotheses.append({
                    "hypothesis_id": f"hypothesis_{index:02d}",
                    "hypothesis_text": claim_text,
                    "rationale": rationale,
                    "suggested_evidence": suggestions,
                })
                data_gaps.append({
                    "gap_id": f"gap_{index:02d}",
                    "claim_text": claim_text,
                    "gap_reason": (
                        "related_evidence_only" if related_only else "no_evidence_bound"
                    ),
                    "suggested_fix": suggestions[0],
                })
                # Copilot-Review PR #1151: dieser Zweig fängt auch den Fall
                # medium/high/verified ohne jede Evidence ab (der spätere
                # P2.1-Zweig ist dafür unerreichbar) — das Label macht die
                # Verletzung im Audit-Trail unterscheidbar.
                gate_decisions.append({
                    "claim_id": str(claim.get("claim_id") or "<no-id>"),
                    "violation": (
                        "confidence_label_without_evidence"
                        if not evidence and label in ("medium", "high", "verified")
                        else "no_supporting_evidence"
                    ),
                    "action": "moved_to_hypotheses",
                    "detail": rationale[:500],
                })
                continue
            if not evidence and label in ("medium", "high", "verified"):
                # P2.1: medium/high/verified ohne Evidence darf nicht in claims[]
                # (würde ReportClaimModel-Validator verletzen). Stattdessen data_gap.
                index = len(data_gaps) + 1
                claim_text = (
                    str(claim.get("claim_text") or claim.get("claim") or "").strip()
                    or "No evidence-bound claim text available."
                )
                claim_text = self._truncate(claim_text, 1000)
                suggestions = self._suggested_evidence_from_claim_audit(claim)
                data_gaps.append({
                    "gap_id": f"gap_{index:02d}",
                    "claim_text": claim_text,
                    "gap_reason": "no_evidence_bound",
                    "suggested_fix": suggestions[0] if suggestions else None,
                })
                continue

            # ADR-0002 Stufe agent_grounded: `medium` verlangt mind. 1
            # agent_quote (mit nicht-leerem quote) UND mind. 1 seed_corpus.
            # Der Builder hat das bisher nicht geprüft — ein medium-Claim ohne
            # diese Komposition erreichte den ReportClaimModel-Validator und
            # ließ die gesamte EvidenceMap-Validierung scheitern: Report
            # abgebrochen statt Claim abgestuft. Der Reparaturlauf in
            # `degrade_sections_for_violations` fängt das nicht zuverlässig
            # auf, weil Pydantic pro Durchgang nur den ersten Verstoß je Modell
            # meldet — bei mehreren betroffenen Claims einer Section bleibt
            # nach der Reparatur des ersten der nächste stehen.
            #
            # Der Validator bleibt unverändert streng (ADR-0002 Anker 4/5
            # unberührt); hier entsteht das verletzende Label gar nicht erst.
            # Schwesterregel für high/verified:
            # `auto_downgrade_unsupported_high_claims`.
            # getattr: ``_finalize_section_claims`` wird in Tests auch an einer
            # per ``__new__`` gebauten Instanz ohne ``__init__`` aufgerufen.
            evidence_index = (getattr(self, "evidence_map", None) or {}).get("evidence_index") or {}
            if label == "medium" and not has_agent_grounded_evidence(
                evidence, evidence_index=evidence_index
            ):
                claim["confidence_label"] = "low"
                detail = (
                    "medium verlangt agent_quote (mit Zitat) UND seed_corpus "
                    "(ADR-0002 Stufe agent_grounded) — Komposition nicht "
                    "erfüllt, Claim als low geführt."
                )
                logger.warning(
                    "_finalize_section_claims: %s medium → low (%s)",
                    str(claim.get("claim_id") or "<no-id>"),
                    "nicht agent_grounded",
                )
                gate_decisions.append({
                    "claim_id": str(claim.get("claim_id") or "<no-id>"),
                    "violation": "medium_without_agent_grounded_evidence",
                    "action": "downgraded_to_low",
                    "detail": detail[:500],
                })

            finalized_claims.append(claim)

        return finalized_claims, hypotheses, data_gaps, gate_decisions

    def _section_dedup_check(
        self, new_summary: str, existing: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        return section_dedup_check(
            new_summary,
            existing,
            get_embedder=self._try_get_embedder,
            logger=logger,
        )

    def _prose_evidence_pool(self) -> List[Dict[str, Any]]:
        """Evidence-Basis für die Fließtext-Faktenprüfung.

        Der Abschnitts-Pool zuerst — dort liegen die Treffer, die der Agent für
        genau diesen Abschnitt geholt hat. Die globale Simulationsevidence
        ergänzt ihn, damit ein Seed-Fakt auch dann als Beleg zählt, wenn er in
        diesem Abschnitt nicht erneut abgefragt wurde.
        """
        pool: List[Dict[str, Any]] = list(self._active_section_evidence or [])
        if self.evidence_map:
            evidence_index = self.evidence_map.get("evidence_index") or {}
            pool.extend(
                evidence_index[evidence_id]
                for evidence_id in self.evidence_map.get("global_evidence_refs") or []
                if evidence_id in evidence_index
            )
        return pool

    def _record_prose_hypotheses(
        self,
        section_index: int,
        rejected: List[Any],
    ) -> None:
        """Merkt aus dem Fließtext entfernte Aussagen als Hypothesen vor.

        Sie werden in ``_save_evidence_section`` in den Hypothesen-Slot der
        Section übernommen — entfernte Behauptungen verschwinden also nicht,
        sie verlieren nur ihren Status als belegte Aussage.
        """
        if not rejected:
            return
        if not hasattr(self, "_pending_prose_hypotheses") or self._pending_prose_hypotheses is None:
            self._pending_prose_hypotheses = {}
        bucket = self._pending_prose_hypotheses.setdefault(section_index, [])
        for offset, statement in enumerate(rejected, start=len(bucket) + 1):
            bucket.append(statement.as_hypothesis(offset))

    def _record_section_metadata(self, section_index: int, metadata: Dict[str, Any]) -> None:
        """Merkt die Struktur-Metadaten eines Abschnitts für ReportV3 vor.

        Wird von der Section-Schleife aufgerufen, bevor
        ``_save_evidence_section`` die Section persistiert.
        """
        if not metadata:
            return
        if not hasattr(self, "_pending_section_metadata") or self._pending_section_metadata is None:
            self._pending_section_metadata = {}
        self._pending_section_metadata[section_index] = metadata

    def _remap_active_evidence_ids(self, id_remap: Dict[str, str]) -> None:
        """Zieht die Puffer des laufenden Abschnitts auf neue Evidence-IDs nach.

        Gegenstück zu ``demote_unanchored_seed_corpus_records`` (Issue #1154):
        die Migration schlüsselt den ``evidence_index`` um, diese Methode die
        noch nicht persistierten Referenzen im Speicher. Nach dem Nachzug
        können zwei Puffereinträge auf dieselbe Quelle zeigen — sie werden zu
        einem zusammengeführt, damit die Confidence dieselbe Quelle nicht
        doppelt zählt.
        """
        for attribute in ("_active_section_evidence", "_active_section_unresolved_evidence"):
            buffer = getattr(self, attribute, None)
            if not isinstance(buffer, list):
                continue
            # Reihenfolge bleibt erhalten: ``_build_claims_for_section``
            # schneidet den Puffer danach mit ``[:10]`` ab — eine Umsortierung
            # würde die Auswahl der gebundenen Evidence verschieben, obwohl
            # hier nur IDs ersetzt werden.
            kept: List[Any] = []
            seen: set[str] = set()
            for item in buffer:
                if not isinstance(item, dict) or not item.get("evidence_id"):
                    kept.append(item)
                    continue
                target = id_remap.get(str(item["evidence_id"]), str(item["evidence_id"]))
                item["evidence_id"] = target
                if target in seen:
                    continue
                seen.add(target)
                kept.append(item)
            setattr(self, attribute, kept)

    def _save_evidence_section(
        self, report_id: str, section_index: int, section_title: str, content: str
    ) -> SectionEvidenceOutcome:
        """Extrahiert Claims, bindet Evidence und persistiert die Evidenzkarte.

        Issue #1212: Der Rückgabewert ist additiv — die Persistenz und alle
        Seiteneffekte auf ``self.evidence_map`` sind unverändert. Er macht
        beobachtbar, was gebunden und was vom Gate verworfen wurde, ohne dass
        ein Aufrufer dafür die persistierte Karte durchsuchen muss.
        """
        from .output_contract import is_fallback_content  # noqa: PLC0415

        # Issue #1187: macht die bislang unsichtbare Nachbearbeitung
        # (Claim-Extraktion, Evidence-Binding, Persistenz der Evidenzkarte)
        # sichtbar und messbar — ohne ihr Verhalten zu aendern.
        #
        # Nur aktiv, wenn ein echter ``report_logger`` gesetzt ist (wie beim
        # bestehenden ``if agent.report_logger:``-Muster in workflow.py) —
        # das ist ausserhalb eines echten ``generate_report``-Laufs nicht der
        # Fall (u. a. viele Unit-Tests bauen ``ReportAgent.__new__`` ohne
        # ``report_logger``) und verhindert dort ungewollte
        # progress.json-Schreibzugriffe auf das reale ``ReportManager``.
        report_logger = getattr(self, "report_logger", None)
        phase_tracker: Optional[PostprocessPhaseTracker] = None
        if report_logger is not None:
            phase_tracker = PostprocessPhaseTracker(
                report_id,
                section_index=section_index,
                section_title=section_title,
                report_logger=report_logger,
                report_manager=ReportManager,
            )

        def _phase(name: str):
            return phase_tracker.phase(name) if phase_tracker is not None else nullcontext()

        id_remap: Dict[str, str] = {}
        if self.evidence_map is None:
            self._init_evidence_map(report_id)
        else:
            # Issue #1154: Die Normalisierung kann Evidence umschlüsseln
            # (seed_corpus ohne Dokumentanker → graph_relation, und der
            # source_kind steckt im Identitäts-Hash). Der Abschnittspuffer hält
            # die alten IDs; ohne Nachzug bauen die gleich folgenden Claims
            # Bindungen auf Schlüssel, die es nicht mehr gibt — der
            # Cross-Reference-Validator lehnt die Map dann ab.
            self.evidence_map = (
                normalize_persisted_evidence_map(self.evidence_map, remap_out=id_remap)
                or self.evidence_map
            )
            if id_remap:
                self._remap_active_evidence_ids(id_remap)
        self.evidence_map.setdefault("schema_version", CURRENT_SCHEMA_VERSION)
        self.evidence_map.setdefault("evidence_index", {})
        self.evidence_map.setdefault("global_evidence_refs", [])
        # schema_version gehört nur auf Map-Ebene, nicht auf Section-Ebene
        # (ReportSectionModel hat das Feld nicht).
        #
        # P0-7: Fehlgeschlagene Sections enthalten Fehlertext, keinen Bericht.
        # Daraus dürfen weder Claims noch Evidence entstehen — sonst erscheint
        # eine LLM-Fehlermeldung als Medium-Confidence-Aussage im Report.
        generation_failed = is_fallback_content(content)
        if generation_failed:
            logger.warning(
                "section %d (%r): Fallback-Inhalt — keine Claim-/Evidence-Extraktion.",
                section_index,
                section_title,
            )
            claims: List[Dict[str, Any]] = []
            raw_hypotheses: List[Dict[str, Any]] = []
            gate_decisions: List[Dict[str, Any]] = []
            data_gaps: List[Dict[str, Any]] = [{
                # ReportSectionDataGapModel.gap_id erzwingt ^gap_\d{2,}$ —
                # ein sprechendes Präfix ("gap_section_03") lässt die gesamte
                # EvidenceMap-Validierung scheitern (E2E-Lauf, Runde 4).
                "gap_id": f"gap_{section_index:02d}",
                "gap_reason": "Abschnitt konnte nicht generiert werden (LLM-Fehler).",
                "claim_text": section_title,
            }]
        else:
            heartbeat_cb = phase_tracker.heartbeat if phase_tracker is not None else None
            with _phase("claim_extraction_and_evidence_binding"):
                extracted_claims = self._build_claims_for_section(
                    content, heartbeat=heartbeat_cb
                )
            with _phase("claim_finalization"):
                claims, raw_hypotheses, data_gaps, gate_decisions = self._finalize_section_claims(
                    extracted_claims
                )
            # Issue #1154: letzte Station vor der Validierung. Der Nachzug auf
            # den Abschnittspuffern deckt den Regelfall ab; hier landen alle
            # Claims, gleich woher sie stammen. Eine Bindung auf einen
            # umgeschlüsselten Record würde die ganze Map ungültig machen.
            if id_remap:
                claims = _remap_claim_bindings(claims, id_remap)
        # Aus dem Fließtext entfernte Faktenaussagen sind Hypothesen, keine
        # gelöschten Sätze — sie bleiben für den Leser nachvollziehbar.
        prose_hypotheses = (
            getattr(self, "_pending_prose_hypotheses", {}) or {}
        ).get(section_index, [])
        raw_hypotheses = list(raw_hypotheses) + prose_hypotheses
        # IDs zentral neu vergeben: Claim-Routing und Fließtext-Prüfung zählen
        # jeweils ab 1, zusammengeführt kollidieren sie sonst.
        for _position, _hypothesis in enumerate(raw_hypotheses, start=1):
            if isinstance(_hypothesis, dict):
                _hypothesis["hypothesis_id"] = f"hypothesis_{_position:02d}"
        # Slice 7 (Audit Trail): Gate-Routing und Fließtext-Entfernungen sind
        # Degradation-Entscheidungen und werden auditierbar protokolliert —
        # der leere degradation_log bei 17 entfernten Aussagen
        # (report_06f654800817) war eine Erfassungslücke, keine Absicht.
        for _prose_hypothesis in prose_hypotheses:
            if not isinstance(_prose_hypothesis, dict):
                continue
            gate_decisions.append({
                "claim_id": str(_prose_hypothesis.get("hypothesis_id") or "<no-id>"),
                "violation": "prose_fact_unsupported",
                "action": "moved_to_hypotheses",
                "detail": self._truncate(
                    str(_prose_hypothesis.get("hypothesis_text") or ""), 500
                ) or "Fließtext-Aussage ohne deckende Evidence entfernt.",
            })
        if gate_decisions:
            # Getrennt vom degradation_log: reguläres Gate-Routing ist kein
            # Statusmangel und darf apply_degradation_downgrade nicht auslösen.
            self.evidence_map["gate_decision_log"] = list(
                self.evidence_map.get("gate_decision_log") or []
            ) + [
                {**decision, "section_index": section_index}
                for decision in gate_decisions
            ]
        # Slice 3 (Issue #495): Dedup + Cap per Section.
        from .hypothesis_cap import dedup_and_cap_hypotheses  # noqa: PLC0415
        hypotheses_visible, hypotheses_appendix = dedup_and_cap_hypotheses(raw_hypotheses)
        section_entry = {
            "section_index": section_index,
            "section_title": section_title,
            "section_summary": self._truncate(content, 400),
            "claims": claims,
            "hypotheses": hypotheses_visible,
            "hypotheses_appendix": hypotheses_appendix,
            "data_gaps": data_gaps,
            "structured_metadata": (
                getattr(self, "_pending_section_metadata", {}) or {}
            ).get(section_index, {}),
            "generation_failed": generation_failed,
        }
        # Issue #1187: Persistenz-Phase startet hier explizit statt per
        # ``with``, damit der weit verschachtelte Validierungs-/Reparatur-
        # block unten unveraendert bleibt (keine Re-Indentation der
        # ADR-0002-Degradationslogik).
        if phase_tracker is not None:
            phase_tracker.start_phase("evidence_map_persistence")
        # schema_version auf Section-Ebene entfernen — Überbleibsel von
        # migrate_v1_to_v2 oder alten Persistierungen; ReportSectionModel
        # erlaubt das Feld nicht (extra="forbid").
        existing_sections = normalize_sections_for_contract([
            s for s in self.evidence_map["sections"]
            if s.get("section_index") != section_index
        ])
        # Reader Honesty: Section-Dedup — Duplikat-Marker im audit_trail ablegen,
        # Section selbst nicht droppen (Frontend entscheidet).
        dedup_marker = self._section_dedup_check(
            new_summary=section_title or content[:200],
            existing=existing_sections,
        )
        if dedup_marker is not None:
            claims = section_entry.get("claims") or []
            if claims:
                claims[0].setdefault("audit_trail", []).append(dedup_marker)
        existing_sections.append(section_entry)
        existing_sections.sort(key=lambda item: item.get("section_index", 0))
        # Layer-0 Boundary: vor dem Persistieren auto-downgrade'n und gegen
        # EvidenceMapModel validieren. ``normalize_sections_for_contract``
        # senkt confidence_label='high'/'verified' auf 'medium', wenn die
        # ADR-0002-Cross-Stakeholder-Anforderung nicht erfüllt ist
        # (Smoke-Live 2026-05-15). Der Validator bleibt strikt.
        self.evidence_map["sections"] = normalize_sections_for_contract(
            existing_sections, logger=logger,
        )
        try:
            validated = EvidenceMapModel.model_validate(self.evidence_map).model_dump(mode="json")
        except ValidationError as first_error:
            # Issue #1006: ein einzelner ADR-0002-Verstoss darf nicht den
            # gesamten Report auf FAILED kippen und bereits fertige Sections
            # mitreissen. Statt den Validator zu lockern, wird der
            # verletzende Claim lokal abgestuft/entfernt und protokolliert.
            repaired_sections, violations = degrade_sections_for_violations(
                self.evidence_map["sections"], first_error, logger=logger,
            )
            self.evidence_map["sections"] = repaired_sections
            self.evidence_map["degradation_log"] = (
                list(self.evidence_map.get("degradation_log") or []) + violations
            )
            logger.warning(
                "_save_evidence_section: section=%d ValidationError repariert — %d Verstoss/Verstösse.",
                section_index, len(violations),
            )
            try:
                validated = EvidenceMapModel.model_validate(self.evidence_map).model_dump(mode="json")
            except ValidationError as second_error:
                # Zweiter Versuch ebenfalls ungültig: degrade_sections_for_violations
                # kennt nur die Fehlerformen aus dem ersten Durchlauf. Jetzt werden
                # alle Claims/Hypothesen, deren loc-Pfad im neuen Fehler auftaucht,
                # ersatzlos aus ihrer Section entfernt.
                sections = self.evidence_map["sections"]
                indices_to_remove: Dict[Any, set] = {}
                removed_entries: List[Dict[str, Any]] = []
                for err in second_error.errors():
                    loc = err.get("loc") or ()
                    if len(loc) < 4 or loc[0] != "sections":
                        continue
                    si, kind, idx = loc[1], loc[2], loc[3]
                    if kind not in ("claims", "hypotheses", "hypotheses_appendix"):
                        continue
                    if not isinstance(si, int) or not (0 <= si < len(sections)):
                        continue
                    entries = sections[si].get(kind) or []
                    if not isinstance(idx, int) or not (0 <= idx < len(entries)):
                        continue
                    key = (si, kind)
                    if idx in indices_to_remove.get(key, set()):
                        continue
                    indices_to_remove.setdefault(key, set()).add(idx)
                    entry = entries[idx]
                    entry_id = ""
                    if isinstance(entry, dict):
                        entry_id = str(entry.get("claim_id") or entry.get("hypothesis_id") or "")
                    removed_entries.append({
                        "section_index": sections[si].get("section_index", 0),
                        "claim_id": entry_id,
                        "violation": str(err.get("type") or "unknown"),
                        "action": "dropped",
                        "detail": str(err.get("msg") or "")[:500],
                    })
                for (si, kind), indices in indices_to_remove.items():
                    entries = sections[si].get(kind)
                    if not isinstance(entries, list):
                        continue
                    for i in sorted(indices, reverse=True):
                        del entries[i]
                self.evidence_map["degradation_log"] = (
                    list(self.evidence_map.get("degradation_log") or []) + removed_entries
                )
                logger.warning(
                    "_save_evidence_section: section=%d zweiter ValidationError — %d Eintrag/Einträge hart entfernt.",
                    section_index, len(removed_entries),
                )
                # Dritter Versuch: scheitert er erneut, ist etwas anderes kaputt —
                # die Exception läuft bewusst ungefangen weiter (Issue #1006).
                validated = EvidenceMapModel.model_validate(self.evidence_map).model_dump(mode="json")
        self.evidence_map = validated
        ReportManager.save_evidence_map(report_id, validated)
        if phase_tracker is not None:
            phase_tracker.end_phase()
        return SectionEvidenceOutcome.from_persisted_section(
            validated,
            section_index,
            gate_decisions=gate_decisions,
            generation_failed=generation_failed,
        )

    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        return define_tools(self)

    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        return execute_tool_call(self, tool_name, parameters, report_context=report_context)

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        return parse_tool_calls(response)

    def _is_valid_tool_call(self, data: dict) -> bool:
        return is_valid_tool_call(data)

    def _get_tools_description(self) -> str:
        return describe_tools(self.tools)

    def _get_openai_tools_schema(self) -> List[Dict[str, Any]]:
        """Liefert die Tool-Definitionen im OpenAI function-calling Format."""
        return get_openai_tools_schema(self)

    def plan_outline(
        self,
        progress_callback: Optional[Callable] = None,
        required_sections: Optional[list[tuple[str, str]]] = None,
    ) -> ReportOutline:
        return plan_outline_impl(
            self,
            progress_callback=progress_callback,
            required_sections=required_sections,
        )

    def _generate_section_react(
        self,
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        return generate_section_react_impl(
            self,
            section=section,
            outline=outline,
            previous_sections=previous_sections,
            progress_callback=progress_callback,
            section_index=section_index,
        )

    def generate_report(
        self,
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None,
        *,
        report_mode: str = "balanced",
    ) -> Report:
        return generate_report_impl(self, progress_callback=progress_callback, report_id=report_id, report_mode=report_mode)  # type: ignore[arg-type]

    def chat(
        self,
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        return chat_impl(self, message=message, chat_history=chat_history)
