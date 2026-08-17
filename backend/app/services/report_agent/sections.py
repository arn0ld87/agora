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


def render_claim_to_markdown(claim: Dict[str, Any], *, raw_html: bool = True) -> str:
    """Render sichtbare Confidence-Marker fuer Markdown-/Print-Export.

    Issue #1315: ``raw_html=True`` (Default, unveraendertes Verhalten) haengt
    das CSS-geklasste ``<span class="conf-badge ...">`` an — das braucht der
    HTML-/Print-Pfad (Rendering via ``marked`` + DOMPurify im Frontend,
    CSS in ``frontend/src/composables/useReportExports.ts`` und
    ``frontend/src/assets/styles/global.css``). Wird der Text stattdessen als
    reines Markdown konsumiert (z. B. Copy-to-Clipboard, roher .md-Export ohne
    HTML-Renderer), bleibt das Tag unrendert im Fliesstext sichtbar. Mit
    ``raw_html=False`` wird eine Markdown-native Variante ohne Roh-HTML
    geliefert (Fettung + Emoji statt Span). Kein bestehender Aufrufer wird
    umgestellt — der einzige Callsite (``render_confidence_markers_for_section``
    -> ``assemble_full_report``) behaelt den Default und damit exakt das
    bisherige Verhalten.
    """
    label = str(claim.get("confidence_label") or claim.get("confidence") or "").lower()
    score = _format_confidence_score(claim.get("confidence_score"))
    text = _claim_text_for_markdown(claim)

    if label == "low":
        if raw_html:
            return (
                '> <span class="conf-badge conf-low">'
                f"⚠️ Low-Confidence-Hinweis (score={score})"
                f"</span>: {text}"
            )
        return f"> **⚠️ Low-Confidence-Hinweis (score={score})**: {text}"
    if label == "medium":
        if raw_html:
            return (
                f'- {text} <span class="conf-badge conf-medium">'
                f"medium-confidence (score={score})"
                "</span>"
            )
        return f"- {text} **medium-confidence (score={score})**"
    return ""


#: Erkennt die von ``render_claim_to_markdown`` erzeugten HTML-Badges.
_CONF_BADGE_RE = re.compile(
    r'<span class="conf-badge[^"]*">(.*?)</span>',
    re.DOTALL,
)


def strip_raw_html_markers(content: str) -> str:
    """Wandelt Roh-HTML-Badges in Markdown-Fettung (#1315).

    ``markdown_content`` traegt die Badges bewusst als HTML — das Frontend
    rendert sie ueber ``marked`` und faerbt sie per CSS ein. Wird derselbe
    Text ohne HTML-Renderer ausgeliefert, etwa als Fallback des
    ``.md``-Exports, bleibt das Tag unrendert im Fliesstext stehen. Diese
    Funktion ist genau fuer diesen Fallback da und wird nicht auf den
    gespeicherten Inhalt selbst angewandt.
    """
    return _CONF_BADGE_RE.sub(
        lambda match: f"**{match.group(1).strip()}**", content or ""
    )


def render_confidence_markers_for_section(
    section: Optional[Dict[str, Any]], *, raw_html: bool = True
) -> str:
    if not section:
        return ""
    rendered = [
        marker for claim in section.get("claims") or []
        if (marker := render_claim_to_markdown(claim, raw_html=raw_html))
    ]
    if not rendered:
        return ""
    return "\n".join(["**Konfidenz-Hinweise**", "", *rendered])


def _hypothesis_text_for_markdown(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return escape(truncate_text(text, 1000), quote=False)


def render_hypotheses_for_section(section: Optional[Dict[str, Any]]) -> str:
    if not section:
        return ""
    hypotheses = section.get("hypotheses") or []
    if not hypotheses:
        return ""

    lines = ["### Hypothesen ohne Evidence", ""]
    for hypothesis in hypotheses:
        if not isinstance(hypothesis, dict):
            continue
        hypothesis_id = _hypothesis_text_for_markdown(
            hypothesis.get("hypothesis_id") or "hypothesis"
        )
        hypothesis_text = _hypothesis_text_for_markdown(
            hypothesis.get("hypothesis_text")
        )
        rationale = _hypothesis_text_for_markdown(hypothesis.get("rationale"))
        if not hypothesis_text:
            continue
        lines.append(f"- **{hypothesis_id}:** {hypothesis_text}")
        if rationale:
            lines.append(f"  - Rationale: {rationale}")
        suggestions = [
            _hypothesis_text_for_markdown(item)
            for item in (hypothesis.get("suggested_evidence") or [])
            if _hypothesis_text_for_markdown(item)
        ]
        if suggestions:
            lines.append(f"  - Suggested Evidence: {', '.join(suggestions)}")

    # #1315: Appendix-Hypothesen werden im Fließtext markiert (siehe
    # mark_hypotheses_in_content), standen hier bisher aber nirgends — der
    # Marker zeigte damit auf eine Liste, die den Satz nicht enthielt. Analog
    # zu den Datenlücken wird die Restzahl ausgewiesen statt sie zu verschweigen.
    appendix = [
        hypothesis
        for hypothesis in (section.get("hypotheses_appendix") or [])
        if isinstance(hypothesis, dict)
        and _hypothesis_text_for_markdown(hypothesis.get("hypothesis_text"))
    ]
    if appendix and len(lines) > 2:
        noun = "Hypothese" if len(appendix) == 1 else "Hypothesen"
        lines.append(
            f"- _{len(appendix)} weitere markierte {noun} stehen im "
            "maschinenlesbaren Evidence-Export._"
        )
    return "\n".join(lines) if len(lines) > 2 else ""


def mark_hypotheses_in_content(
    content: str,
    section: Optional[Dict[str, Any]],
) -> str:
    """Kennzeichnet Hypothesensätze direkt im narrativen Abschnitt (#1232).

    Das Evidence-Gate persistiert die atomisierte Aussage separat in
    ``hypotheses[]`` oder bei Überschreitung des sichtbaren Caps in
    ``hypotheses_appendix[]``. Ohne diese Markierung blieb dieselbe
    Zeichenfolge im Fließtext jedoch eine apodiktische Feststellung. Whitespace
    darf zwischen Atomisierung und Markdown-Persistenz variieren; deshalb wird
    er beim Abgleich flexibel behandelt.

    Issue #1315 — zwei Korrekturen gegenueber der urspruenglichen Fassung:
    - Nur der erste Treffer pro Hypothese wird markiert (vormals jedes
      Vorkommen via ``re.sub`` ohne ``count``), sonst wiederholt sich derselbe
      Marker bei wiederkehrenden Formulierungen im Fliesstext.
    - Ist eine Hypothese Teilstring einer laengeren, bereits markierten
      Hypothese, wird sie nicht erneut markiert (keine Marker-in-Marker-
      Verschachtelung). Genau das erzeugte die beobachteten drei Marker im
      selben Absatz.

    Beide Slots bleiben bewusst markiert. ``hypotheses_appendix`` haelt die
    Hypothesen jenseits des sichtbaren Caps — sie sind genauso unbelegt, und
    sie im Fliesstext unmarkiert zu lassen waere ein Rueckfall hinter #1232.
    """
    if not content or not section:
        return content

    marker = "**Hypothese (unbelegt):**"
    hypothesis_texts = {
        str(hypothesis.get("hypothesis_text") or "").strip()
        for slot in ("hypotheses", "hypotheses_appendix")
        for hypothesis in (section.get(slot) or [])
        if isinstance(hypothesis, dict)
        and str(hypothesis.get("hypothesis_text") or "").strip()
    }
    if not hypothesis_texts:
        return content

    claimed_spans: List[tuple[int, int]] = []
    for hypothesis_text in sorted(hypothesis_texts, key=len, reverse=True):
        pattern = r"\s+".join(
            re.escape(part) for part in re.split(r"\s+", hypothesis_text)
        )
        # Ueber alle Treffer laufen, nicht nur den ersten: liegt das erste
        # Vorkommen einer kurzen Hypothese innerhalb einer laengeren, bereits
        # markierten, kommt sie spaeter im Abschnitt womoeglich eigenstaendig
        # vor. Ein `re.search` haette sie dann ganz verworfen und den
        # eigenstaendigen Satz unmarkiert stehen lassen. Beansprucht wird
        # weiterhin hoechstens eine Fundstelle je Hypothese.
        for match in re.finditer(pattern, content, flags=re.IGNORECASE):
            start, end = match.span()
            overlaps_existing = any(
                start < claimed_end and end > claimed_start
                for claimed_start, claimed_end in claimed_spans
            )
            if overlaps_existing:
                continue
            claimed_spans.append((start, end))
            break

    if not claimed_spans:
        return content

    claimed_spans.sort(key=lambda span: span[0])
    pieces: List[str] = []
    cursor = 0
    for start, end in claimed_spans:
        pieces.append(content[cursor:start])
        pieces.append(f"{marker} {content[start:end]}")
        cursor = end
    pieces.append(content[cursor:])
    return "".join(pieces)


def render_data_gaps_for_section(section: Optional[Dict[str, Any]]) -> str:
    """Rendert die maschinenlesbaren Datenlücken direkt an ihrer Section."""
    if not section:
        return ""
    data_gaps = [
        gap for gap in (section.get("data_gaps") or []) if isinstance(gap, dict)
    ]
    if not data_gaps:
        return ""

    lines = ["### Datenlücken dieses Abschnitts", ""]
    visible_limit = 5
    for gap in data_gaps[:visible_limit]:
        gap_id = _hypothesis_text_for_markdown(gap.get("gap_id") or "gap")
        claim_text = _hypothesis_text_for_markdown(gap.get("claim_text"))
        reason = _hypothesis_text_for_markdown(gap.get("gap_reason"))
        suggested_fix = _hypothesis_text_for_markdown(gap.get("suggested_fix"))
        if not claim_text:
            continue
        lines.append(f"- **{gap_id}:** {claim_text}")
        if reason:
            lines.append(f"  - Grund: {reason}")
        if suggested_fix:
            lines.append(f"  - Nächster Schritt: {suggested_fix}")
    remaining = len(data_gaps) - visible_limit
    if remaining > 0:
        noun = "Datenlücke" if remaining == 1 else "Datenlücken"
        lines.append(
            f"- _{remaining} weitere {noun} stehen im maschinenlesbaren "
            "Evidence-Export._"
        )
    return "\n".join(lines) if len(lines) > 2 else ""


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
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
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
    "mark_hypotheses_in_content",
    "render_claim_to_markdown",
    "render_confidence_markers_for_section",
    "render_data_gaps_for_section",
    "render_hypotheses_for_section",
    "sample_actions_timeseries",
    "section_dedup_check",
    "truncate_text",
]
