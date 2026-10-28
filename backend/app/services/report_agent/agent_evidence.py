from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from pydantic import ValidationError

from .evidence_candidates import EvidenceCandidatePool
from .search_dedup import EmptySearchRegistry

if TYPE_CHECKING:
    from ..evidence_entailment import EntailmentJudge

# Issue #1277-6: Stärkste Bindung bei ID-Kollision gewinnen lassen, statt
# per First-Wins die schwächere zu behalten und die stärkere still zu
# verwerfen. Rang nach Entailment, Tie-Break über match_score.
_ENTAILMENT_RANK: Dict[str, int] = {
    "SUPPORTED": 3,
    "RELATED_ONLY": 2,
    "INSUFFICIENT": 1,
    "CONTRADICTED": 0,
}

#: Rollenwechsel-Kategorien, bei denen eine Aktion nicht als Stimme ihres
#: Agents gelten darf (Issue #1323, Slice 5.2).
_HARD_ROLE_CONFLICTS = frozenset({"foreign_role", "foreign_name_signature"})


def _binding_strength(binding: Dict[str, Any]) -> tuple[int, float]:
    rank = _ENTAILMENT_RANK.get(str(binding.get("entailment") or ""), 0)
    return (rank, float(binding.get("match_score") or 0.0))


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
            existing = merged.get(target)
            if existing is None or _binding_strength(binding) > _binding_strength(existing):
                merged[target] = binding
        claim["evidence"] = others + list(merged.values())
        remapped.append(claim)
    return remapped


class ReportAgentEvidenceMixin:
    """Evidence-Index-, Pool-, Embedder- und Simulationsbeleg-Verwaltung für ReportAgent."""

    if TYPE_CHECKING:
        _active_section_evidence: List[Dict[str, Any]]
        _judge_cache: Optional[EntailmentJudge]
        def __getattr__(self, name: str) -> Any: ...
        def __setattr__(self, name: str, value: Any) -> None: ...

    def _init_evidence_map(self, report_id: str) -> None:
        from . import agent as _agent_mod

        self.evidence_map = _agent_mod.init_evidence_map(
            report_id=report_id,
            simulation_id=self.simulation_id,
            global_evidence=self._collect_simulation_evidence_items(),
        )

    def _truncate(self, text: str, limit: int = 300) -> str:
        from . import agent as _agent_mod

        return _agent_mod.truncate_text(text, limit)

    def _record_evidence_item(self, item: Dict[str, Any]) -> Optional[str]:
        from . import agent as _agent_mod

        enriched = _agent_mod.attach_provenance(dict(item))
        if self.evidence_map is None:
            _agent_mod.ledger_for(self).dropped(enriched, "no_evidence_map")
            self._active_section_unresolved_evidence.append(enriched)
            return None
        try:
            record = _agent_mod.register_evidence_record(
                self.evidence_map,
                enriched,
                scope_id=self.simulation_id,
                ledger=_agent_mod.ledger_for(self),
            )
        except ValidationError as exc:
            _agent_mod.logger.warning(
                "register_evidence_record: Item verworfen (type=%r, %d Validierungsfehler)",
                enriched.get("type"),
                len(exc.errors()),
            )
            _agent_mod.ledger_for(self).dropped(
                enriched, f"validation_error:{len(exc.errors())}_fields"
            )
            self._active_section_unresolved_evidence.append(enriched)
            return None
        if record is None:
            self._active_section_unresolved_evidence.append(enriched)
            return None
        self._active_section_evidence = _agent_mod.record_evidence_item(
            self._active_section_evidence,
            record,
        )
        return record.get("evidence_id")

    def _try_get_embedder(self) -> Optional[Callable[[str], List[float]]]:
        from . import agent as _agent_mod

        cached = getattr(self, "_embed_cache", "missing")
        embed_fn = _agent_mod.resolve_embedder(cached=cached, logger=_agent_mod.logger)
        self._embed_cache = embed_fn
        return embed_fn

    def _try_get_entailment_judge(self) -> Optional["EntailmentJudge"]:
        """Der Judge für die Grauzone des qualitativen Entailments (#1357)."""
        from . import agent as _agent_mod

        if hasattr(self, "_judge_cache"):
            return self._judge_cache
        judge: Optional[EntailmentJudge] = None
        try:
            judge = _agent_mod.build_llm_judge(self.llm, logger=_agent_mod.logger)
        except Exception as exc:  # noqa: BLE001 — Judge ist optional
            _agent_mod.logger.warning(f"Entailment-Judge nicht verfügbar: {exc!r}")
        self._judge_cache = judge
        return judge

    @staticmethod
    def _sample_actions_timeseries(
        actions: List[Dict[str, Any]], k: int = 8
    ) -> List[Dict[str, Any]]:
        from . import agent as _agent_mod

        return _agent_mod.sample_actions_timeseries(actions, k)

    def _collect_simulation_evidence_items(self) -> List[Dict[str, Any]]:
        """Collect reusable evidence from existing metrics and simulation actions."""
        from . import agent as _agent_mod

        try:
            from ..network_analytics import NetworkAnalyticsService
            from ..simulation_runner import SimulationRunner

            actions = SimulationRunner.get_all_actions(self.simulation_id)
            action_dicts = [action.to_dict() for action in actions]
            if not action_dicts:
                return []

            metrics = (
                NetworkAnalyticsService()
                .compute_metrics(
                    action_dicts,
                    simulation_id=self.simulation_id,
                )
                .to_dict()
            )
            items: List[Dict[str, Any]] = []
            if metrics.get("status") != "ok":
                items.append(
                    _agent_mod.EvidenceItem(
                        type="graph_metric_status",
                        source="simulation_metrics",
                        value=f"status={metrics.get('status')}",
                        snippet=(
                            f"Polarization-Metriken nicht verfügbar "
                            f"(Status: {metrics.get('status')})"
                        ),
                        raw={"metrics": metrics},
                    ).to_dict()
                )
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
                    items.append(
                        _agent_mod.EvidenceItem(
                            type="graph_metric",
                            source="simulation_metrics",
                            value=f"{field}={value}",
                            snippet=f"{field}: {value}",
                            raw={"metric": field, "value": value, "metrics": metrics},
                        ).to_dict()
                    )
                    items[-1]["producer_key"] = f"simulation-metric:{field}"

            eligible_actions = [
                action
                for action in action_dicts
                if action.get("role_conflict") not in _agent_mod._HARD_ROLE_CONFLICTS
            ]
            _skipped_foreign = len(action_dicts) - len(eligible_actions)
            sampled_actions = self._sample_actions_timeseries(eligible_actions, k=8)
            for action in sampled_actions:
                items.append(_agent_mod.build_action_evidence_item(action))
            if _skipped_foreign:
                _agent_mod.logger.info(
                    "report_evidence: %d action(s) with foreign role conflict skipped "
                    "(simulation_id=%s)",
                    _skipped_foreign,
                    self.simulation_id,
                )
            return items
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            _agent_mod.logger.warning(f"Failed to collect simulation evidence: {exc}")
            return []

    @staticmethod
    def _build_source_id_anchor(item: Dict[str, Any]) -> Optional[str]:
        from . import agent as _agent_mod

        return _agent_mod.build_source_id_anchor(item)

    def _evidence_index_map(self) -> Dict[str, Any]:
        """Die kanonische Evidence-Map des laufenden Reports."""
        return (getattr(self, "evidence_map", None) or {}).get("evidence_index") or {}

    @property
    def empty_searches(self) -> EmptySearchRegistry:
        """Merkliste ergebnisloser Suchen des laufenden Abschnitts (#1191)."""
        from . import agent as _agent_mod

        return _agent_mod.registry_for(self)

    @staticmethod
    def _attach_provenance(item: Dict[str, Any]) -> Dict[str, Any]:
        from . import agent as _agent_mod

        return _agent_mod.attach_provenance(item)

    @staticmethod
    def _candidate_pool(
        direct_items: List[Dict[str, Any]],
        global_items: List[Dict[str, Any]],
        evidence_index: Dict[str, Any],
        embedder: Any,
    ) -> Optional[EvidenceCandidatePool]:
        """Kandidaten-Pool eines Abschnitts; ``None`` ohne Embedder."""
        from . import agent as _agent_mod

        if embedder is None:
            return None
        searched_action_items = [
            deepcopy(record)
            for record in evidence_index.values()
            if isinstance(record, dict) and record.get("type") == "agent_action"
        ]
        return _agent_mod.EvidenceCandidatePool(
            direct_items + global_items + searched_action_items,
            embedder,
            reserved_slots=_agent_mod.RESERVED_CANDIDATE_SLOTS,
        )

    def _evidence_pool_for_gap_check(self) -> List[Dict[str, Any]]:
        """Alle bisher kanonisierten Evidence-Records dieses Reports."""
        index = self._evidence_index_map()
        pool = [record for record in index.values() if isinstance(record, dict)]
        pool.extend(
            record
            for record in getattr(self, "_active_section_unresolved_evidence", None) or []
            if isinstance(record, dict)
        )
        return pool

    def _prose_evidence_pool(self) -> List[Dict[str, Any]]:
        """Evidence-Basis für die Fließtext-Faktenprüfung."""
        pool: List[Dict[str, Any]] = list(self._active_section_evidence or [])
        seen = {
            str(item.get("evidence_id"))
            for item in pool
            if isinstance(item, dict) and item.get("evidence_id")
        }
        if self.evidence_map:
            evidence_index = self.evidence_map.get("evidence_index") or {}
            for evidence_id, item in evidence_index.items():
                if evidence_id in seen or not isinstance(item, dict):
                    continue
                seen.add(str(evidence_id))
                pool.append(item)
        return pool

    def _remap_active_evidence_ids(self, id_remap: Dict[str, str]) -> None:
        """Zieht die Puffer des laufenden Abschnitts auf neue Evidence-IDs nach."""
        for attribute in ("_active_section_evidence", "_active_section_unresolved_evidence"):
            buffer = getattr(self, attribute, None)
            if not isinstance(buffer, list):
                continue
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


__all__ = [
    "ReportAgentEvidenceMixin",
    "_ENTAILMENT_RANK",
    "_HARD_ROLE_CONFLICTS",
    "_binding_strength",
    "_remap_claim_bindings",
]
