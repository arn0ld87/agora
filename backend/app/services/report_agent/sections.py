from __future__ import annotations

import re
from html import escape
from typing import Any, Callable, Dict, List, Optional

from ..evidence_binder import _cosine


CLAIM_VERB_HINTS = (
    " ist ", " sind ", " war ", " waren ", " wird ", " werden ",
    " soll ", " sollen ", " kann ", " können ", " muss ", " müssen ",
    " hat ", " haben ", " erklärt", " fordert", " kritisiert",
    " betont", " sagt", " warnt", " beschloss", " plant",
    " antwortete", " unterstützt",
)


def truncate_text(text: str, limit: int = 300) -> str:
    if not text:
        return ""
    text = str(text).strip()
    return text if len(text) <= limit else text[:limit] + "..."


def sample_actions_timeseries(
    actions: List[Dict[str, Any]], k: int = 8
) -> List[Dict[str, Any]]:
    if not actions:
        return []
    if len(actions) <= k:
        return list(actions)

    def sort_key(a: Dict[str, Any]) -> Any:
        r = a.get("round_num")
        if r is not None:
            return (0, r, str(a.get("action_id") or a.get("id") or ""))
        ts = a.get("created_at") or a.get("timestamp")
        if ts is not None:
            return (1, str(ts), "")
        return (2, 0, "")

    sorted_actions = sorted(actions, key=sort_key)
    n = len(sorted_actions)
    sampled: List[Dict[str, Any]] = []
    for bin_idx in range(k):
        start = (bin_idx * n) // k
        end = ((bin_idx + 1) * n) // k
        if start >= end:
            continue
        picked = dict(sorted_actions[start])
        raw_marker = picked.setdefault("_sampling", {})
        raw_marker["bin"] = bin_idx
        raw_marker["bin_total"] = k
        raw_marker["sampled_from_total"] = n
        sampled.append(picked)
    return sampled


def atomize_claim_chunk(chunk: str) -> List[str]:
    cleaned = (chunk or "").strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[a-zäöüß][.!?])\s+(?=[A-ZÄÖÜ])", cleaned)
    return [p.strip() for p in parts if p.strip()]


def is_atomic_claim(text: str) -> bool:
    s = (text or "").strip()
    if len(s.split()) < 5:
        return False
    if s.endswith((".", "!", "?")):
        return True
    return any(hint in s.lower() for hint in CLAIM_VERB_HINTS)


def is_claim_candidate(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if (
        stripped.startswith("**")
        and stripped.endswith("**")
        and stripped.count("**") == 2
        and len(stripped.split()) < 8
    ):
        return False
    if re.fullmatch(r"[-*]\s*\*\*[^*]+\*\*\s*", stripped):
        return False
    return True


def build_source_id_anchor(item: Dict[str, Any]) -> Optional[str]:
    ref = item.get("agent_log_ref") or {}
    if isinstance(ref, dict):
        log_id = ref.get("agent_log_id") or ref.get("log_id")
        entry = ref.get("entry_id") or ref.get("post_id")
        if log_id and entry:
            return f"agent-log-{log_id}#entry-{entry}"
        if log_id:
            return f"agent-log-{log_id}"
    raw = item.get("raw") or {}
    if isinstance(raw, dict):
        url = raw.get("url") or raw.get("source_url")
        text = raw.get("text") or raw.get("content") or item.get("snippet") or ""
        if url:
            if text:
                fragment = text.strip().split("\n", 1)[0][:60]
                return f"web:{url}#:~:text={fragment}"
            return f"web:{url}"
    return None


def attach_provenance(item: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return item
    if not item.get("quote"):
        raw = item.get("raw") or {}
        candidate = None
        if isinstance(raw, dict):
            candidate = raw.get("text") or raw.get("content")
        candidate = candidate or item.get("snippet")
        if candidate:
            quote = str(candidate).strip()
            if quote:
                item["quote"] = quote[:500]
    if not item.get("source_id_anchor"):
        anchor = build_source_id_anchor(item)
        if anchor:
            item["source_id_anchor"] = anchor[:200]
    return item


def _format_confidence_score(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _claim_text_for_markdown(claim: Dict[str, Any]) -> str:
    text = str(claim.get("claim_text") or claim.get("claim") or "").strip()
    text = re.sub(r"\s+", " ", text)
    return escape(truncate_text(text, 1000), quote=False) or "Claim-Text nicht verfügbar."


def render_claim_to_markdown(claim: Dict[str, Any]) -> str:
    """Render sichtbare Confidence-Marker fuer Markdown-/Print-Export."""
    label = str(claim.get("confidence_label") or claim.get("confidence") or "").lower()
    score = _format_confidence_score(claim.get("confidence_score"))
    text = _claim_text_for_markdown(claim)

    if label == "low":
        return (
            '> <span class="conf-badge conf-low">'
            f"⚠️ Low-Confidence-Hinweis (score={score})"
            f"</span>: {text}"
        )
    if label == "medium":
        return (
            f'- {text} <span class="conf-badge conf-medium">'
            f"medium-confidence (score={score})"
            "</span>"
        )
    return ""


def render_confidence_markers_for_section(section: Optional[Dict[str, Any]]) -> str:
    if not section:
        return ""
    rendered = [
        marker for claim in section.get("claims") or []
        if (marker := render_claim_to_markdown(claim))
    ]
    if not rendered:
        return ""
    return "\n".join(["**Konfidenz-Hinweise**", "", *rendered])


def section_dedup_check(
    new_summary: str,
    existing: List[Dict[str, Any]],
    *,
    get_embedder: Callable[[], Optional[Callable[[str], List[float]]]],
    logger: Any,
) -> Optional[Dict[str, Any]]:
    if not new_summary or not existing:
        return None
    new_norm = (new_summary or "").strip()
    if not new_norm:
        return None
    embedder = get_embedder()
    if embedder is not None:
        try:
            new_vec = embedder(new_norm)
            for sec in existing:
                other = (sec.get("section_summary") or "").strip()
                if not other:
                    continue
                other_vec = embedder(other)
                sim = float(_cosine(new_vec, other_vec))
                if sim >= 0.92:
                    return {
                        "type": "model_generated_inference",
                        "source": "section_dedup",
                        "tool_name": "section_dedup_check",
                        "snippet": f"duplicate_of_section_{sec.get('section_index')}",
                        "raw": {
                            "similarity": round(sim, 4),
                            "method": "cosine",
                            "matched_section_index": sec.get("section_index"),
                        },
                    }
        except Exception as exc:
            logger.warning(f"Section-Dedup cosine fail, jaccard fallback: {exc!r}")

    def tokens(s: str) -> set[str]:
        return {t for t in re.split(r"\W+", (s or "").lower()) if len(t) > 2}

    new_tok = tokens(new_norm)
    if not new_tok:
        return None
    for sec in existing:
        other_tok = tokens(sec.get("section_summary") or "")
        if not other_tok:
            continue
        inter = len(new_tok & other_tok)
        union = len(new_tok | other_tok)
        if union == 0:
            continue
        jac = inter / union
        if jac >= 0.85:
            return {
                "type": "model_generated_inference",
                "source": "section_dedup",
                "tool_name": "section_dedup_check",
                "snippet": f"duplicate_of_section_{sec.get('section_index')}",
                "raw": {
                    "similarity": round(jac, 4),
                    "method": "jaccard",
                    "matched_section_index": sec.get("section_index"),
                },
            }
    return None


__all__ = [
    "attach_provenance",
    "atomize_claim_chunk",
    "build_source_id_anchor",
    "is_atomic_claim",
    "is_claim_candidate",
    "render_claim_to_markdown",
    "render_confidence_markers_for_section",
    "sample_actions_timeseries",
    "section_dedup_check",
    "truncate_text",
]
