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
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Sequence, Tuple

if TYPE_CHECKING:  # pragma: no cover - nur für Typprüfung
    from .evidence_entailment import EntailmentJudge

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


def candidate_text(item: Dict[str, Any]) -> str:
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


#: Alias fuer Alt-Aufrufer; ``candidate_text`` ist seit #1217 die oeffentliche
#: Form, weil die Kandidatenauswahl (``evidence_candidates``) dieselbe
#: Textextraktion braucht wie das Binding.
_candidate_text = candidate_text


def bind_evidence_to_claim(
    claim_text: str,
    candidates: List[Dict[str, Any]],
    embed: EmbedFn,
    *,
    threshold: float = 0.65,
    top_k: int = 5,
    judge: "EntailmentJudge | None" = None,
) -> List[Dict[str, Any]]:
    """Bindet Evidence an einen Claim — in zwei getrennten Stufen.

    Stufe 1 (Retrieval): Cosine-Similarity findet Kandidaten und schreibt
    ``retrieval_score``. Sie beantwortet nur, ob beide Texte vom selben
    Thema handeln.

    Stufe 2 (Entailment): :func:`classify_evidence` entscheidet, ob die
    Evidence den Claim trägt, und schreibt ``entailment``. Nur das Urteil
    ``SUPPORTED`` setzt ``supports_claim=True``; ``CONTRADICTED`` setzt
    zusätzlich ``contradicts_claim=True``.

    ``match_score`` bleibt als Alias von ``retrieval_score`` erhalten, damit
    bestehende Consumer (confidence_calculator, Contracts, Frontend) ohne
    Migration weiterlaufen — es ist aber ausdrücklich ein Retrieval-Wert und
    kein Beleggrad.

    Items unter dem Threshold fallen raus, der Rest wird nach Score
    absteigend sortiert und auf ``top_k`` gekürzt.

    Empty/whitespace-only Claim oder keine Kandidaten → leere Liste.
    Embedder-Errors werden hochgereicht; der Caller entscheidet ob er
    fallen lässt (ReportAgent fängt das in seinem Try-Block).
    """
    from .evidence_entailment import EntailmentVerdict, classify_evidence  # noqa: PLC0415
    from .numeric_evidence import shares_numeric_fact  # noqa: PLC0415

    if not (claim_text or "").strip() or not candidates:
        return []

    claim_vec = embed(claim_text.strip())
    # Der numerische Treffer gehört in die Sortierung, nicht in die Bindung:
    # ``ClaimEvidenceBindingModel`` ist ``extra="forbid"``, und ein
    # zusätzliches Feld auf ``bound`` lässt die gesamte Section-Validierung
    # scheitern — bis hin zum Reparaturlauf, der dann jeden Claim mit
    # gebundener Evidence löscht.
    scored: List[Tuple[Dict[str, Any], Dict[str, Any], bool]] = []
    for item in candidates:
        text = candidate_text(item)
        if not text:
            continue
        # Deterministischer Vorabruf vor der Cosine-Schwelle. Eine Quelle, die
        # dieselbe Zahl in derselben Einheit nennt, ist einschlägig, auch wenn
        # sie es in ganz anderen Worten tut — und genau das war im
        # Referenzlauf der Regelfall: acht belegte Zahlen galten als unbelegt,
        # weil ihre Quellen die Retrieval-Schwelle nicht erreichten. Ob die
        # Quelle den Claim *trägt*, entscheidet unverändert das Entailment.
        numeric_hit = shares_numeric_fact(claim_text, text)
        try:
            cand_vec = embed(text)
        except Exception:  # pragma: no cover - safety net  # noqa: BLE001 — safety net; caller handles empty result
            continue
        score = _cosine(claim_vec, cand_vec)
        if score < threshold and not numeric_hit:
            continue

        # Canonical Records werden nicht in jeden Claim kopiert. Der
        # Legacy-Zweig ohne evidence_id bleibt nur fuer interne Alt-Caller;
        # persistierte v3-Maps akzeptieren ausschliesslich Bindings.
        evidence_id = item.get("evidence_id")
        bound = {"evidence_id": evidence_id} if evidence_id else dict(item)
        rounded = round(float(score), 3)
        bound["retrieval_score"] = rounded
        bound["match_score"] = rounded
        scored.append((bound, item, numeric_hit))

    # Erst kürzen, dann klassifizieren. Die Reihenfolge ist seit #1357 nicht
    # mehr beliebig: der Entailment-Check kann in der Grauzone einen LLM-Judge
    # befragen, und ein Claim mit zwanzig Kandidaten über der Retrieval-
    # Schwelle würde sonst zwanzig Calls auslösen, von denen fünfzehn ohnehin
    # verworfen werden. So ist das Judge-Budget durch ``top_k`` gedeckelt.
    #
    # Der Preis: ein widersprechendes Item mit schwachem Retrieval-Score fällt
    # jetzt heraus, statt ``contradicts_claim`` zu setzen. Das ist vertretbar,
    # weil eine Quelle, die dem Claim inhaltlich widerspricht, ihn thematisch
    # trifft und damit oben landet.
    # Numerische Treffer zuerst: sie sind deterministisch einschlägig, während
    # der Retrieval-Score eine Schätzung ist. Ohne diesen Vorrang verdrängte
    # ein thematisch naher Kandidat ohne Zahlen genau die Quelle, wegen der
    # der Claim geprüft wird.
    scored.sort(
        key=lambda entry: (entry[2], entry[0]["retrieval_score"]),
        reverse=True,
    )

    results: List[Dict[str, Any]] = []
    for bound, item, _numeric_hit in scored[:top_k]:
        result = classify_evidence(
            claim_text,
            item,
            judge=judge,
            retrieval_score=bound["retrieval_score"],
        )
        bound["entailment"] = result.verdict.value
        bound["entailment_reason"] = result.reason
        bound["supports_claim"] = result.verdict is EntailmentVerdict.SUPPORTED
        if result.verdict is EntailmentVerdict.CONTRADICTED:
            bound["contradicts_claim"] = True
        results.append(bound)
    return results


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

    # Regel 1: Explizite Boolean-Contradiction-Flags.
    #
    # #1327: Die Schleife laeuft bewusst ueber ``supporting`` und NICHT ueber
    # die volle ``evidence``-Liste. Der Producer ``bind_evidence_to_claim``
    # setzt ``contradicts_claim`` nur bei ``EntailmentVerdict.CONTRADICTED``,
    # was zwangslaeufig ``supports_claim=False`` bedeutet — ein solches Item
    # erreicht diese Schleife also nie. Das sieht nach totem Code aus, ist
    # aber Absicht: ``confidence_calculator.partition_by_entailment`` zaehlt
    # genau dieses Item bereits als ``contradicting`` und der Rechner zieht
    # dafuer ``_CONTRADICTION_PENALTY_AMOUNT`` (0.2) ab. Wuerde diese Schleife
    # es zusaetzlich mit 0.15 belasten, waere derselbe Widerspruch doppelt
    # bestraft — ``report_agent/agent.py`` reicht das Ergebnis hier als
    # ``contradiction_penalty`` in genau jenen Rechner hinein.
    #
    # Was hier bleibt, ist der Fall, den der Entailment-Pfad nicht kennt: ein
    # stuetzendes Item, das ueber ``is_contradiction``/``contradiction`` aus
    # einer anderen Quelle als widerspruechlich markiert wurde.
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


__all__ = [
    "bind_evidence_to_claim",
    "candidate_text",
    "detect_contradiction_penalty",
    "EmbedFn",
]
