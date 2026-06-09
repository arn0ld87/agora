"""S4a — claim-spezifisches Evidence-Binding.

Vor S4a hatte der `report_agent` jedem Claim denselben generischen
Evidence-Pool (globale Metriken + erste 8 Actions) angehangen. Reviewer
hatte das als "dekorierter Report mit Evidence-Anmutung" bezeichnet.

Dieser Service nimmt einen Claim-Text + eine Kandidatenliste + einen
Embedder und liefert pro Kandidat einen Cosine-`match_score`. Threshold
und Top-K filtern; übrig bleibt nur Evidence, die semantisch zum Claim
passt.

Stateless, kein DB- oder Service-Container-Zugriff. Embedder wird per
Dependency-Injection reingereicht (Tests können einen deterministischen
Fake einsetzen).
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Sequence

EmbedFn = Callable[[str], Sequence[float]]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _candidate_text(item: Dict[str, Any]) -> str:
    """Verwendet die textuell aussagekräftigsten Felder eines Evidence-Items."""
    parts = [
        str(item.get("snippet") or ""),
        str(item.get("value") or ""),
    ]
    raw = item.get("raw")
    if isinstance(raw, dict):
        for key in ("content", "snippet", "summary", "name"):
            val = raw.get(key)
            if isinstance(val, str) and val:
                parts.append(val)
    elif isinstance(raw, str):
        parts.append(raw)
    return " ".join(p for p in parts if p).strip()


def bind_evidence_to_claim(
    claim_text: str,
    candidates: List[Dict[str, Any]],
    embed: EmbedFn,
    *,
    threshold: float = 0.65,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Bind ranked evidence to a claim by embedding cosine similarity.

    Returns deepcopy-freundliche neue Dicts mit zusätzlichem
    ``match_score`` (round 3 decimals) und ``supports_claim`` bool.
    Items unter dem Threshold fallen raus, der Rest wird nach Score
    absteigend sortiert und auf ``top_k`` gekürzt.

    Empty/whitespace-only Claim oder keine Kandidaten → leere Liste.
    Embedder-Errors werden hochgereicht; der Caller entscheidet ob er
    fallen lässt (ReportAgent fängt das in seinem Try-Block).
    """
    if not (claim_text or "").strip() or not candidates:
        return []

    claim_vec = embed(claim_text.strip())
    scored: List[Dict[str, Any]] = []
    for item in candidates:
        text = _candidate_text(item)
        if not text:
            continue
        try:
            cand_vec = embed(text)
        except Exception:  # pragma: no cover - safety net  # noqa: BLE001 — safety net; caller handles empty result
            continue
        score = _cosine(claim_vec, cand_vec)
        if score < threshold:
            continue
        bound = dict(item)
        bound["match_score"] = round(float(score), 3)
        bound["supports_claim"] = True
        scored.append(bound)

    scored.sort(key=lambda it: it["match_score"], reverse=True)
    return scored[:top_k]


def detect_contradiction_penalty(
    evidence: List[Dict[str, Any]],
    *,
    max_penalty: float = 0.5,
) -> float:
    """Ermittelt Penalty aus strukturierten Widerspruch-Flags.

    Wertet ausschliesslich strukturierte Felder aus — keine Textanalyse,
    keine Embeddings.

    Quellen (pro Treffer +0.15):
    1. Boolean-Felder: contradicts_claim, is_contradiction, contradiction
    2. Stance-Konflikte: Items mit gegensaetzlicher Haltung
       (support/oppose, pro/contra, positive/negative)

    Nur Items mit supports_claim=True werden geprueft.
    Gedeckelt auf max_penalty (default 0.5).
    """
    if len(evidence) < 2:
        return 0.0

    # Nur stützende Evidence betrachten
    supporting = [it for it in evidence if it.get("supports_claim") is True]
    if len(supporting) < 2:
        return 0.0

    penalty = 0.0

    # Regel 1: Explizite Boolean-Contradiction-Flags
    _bool_flags = ("contradicts_claim", "is_contradiction", "contradiction")
    for item in supporting:
        if any(item.get(flag) for flag in _bool_flags):
            penalty += 0.15

    # Regel 2: Stance-Konflikte zwischen Item-Paaren
    _opposing_stances = (
        ({"support"}, {"oppose"}),
        ({"pro"}, {"contra"}),
        ({"positive"}, {"negative"}),
    )

    for i in range(len(supporting)):
        for j in range(i + 1, len(supporting)):
            stance_a = supporting[i].get("stance")
            stance_b = supporting[j].get("stance")
            if not stance_a or not stance_b:
                continue
            sa, sb = str(stance_a).lower(), str(stance_b).lower()
            # Ein Konflikt gilt nur, wenn beide dieselbe Oppositions-Achse nutzen
            for side_a, side_b in _opposing_stances:
                axis = side_a | side_b
                if sa in axis and sb in axis and sa != sb:
                    penalty += 0.15
                    break  # nur einmal pro Paar zaehlen

    return round(min(penalty, max_penalty), 3)


__all__ = ["bind_evidence_to_claim", "detect_contradiction_penalty", "EmbedFn"]
