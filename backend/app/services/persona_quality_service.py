"""Persona quality heuristics for the Slice 2.2 review foundation.

Pure-Python, deterministic checks over the existing ``reddit_profiles.json``
artifact. No LLM calls, no Neo4j round-trips — the goal is to give the UI a
fast hint surface (badges, drawer warnings) before a reviewer has to read each
persona individually.

Detectors are intentionally cheap and conservative:

- ``duplicate_username``  — same ``username`` (case-insensitive) listed twice.
- ``duplicate_name``      — same ``name`` (case-insensitive, trimmed) twice.
- ``missing_core_fields`` — ``bio``/``persona``/``profession`` empty.
                            One missing → ``warning``, all three → ``error``.
- ``missing_entity_link`` — no ``source_entity_uuid`` for an auto-generated
                            persona; ``is_manual=true`` exempts it.
- ``role_diversity``      — ratio of distinct ``profession`` values vs. total.
- ``mbti_diversity``      — ratio of distinct ``mbti`` values vs. total.

Returns a stable, JSON-serialisable structure. Callers (API, future Slice 2.4
UI) are free to ignore severities they don't want to render.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from .artifact_store import SimulationArtifactStore, resolve_default_store
from .persona_review_service import PersonaReviewService

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

CORE_FIELDS = ("bio", "persona", "profession")

# Diversity ratio below this triggers a warning. Above stays informational.
_DIVERSITY_WARN_THRESHOLD = 0.34


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


class PersonaQualityService:
    """Compute quality hints for the personas of a single simulation."""

    def __init__(
        self,
        store: Optional[SimulationArtifactStore] = None,
        *,
        review_service: Optional[PersonaReviewService] = None,
    ) -> None:
        self._store = store or resolve_default_store()
        self._reviews = review_service or PersonaReviewService(self._store)

    def evaluate(self, simulation_id: str) -> Dict[str, Any]:
        profiles = self._reviews.list_profiles(simulation_id)
        username_counts = Counter(_norm(p.get("username")) for p in profiles)
        name_counts = Counter(
            _norm(p.get("name")) for p in profiles if _norm(p.get("name"))
        )

        personas = [
            self._evaluate_persona(profile, username_counts, name_counts)
            for profile in profiles
        ]

        summary = self._build_summary(profiles)
        global_issues = self._build_global_issues(profiles, summary)

        return {
            "simulation_id": simulation_id,
            "summary": summary,
            "global_issues": global_issues,
            "personas": personas,
        }

    # ------------------------------------------------------------------
    # Per-persona checks
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_persona(
        profile: Dict[str, Any],
        username_counts: Counter,
        name_counts: Counter,
    ) -> Dict[str, Any]:
        issues: List[Dict[str, Any]] = []
        username = profile.get("username")
        username_key = _norm(username)
        if username_key and username_counts[username_key] > 1:
            issues.append({
                "code": "duplicate_username",
                "severity": SEVERITY_ERROR,
                "detail": {"username": username},
            })

        name_key = _norm(profile.get("name"))
        if name_key and name_counts[name_key] > 1:
            issues.append({
                "code": "duplicate_name",
                "severity": SEVERITY_WARNING,
                "detail": {"name": profile.get("name")},
            })

        missing = [field for field in CORE_FIELDS if _is_blank(profile.get(field))]
        if missing:
            severity = (
                SEVERITY_ERROR if len(missing) == len(CORE_FIELDS)
                else SEVERITY_WARNING
            )
            issues.append({
                "code": "missing_core_fields",
                "severity": severity,
                "detail": {"missing": missing},
            })

        if not profile.get("is_manual") and not profile.get("source_entity_uuid"):
            issues.append({
                "code": "missing_entity_link",
                "severity": SEVERITY_INFO,
                "detail": None,
            })

        return {
            "username": username,
            "review_status": profile.get("review_status"),
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # Summary + global issues
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(profiles)
        status_counts = Counter(p.get("review_status") for p in profiles)
        professions = {_norm(p.get("profession")) for p in profiles if _norm(p.get("profession"))}
        mbti_values = {_norm(p.get("mbti")) for p in profiles if _norm(p.get("mbti"))}

        return {
            "total": total,
            "approved": status_counts.get("approved", 0),
            "pending": status_counts.get("pending", 0),
            "rejected": status_counts.get("rejected", 0),
            "role_diversity": (len(professions) / total) if total else 0.0,
            "mbti_diversity": (len(mbti_values) / total) if total else 0.0,
            "distinct_roles": sorted(professions),
            "distinct_mbti": sorted(mbti_values),
        }

    @classmethod
    def _build_global_issues(
        cls, profiles: List[Dict[str, Any]], summary: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        if not profiles:
            issues.append({
                "code": "no_personas",
                "severity": SEVERITY_WARNING,
                "detail": None,
            })
            return issues

        role_diversity = summary["role_diversity"]
        if len(summary["distinct_roles"]) <= 1:
            issues.append({
                "code": "role_diversity",
                "severity": SEVERITY_WARNING,
                "detail": {
                    "ratio": role_diversity,
                    "distinct_roles": summary["distinct_roles"],
                },
            })
        elif role_diversity < _DIVERSITY_WARN_THRESHOLD:
            issues.append({
                "code": "role_diversity",
                "severity": SEVERITY_INFO,
                "detail": {
                    "ratio": role_diversity,
                    "distinct_roles": summary["distinct_roles"],
                },
            })

        mbti_diversity = summary["mbti_diversity"]
        if len(summary["distinct_mbti"]) <= 1 and summary["total"] > 1:
            issues.append({
                "code": "mbti_diversity",
                "severity": SEVERITY_WARNING,
                "detail": {
                    "ratio": mbti_diversity,
                    "distinct_mbti": summary["distinct_mbti"],
                },
            })
        elif mbti_diversity and mbti_diversity < _DIVERSITY_WARN_THRESHOLD:
            issues.append({
                "code": "mbti_diversity",
                "severity": SEVERITY_INFO,
                "detail": {
                    "ratio": mbti_diversity,
                    "distinct_mbti": summary["distinct_mbti"],
                },
            })

        return issues


__all__ = [
    "PersonaQualityService",
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "CORE_FIELDS",
]
