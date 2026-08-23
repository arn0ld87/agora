"""Issue #1303 — Panel-Rotation fuer Abschnitts-Interviews.

Empirischer Befund des Referenzlaufs: Abschnitt 1, 3 und 5 interviewten
praktisch dasselbe Fuenferpanel. Mehr Interviews machten den bestehenden
Konsens nur lauter, statt neue Perspektiven zu bringen — die LLM-Auswahl in
``GraphToolsService._select_agents_for_interview`` hatte kein Run-Gedaechtnis.

``InterviewPanelTracker`` ist dieses Gedaechtnis. Pro Report-Lauf (eine
``GraphToolsService``-Instanz lebt genau einen Lauf lang) zaehlt er, wie oft
jede Persona bereits befragt wurde, und ordnet Kandidaten drei
Prioritaetsklassen zu:

1. **frisch** — noch nie befragt; immer bevorzugt.
2. **wiederverwendbar** — unter dem Diversitaetslimit UND der neue Aspekt
   unterscheidet sich signifikant von allen frueheren Aspekten dieser Persona.
3. **Ausschoepfungs-Fallback** — nur wenn die Klassen 1 und 2 das gewuenschte
   Panel nicht fuellen: Wiederverwendung trotz Limit, mit anderem Aspekt
   bevorzugt, gleicher Aspekt als letzter Ausweg.

Interpretation von "signifikant anderer Kontext/Aspekt" (#1303): zwei
Anforderungstexte gelten als unterschiedlich, wenn ihre Inhaltswoerter
(>= 4 Zeichen, Stopwoerter entfernt) eine Jaccard-Aehnlichkeit unterhalb
``CONTEXT_SIMILARITY_THRESHOLD`` haben. Das ist bewusst lexikalisch und
billig — ein zweiter Judge-LLM-Call je Section waere im Referenzlauf 32
zusaetzliche Calls fuer wenig Zuwachs gewesen.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

DEFAULT_MAX_INTERVIEWS_PER_PERSONA = 2

#: Jaccard-Schwelle: darunter gilt eine neue Interview-Anforderung als
#: signifikant anderer Aspekt als eine fruehere.
CONTEXT_SIMILARITY_THRESHOLD = 0.5

#: Woerter, die keinen Aspekt tragen und aus dem Aehnlichkeitsvergleich
#: fliegen. Bewusst klein — Falsch-Positive hier verteuern nur die Schwelle,
#: nicht die Korrektheit.
_ASPECT_STOPWORDS = frozenset({
    "aber", "alle", "allem", "allen", "auch", "auf", "aus", "bei", "dem",
    "den", "der", "des", "dessen", "die", "dies", "diese", "dieser",
    "doch", "durch", "ein", "eine", "einem", "einen", "einer", "erhält",
    "fuer", "für", "gegen", "haben", "hatte", "hier", "ihre", "ihren",
    "immer", "ist", "jede", "jeden", "kann", "keine", "können", "macht",
    "mehr", "mit", "muss", "nach", "nicht", "noch", "nur", "oder", "ohne",
    "sehr", "sein", "sich", "sind", "soll", "sonst", "über", "um", "und",
    "unter", "vom", "von", "vor", "was", "weg", "weil", "weiter", "welche",
    "wenn", "werde", "werden", "wie", "wieder", "will", "wir", "wird",
    "wurde", "zu", "zum", "zur", "zwar", "zwischen",
})


def aspect_tokens(text: str) -> frozenset[str]:
    """Inhaltswoerter einer Anforderung: lowercase, >= 4 Zeichen, Stopwoerter raus."""
    tokens = set()
    for word in str(text or "").lower().split():
        cleaned = word.strip(".,;:!?\u201e\u201c\"'()[]{}—–-")
        if len(cleaned) >= 4 and cleaned not in _ASPECT_STOPWORDS:
            tokens.add(cleaned)
    return frozenset(tokens)


def aspects_differ(a: str, b: str) -> bool:
    """Unterscheiden sich zwei Anforderungen signifikant als Aspekt?"""
    tokens_a = aspect_tokens(a)
    if not tokens_a:
        # Ohne tragfähige Tokens keine Behauptung ueber Gleichheit wagen —
        # wir behandeln das als "anders" statt Panels leerzukürzen.
        return True
    union = tokens_a | aspect_tokens(b)
    if not union:
        return True
    similarity = len(tokens_a & aspect_tokens(b)) / len(union)
    return similarity < CONTEXT_SIMILARITY_THRESHOLD


def panel_overlap_ratio(panel_a: Iterable[str], panel_b: Iterable[str]) -> float:
    """Panel-Ueberlappung als Jaccard-Koeffizient ueber Persona-Namen.

    1.0 = identische Panels, 0.0 = keine gemeinsame Persona. Leere Panels
    liefern 0.0 statt zu teilen durch null.
    """
    set_a = {name for name in panel_a if name}
    set_b = {name for name in panel_b if name}
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


class InterviewPanelTracker:
    """Trackt pro Report-Lauf, welche Personas bereits interviewt wurden."""

    def __init__(self, max_interviews_per_persona: int | None = None):
        self.max_interviews_per_persona = (
            max_interviews_per_persona
            if max_interviews_per_persona is not None
            else DEFAULT_MAX_INTERVIEWS_PER_PERSONA
        )
        self._usage: dict[str, int] = {}
        self._contexts: dict[str, list[str]] = {}

    @staticmethod
    def persona_key(profile: Mapping) -> str:
        """Stabile Identitaet einer Persona ueber Sections hinweg."""
        name = profile.get("username") or profile.get("realname") or ""
        return str(name).strip().casefold()

    def usage(self, persona_key: str) -> int:
        return self._usage.get(persona_key, 0)

    def contexts_of(self, persona_key: str) -> list[str]:
        return list(self._contexts.get(persona_key, []))

    def _is_reusable(self, persona_key: str, requirement: str) -> bool:
        """Klasse 2: unter dem Limit UND jeder fruehere Aspekt deutlich anders."""
        if self.usage(persona_key) >= self.max_interviews_per_persona:
            return False
        return all(
            aspects_differ(requirement, previous)
            for previous in self._contexts.get(persona_key, [])
        )

    def apply_selection(
        self,
        profiles: Sequence[Mapping],
        selected_indices: Sequence[int],
        requirement: str,
    ) -> tuple[list[int], str]:
        """Haertet die LLM-Auswahl gegen die Diversitaetsregeln.

        Liefert ``(final_indices, note)``. ``note`` erklaert Eingriffe und
        wird vom Caller an ``selection_reasoning`` angehaengt — die Rotation
        soll im Berichts-Trace nachvollziehbar bleiben.

        Die Relevanz-Rangfolge des LLM gilt innerhalb jeder Klasse weiter;
        Klassen schlagen Rangfolge: frisch > regelkonforme Wiederverwendung >
        Ausschoepfungs-Fallback.
        """
        ordered: list[int] = []
        seen: set[int] = set()
        for idx in selected_indices:
            if isinstance(idx, bool) or not isinstance(idx, int):
                continue
            if 0 <= idx < len(profiles) and idx not in seen:
                seen.add(idx)
                ordered.append(idx)
        if not ordered:
            return [], ""

        keys = [self.persona_key(profile) for profile in profiles]

        llm_set = set(ordered)
        position = {idx: pos for pos, idx in enumerate(ordered)}

        def class_rank(idx: int) -> int:
            usage = self.usage(keys[idx])
            if usage == 0:
                return 0
            if self._is_reusable(keys[idx], requirement):
                return 1
            return 2

        def sort_key(idx: int) -> tuple[int, int]:
            # Innerhalb einer Klasse gilt weiter: vom LLM Genaannte vor
            # Nachrueckern, unter den Genannten deren Relevanz-Reihenfolge.
            if idx in llm_set:
                return class_rank(idx), position[idx]
            return class_rank(idx), len(ordered) + idx

        ranked = sorted(range(len(profiles)), key=sort_key)
        final = ranked[: len(ordered)]

        notes: list[str] = []
        replaced = [i for i in ordered if i not in final]
        if replaced and all(class_rank(i) < 2 for i in final):
            names = ", ".join(str(i) for i in replaced)
            notes.append(
                f"Panel-Rotation: Auswahlpositionen [{names}] zugunsten "
                f"noch nicht befragter bzw. regelkonform wiederverwendbarer "
                f"Personas ersetzt"
            )
        elif any(class_rank(i) == 2 for i in final):
            exhausted = any(self.usage(keys[i]) >= self.max_interviews_per_persona for i in final)
            if exhausted:
                notes.append(
                    "Panel-Ausschoepfung: alle Personas am Diversitaetslimit — "
                    "Wiederverwendung mit anderem Aspekt bevorzugt"
                )

        return final, "; ".join(notes)

    def record(
        self,
        profiles: Sequence[Mapping],
        indices: Sequence[int],
        requirement: str,
    ) -> None:
        """Verbucht tatsaechlich durchgefuehrte Interviews (nicht Versuche)."""
        for idx in indices:
            if not 0 <= idx < len(profiles):
                continue
            key = self.persona_key(profiles[idx])
            self._usage[key] = self.usage(key) + 1
            self._contexts.setdefault(key, []).append(requirement)
