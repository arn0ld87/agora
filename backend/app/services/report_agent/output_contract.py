"""Final-Content-Contract für generierte Report-Abschnitte.

Der Report-Agent darf pro Antwort genau eines tun: ein Tool aufrufen oder
finalen Abschnittstext liefern. Internes Überlegen, Toolplanung und
Beobachtungsprotokolle sind Arbeitsspuren und gehören nicht in den Report.

Die primäre Absicherung liegt im Prompt (siehe
``report_prompts/sections.py``): dort wird kein "Thought" mehr angefordert.
Dieses Modul ist die Durchsetzung dahinter — es ersetzt das frühere
``final_answer = response.strip()``, das jeden Modelloutput ungeprüft zum
Abschnittsinhalt gemacht hat.

Gestaffelt statt als Regex-Halde:

1. Strukturell — alles vor ``Final Answer:`` ist Arbeitsspur und entfällt.
2. Zeilenweise — Zeilen, die ein ReACT-Protokollpräfix tragen, entfallen.
3. Gate — bleibt danach nichts Berichtsfähiges übrig, ist der Output
   ungültig und wird abgelehnt statt notdürftig weitergereicht.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, List, Sequence

if TYPE_CHECKING:  # pragma: no cover - nur für Typprüfung
    from ...models.report import ReportStatus


class FinalContentRejected(ValueError):
    """Der Modelloutput enthält keinen berichtsfähigen Abschnittsinhalt."""

    def __init__(self, reason: str, *, removed_segments: Sequence[str] = ()) -> None:
        super().__init__(reason)
        self.reason = reason
        self.removed_segments = list(removed_segments)


@dataclass
class SanitizedContent:
    content: str
    removed_segments: List[str] = field(default_factory=list)


#: Protokoll-Präfixe des ReACT-Formats. Eine Zeile, die so beginnt, ist
#: Arbeitsspur — unabhängig davon, was dahinter steht.
_PROTOCOL_PREFIXES: tuple[str, ...] = (
    "thought:",
    "thoughts:",
    "action:",
    "action input:",
    "observation:",
    "reflection:",
    "plan:",
    "reasoning:",
    "gedanke:",
    "beobachtung:",
)

#: Formulierungen, mit denen Modelle ihre nächste Arbeitshandlung ankündigen.
#: Bewusst auf den Zeilenanfang verankert: "Ich werde" mitten in einem
#: Persona-Zitat ist legitimer Berichtsinhalt.
_PLANNING_OPENERS: tuple[str, ...] = (
    "let me ",
    "let's ",
    "i need to ",
    "i will ",
    "i'll ",
    "i should ",
    "i am going to ",
    "i'm going to ",
    "first, i ",
    "next, i ",
    "now i ",
    "ich werde jetzt ",
    "ich muss zuerst ",
    "lass mich ",
)

_TOOL_CALL_BLOCK_RE = re.compile(r"<tool_call>.*?</tool_call>", re.DOTALL | re.IGNORECASE)
#: Ein geöffneter, nie geschlossener Tool-Call. Der E2E-Lauf produzierte genau
#: das: das Modell lief in eine Endlosschleife und schrieb ein abgeschnittenes
#: `<tool_call>` mit tausenden Wiederholungen in den Abschnitt. Alles ab dem
#: offenen Tag ist Arbeitsspur.
_UNCLOSED_TOOL_CALL_RE = re.compile(r"<tool_call>", re.IGNORECASE)
_TOOL_CALL_MENTION_RE = re.compile(r"^\s*(?:tool[ _]call|tool-call)\b.*$", re.IGNORECASE)
_FINAL_ANSWER_RE = re.compile(r"final\s*answer\s*:", re.IGNORECASE)

#: Marker der Fallback-Texte, die eingesetzt werden, wenn die Generierung
#: eines Abschnitts fehlschlägt. Solcher Text darf niemals als Claim oder
#: Evidence weiterverarbeitet werden.
FALLBACK_MARKERS: tuple[str, ...] = (
    "konnte nicht generiert werden",
    "generate failed",
    "generatefailed",
    "llm returned empty",
    "llm lieferte eine leere antwort",
    "abschnitt konnte nicht",
    "section generation failed",
    "bitte später erneut",
    "pleaselaterretry",
)

#: Ohne so viele Zeichen ist ein Abschnitt kein Abschnitt.
#:
#: Herleitung (Handover P2.9): Messung an den realen Sections der Läufe
#: ``report_e2e_trust01`` (Opinion, COMPLETED) und ``report_e2e_full01``
#: (Full, FAILED) — kürzester echter Section-Inhalt 4230 Zeichen, längster
#: Fallback-Text 217 Zeichen. 40 liegt ~106x unter dem Minimum realer
#: Sections und ist damit konservativ: die Schwelle fängt nur leer oder
#: fast-leer gerenderte Outputs ab (z. B. ``## Titel`` ohne Body nach
#: Protokoll-Strip), nicht den Fallback-Text — den filtert
#: :func:`is_fallback_content` semantisch. 40 Zeichen entspricht etwa einem
#: minimalen sinnvollen Satz (6–8 Wörter); darunter ist kein fachlicher
#: Abschnittsinhalt möglich.
MIN_CONTENT_CHARS = 40

#: Ab so vielen Wiederholungen desselben Fragments gilt der Output als
#: degeneriert. Fachsprache wiederholt Begriffe, aber kein Berichtstext
#: wiederholt dieselbe 20-Zeichen-Sequenz zwanzigmal.
MAX_FRAGMENT_REPEATS = 20
_REPEAT_PROBE_LEN = 20


def _is_degenerate(text: str) -> bool:
    """Erkennt LLM-Endlosschleifen an exzessiver Selbstwiederholung."""
    if len(text) < _REPEAT_PROBE_LEN * MAX_FRAGMENT_REPEATS:
        return False
    probe = text[:_REPEAT_PROBE_LEN]
    if probe.strip() and text.count(probe) >= MAX_FRAGMENT_REPEATS:
        return True
    midpoint = len(text) // 2
    probe = text[midpoint : midpoint + _REPEAT_PROBE_LEN]
    return bool(probe.strip()) and text.count(probe) >= MAX_FRAGMENT_REPEATS


def _is_protocol_line(line: str) -> bool:
    stripped = line.strip().lstrip("*_>-# ").lower()
    if not stripped:
        return False
    if stripped.startswith(_PROTOCOL_PREFIXES):
        return True
    if stripped.startswith(_PLANNING_OPENERS):
        return True
    return bool(_TOOL_CALL_MENTION_RE.match(line))


def _strip_protocol_lines(text: str) -> tuple[str, List[str]]:
    kept: List[str] = []
    removed: List[str] = []
    for line in text.splitlines():
        if _is_protocol_line(line):
            removed.append(line.strip())
        else:
            kept.append(line)
    return "\n".join(kept), removed


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def is_fallback_content(text: str) -> bool:
    """True, wenn ``text`` ein Generierungs-Fehlertext statt Inhalt ist.

    Aufrufer nutzen das, um Claim-Extraktion, Evidence-Bindung und
    Metadaten-Extraktion für diesen Abschnitt zu überspringen.
    """
    lowered = (text or "").strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in FALLBACK_MARKERS)


def sanitize_final_content(raw: str) -> SanitizedContent:
    """Macht aus einem Modelloutput berichtsfähigen Abschnittsinhalt.

    Raises:
        FinalContentRejected: wenn nach dem Entfernen aller Arbeitsspuren
            kein tragfähiger Inhalt übrig bleibt. Der Aufrufer setzt dann
            den Fallback-Text und markiert den Abschnitt als fehlgeschlagen —
            er reicht nicht ungeprüft Modelloutput weiter.
    """
    text = raw or ""
    removed: List[str] = []

    # 1. Strukturell: alles vor dem letzten "Final Answer:" ist Arbeitsspur.
    matches = list(_FINAL_ANSWER_RE.finditer(text))
    if matches:
        cut = matches[-1].end()
        prefix = text[:cut].strip()
        if prefix:
            removed.append(prefix)
        text = text[cut:]

    # 2. Tool-Call-Blöcke entfernen — erst die vollständigen, dann alles ab
    #    einem offen gebliebenen Tag.
    for block in _TOOL_CALL_BLOCK_RE.findall(text):
        removed.append(block.strip())
    text = _TOOL_CALL_BLOCK_RE.sub("", text)

    unclosed = _UNCLOSED_TOOL_CALL_RE.search(text)
    if unclosed:
        removed.append(text[unclosed.start():].strip()[:500])
        text = text[: unclosed.start()]

    # 3. Zeilenweise Protokollspuren entfernen.
    text, line_removals = _strip_protocol_lines(text)
    removed.extend(line_removals)

    content = _collapse_blank_lines(text)

    if not content:
        raise FinalContentRejected(
            "Modelloutput bestand ausschließlich aus Arbeitsspuren",
            removed_segments=removed,
        )
    if len(content) < MIN_CONTENT_CHARS:
        raise FinalContentRejected(
            f"Abschnittsinhalt zu kurz ({len(content)} < {MIN_CONTENT_CHARS} Zeichen)",
            removed_segments=removed,
        )
    if is_fallback_content(content):
        raise FinalContentRejected(
            "Modelloutput ist ein Fehlertext, kein Abschnittsinhalt",
            removed_segments=removed,
        )
    if _is_degenerate(content):
        raise FinalContentRejected(
            "Modelloutput ist degeneriert (Endlosschleife mit Wiederholungen)",
            removed_segments=removed,
        )

    return SanitizedContent(content=content, removed_segments=removed)


def resolve_report_status(
    *,
    total_sections: int,
    failed_section_indices: Iterable[int],
    required_section_indices: Iterable[int] = (),
) -> "ReportStatus":
    """Ermittelt den Report-Status aus dem Erfolg der Einzelabschnitte.

    Eine fehlgeschlagene Pflichtsection macht den Report ``INCOMPLETE``. Der
    Rest bleibt nutzbar — der Nutzer sieht, was fehlt, statt ein ``COMPLETED``
    zu lesen, das der Report nicht einlöst.

    ``FAILED`` wird bewusst **nicht** hier erzeugt: der Workflow setzt ihn
    direkt bei.schema-Validierungsfehlern oder Totalausfällen
    (``workflow.py``), nicht aus der Section-Erfolgsbilanz. Jeder Aufrufer
    übergibt ``required_section_indices=list(range(1, total+1))`` — damit ist
    ``required`` nie leer und jede failed Section schlägt als ``INCOMPLETE``
    durch. Ein früherer ``FAILED``-Zweig (``len(failed) >= total_sections``)
    war unter dieser Aufruf invariant unreachable (CodeRabbit PR #929).
    """
    from ...models.report import ReportStatus  # noqa: PLC0415 — zyklischer Import

    failed = set(failed_section_indices)
    if not failed:
        return ReportStatus.COMPLETED

    required = set(required_section_indices)
    if required and failed & required:
        return ReportStatus.INCOMPLETE
    return ReportStatus.INCOMPLETE


def apply_degradation_downgrade(
    status: "ReportStatus",
    degradation_log: Iterable[Any],
) -> "ReportStatus":
    """Stuft COMPLETED auf INCOMPLETE ab, wenn Claims lokal degradiert wurden.

    Issue #1006: ein Report, in dem ein ADR-0002-Verstoss durch lokale
    Abstufung aufgefangen wurde, ist inhaltlich unvollständig — der Nutzer
    soll das sehen, statt ein COMPLETED zu lesen, das der Report nicht
    einlöst. Bereits INCOMPLETE- oder FAILED-Status werden nicht
    aufgewertet.
    """
    from ...models.report import ReportStatus  # noqa: PLC0415 — zyklischer Import

    if not degradation_log:
        return status
    if status == ReportStatus.COMPLETED:
        return ReportStatus.INCOMPLETE
    return status


def is_deliverable_report_status(status: "ReportStatus") -> bool:
    """True, wenn der Report ausgeliefert werden kann statt als Fehlschlag zu gelten.

    Issue #1006: ``INCOMPLETE`` ist ein Teilergebnis, kein technischer Fehler.
    Der Report existiert, ist lesbar und exportierbar — einzelne Claims wurden
    lokal abgestuft oder eine Section ist fehlgeschlagen. Wird er trotzdem in
    den failed-Zweig geschickt, liest der Nutzer "Report generation failed",
    obwohl das Ergebnis vorliegt; genau diese Zustellungslücke hätte die
    Degradierung aus #1006 in der Oberfläche wirkungslos gemacht.

    ``FAILED``, ``PENDING``, ``PLANNING`` und ``GENERATING`` sind ausdrücklich
    nicht auslieferbar.
    """
    from ...models.report import ReportStatus  # noqa: PLC0415 — zyklischer Import

    return status in (ReportStatus.COMPLETED, ReportStatus.INCOMPLETE)


__all__ = [
    "FALLBACK_MARKERS",
    "FinalContentRejected",
    "MIN_CONTENT_CHARS",
    "SanitizedContent",
    "apply_degradation_downgrade",
    "is_deliverable_report_status",
    "is_fallback_content",
    "resolve_report_status",
    "sanitize_final_content",
]
