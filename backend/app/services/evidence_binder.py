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
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Sequence, Tuple

from .evidence_text import evidence_text
from .sentence_splitter import split_sentences

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
    """Der vollständige Vergleichstext eines Evidence-Items (#1766).

    Dünner Zugang zu :func:`app.services.evidence_text.evidence_text`, der
    einzigen Textprojektion — einschließlich der vollen Interviewantwort aus
    ``raw["response"]``.
    """
    return evidence_text(item)


#: Ab wie vielen Zeichen der Retrieval-Score nicht mehr gegen den ganzen Text
#: gebildet wird. Ein langer Text verdünnt den Cosine-Wert gegen einen
#: Ein-Satz-Claim: derselbe Satz erreicht im 300-Zeichen-Snippet 0.7 und in der
#: 2400-Zeichen-Antwort 0.2.
LONG_TEXT_CHARS = 600

#: Satzfenster für lange Texte: drei Sätze, zwei Sätze Schrittweite, höchstens
#: zwölf Fenster je Item. Der Deckel begrenzt die Embedding-Aufrufe; bei mehr
#: Fenstern werden sie gleichmäßig über den Text verteilt.
RETRIEVAL_WINDOW_SENTENCES = 3
RETRIEVAL_WINDOW_STEP = 2
MAX_RETRIEVAL_WINDOWS = 12


def _sentence_windows(text: str) -> List[str]:
    """Überlappende Satzfenster, gleichmäßig auf ``MAX_RETRIEVAL_WINDOWS`` gedeckelt."""
    sentences = split_sentences(text)
    size = RETRIEVAL_WINDOW_SENTENCES
    if len(sentences) <= size:
        return [" ".join(sentences)] if sentences else []
    starts = list(range(0, len(sentences) - size + 1, RETRIEVAL_WINDOW_STEP))
    # Der Schwanz gehört dazu, auch wenn die Schrittweite ihn überspringt.
    if starts[-1] + size < len(sentences):
        starts.append(len(sentences) - size)
    windows = [" ".join(sentences[start:start + size]) for start in starts]
    if len(windows) <= MAX_RETRIEVAL_WINDOWS:
        return windows
    last = len(windows) - 1
    picked = sorted({
        round(position * last / (MAX_RETRIEVAL_WINDOWS - 1))
        for position in range(MAX_RETRIEVAL_WINDOWS)
    })
    return [windows[position] for position in picked]


def _action_post_text(item: Dict[str, Any]) -> str:
    """Der Wortlaut eines Simulationsbeitrags, ohne Metabeschreibung.

    Das Snippet eines Belegs ``agent_action`` beginnt mit „<Name> CREATE_COMMENT
    on reddit in round 9:", und ``value`` wiederholt den Aktionstyp. Beides
    sagt nichts über den Inhalt und drückt den Cosine-Wert gegen einen Claim
    (Issue #1778: im Mittel 0,025 je Paar). Der Wortlaut steht unter
    ``raw["action_args"]["content"]``.
    """
    if item.get("type") != "agent_action":
        return ""
    raw = item.get("raw")
    args = raw.get("action_args") if isinstance(raw, dict) else None
    content = args.get("content") if isinstance(args, dict) else None
    return content.strip() if isinstance(content, str) else ""


def retrieval_texts(item: Dict[str, Any], text: str) -> List[str]:
    """Die Texte, gegen die der Retrieval-Score eines Items gebildet wird.

    Kurze Texte werden als Ganzes eingebettet. Bei langen Texten sind es der
    bisherige Kurztext (``snippet`` + ``value``, damit nichts schlechter wird
    als vor #1766) und die Satzfenster des Volltexts.

    Ein Simulationsbeitrag wird über seinen Wortlaut gefunden, nicht über die
    Metabeschreibung im Snippet (Issue #1778). Das betrifft nur das Retrieval:
    das Entailment liest weiter den vollen Vergleichstext mit Stimme und Runde.
    """
    post_text = _action_post_text(item)
    if post_text:
        if len(post_text) <= LONG_TEXT_CHARS:
            return [post_text]
        return _sentence_windows(post_text) or [post_text]
    if len(text) <= LONG_TEXT_CHARS:
        return [text]
    short = " ".join(
        part for part in (str(item.get("snippet") or ""), str(item.get("value") or "")) if part
    ).strip()
    texts = [short] if short else []
    texts.extend(_sentence_windows(text))
    return texts or [text]


def retrieval_score(
    claim_vec: Sequence[float],
    item: Dict[str, Any],
    text: str,
    embed: EmbedFn,
) -> "float | None":
    """Bester Cosine-Wert des Claims gegen die Retrieval-Texte eines Items.

    ``None``, wenn kein Text eingebettet werden konnte. Ein einzelner
    scheiternder Text (etwa ein Fenster über dem Kontextfenster des
    Embedders) kostet nur sich selbst, nicht das Item.
    """
    best: "float | None" = None
    for candidate in retrieval_texts(item, text):
        try:
            cand_vec = embed(candidate)
        except Exception as exc:  # noqa: BLE001, PERF203 — ein defekter Text darf das Item nicht kippen
            # Ein erschöpftes Run-Budget ist das Ende des Laufs, kein
            # defekter Text. Lokaler Import: ``run_budget`` zieht diesen
            # Modul-Baum sonst zirkulär.
            from .run_budget import reraise_if_budget_exceeded  # noqa: PLC0415

            reraise_if_budget_exceeded(exc)
            continue
        score = _cosine(claim_vec, cand_vec)
        if best is None or score > best:
            best = score
    return best


def _memoized(embed: EmbedFn) -> EmbedFn:
    """Einbettung je Text nur einmal pro Aufruf; Fehlschläge werden mitgemerkt."""
    cache: Dict[str, "Sequence[float] | None"] = {}

    def cached(text: str) -> Sequence[float]:
        key = text.strip()
        if key in cache:
            vector = cache[key]
            if vector is None:
                raise RuntimeError("embedding previously failed for this text")
            return vector
        try:
            vector = embed(key)
        except Exception:
            cache[key] = None
            raise
        cache[key] = vector
        return vector

    return cached


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
    reserved_slots: "Mapping[str, int] | None" = None,
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

    ``reserved_slots`` (Beleg-Typ → Anzahl) sichert einem Typ eigene Plätze in
    der Entailment-Stufe: Liegen unter den besten ``top_k`` weniger Items des
    Typs als reserviert, rücken die nächstbesten dieses Typs nach — sofern sie
    den Threshold erreichen. Threshold und Entailment gelten für sie
    unverändert; reserviert ist nur die Prüfung, nicht das Urteil.

    Empty/whitespace-only Claim oder keine Kandidaten → leere Liste.
    Embedder-Errors werden hochgereicht; der Caller entscheidet ob er
    fallen lässt (ReportAgent fängt das in seinem Try-Block).
    """
    from .evidence_entailment import EntailmentVerdict, classify_evidence  # noqa: PLC0415
    from .numeric_evidence import shares_numeric_fact  # noqa: PLC0415
    from .quantifier_claims import aggregate_quantifier_support  # noqa: PLC0415

    if not (claim_text or "").strip() or not candidates:
        return []

    # Ein Embedding je Text und Aufruf, auch wenn der Aufrufer keinen
    # memoisierenden Embedder reicht: lange Items bringen bis zu zwölf Fenster
    # mit, und dasselbe Fenster darf nicht zweimal bezahlt werden. Es wird
    # immer die übergebene Funktion benutzt, damit das Budget-Ledger greift.
    embed = _memoized(embed)
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
        # Bei langen Texten zählt das beste Satzfenster statt des verdünnten
        # Gesamttexts (#1766). ``None``: nichts davon war einbettbar.
        best_score = retrieval_score(claim_vec, item, text, embed)
        if best_score is None:
            continue
        score = best_score
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

    selected = _with_reserved_slots(scored, top_k, reserved_slots)

    results: List[Dict[str, Any]] = []
    classified: List[Tuple[Dict[str, Any], Dict[str, Any], List[str]]] = []
    for bound, item, _numeric_hit in selected:
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
        classified.append((bound, item, result.checks))
    # Ein Quantor („nahezu alle", „die meisten", „niemand") ist von keiner
    # einzelnen Quelle belegbar. Erst die Zählung über die Stimmen dieses
    # Claims entscheidet, ob die Kern-Belege ihn gemeinsam tragen (#1345).
    aggregate_quantifier_support(claim_text, classified)
    return results


def _with_reserved_slots(
    scored: List[Tuple[Dict[str, Any], Dict[str, Any], bool]],
    top_k: int,
    reserved_slots: "Mapping[str, int] | None",
) -> List[Tuple[Dict[str, Any], Dict[str, Any], bool]]:
    """Die besten ``top_k`` plus nachrückende Items reservierter Typen.

    ``scored`` ist bereits absteigend sortiert und enthält nur Items über dem
    Threshold. Die Reihenfolge bleibt erhalten; Nachrücker stehen hinten.
    """
    selected = list(scored[:top_k])
    if not reserved_slots:
        return selected
    rest = scored[top_k:]
    for evidence_type, slots in reserved_slots.items():
        missing = slots - sum(1 for _bound, item, _hit in selected if item.get("type") == evidence_type)
        if missing <= 0:
            continue
        selected.extend(
            [entry for entry in rest if entry[1].get("type") == evidence_type][:missing]
        )
    return selected


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
