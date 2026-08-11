"""Kandidatenauswahl der Bindungsphase (#1217).

Vor diesem Modul schnitt ``_build_claims_for_section`` die Kandidaten
**positionsbasiert** zu: ``_active_section_evidence[:10]`` plus
``global_evidence_refs[:6]``. Die Reihenfolge dieser Liste ist die
Erhebungsreihenfolge der Tool-Calls, nicht eine Rangfolge nach Relevanz —
und ein einziger ``insight_forge``-Call erzeugt bis zu 26 Items
(10 Facts + 8 Entities + 8 Chains). Das Zehnerfenster war damit nach dem
ersten Tool-Call gefuellt; die spaeter erhobenen Persona-Zitate
(``interview_agents``) und Seed-Corpus-Treffer (``quick_search``) waren fuer
die Bindung unerreichbar, obwohl sie im ``evidence_index`` stehen.

Der Pool dreht die Reihenfolge um: **erst bewerten, dann kuerzen**. Er
bekommt alle Kandidaten der Section, sortiert sie per Cosine gegen den
Claim-Text und gibt die semantisch naechsten weiter. Das Evidence-Gate
selbst (Threshold, Entailment, Confidence-Regeln) bleibt unberuehrt — dieses
Modul entscheidet nur, *was* das Gate ueberhaupt zu sehen bekommt.

Der Embedding-Cache ist kein Beiwerk, sondern die Bedingung dafuer, dass
das ueberhaupt bezahlbar ist: die Vektoren haengen am Text, nicht am Claim.
Vorher hat jeder Claim jeden Kandidaten neu eingebettet (30 Claims x 16
Kandidaten = 480 Calls pro Section, Issue #1187). Mit Cache faellt pro
Section einmal ``len(items)`` an, plus einen Call je Claim.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..evidence_binder import EmbedFn, _cosine, candidate_text

#: Wie viele Kandidaten pro Claim an den Binder gehen. Der Binder filtert
#: danach per Threshold und kuerzt auf ``top_k`` — diese Grenze begrenzt
#: also nur die Entailment-Aufrufe, nicht die Bindungschance.
DEFAULT_CANDIDATE_LIMIT = 12


class EvidenceCandidatePool:
    """Waehlt pro Claim die semantisch naechsten Evidence-Kandidaten.

    Der Pool ist bewusst zustandsbehaftet: er lebt genau eine Section lang
    und teilt seinen Embedding-Cache ueber alle Claims dieser Section.
    ``embed`` gibt dieselbe memoisierte Funktion heraus, die auch der Binder
    benutzen soll — sonst wuerde die zweite Stufe dieselben Texte erneut
    einbetten.
    """

    def __init__(
        self,
        items: Sequence[Dict[str, Any]],
        embed: EmbedFn,
        *,
        limit: int = DEFAULT_CANDIDATE_LIMIT,
    ) -> None:
        self._raw_embed = embed
        self._limit = max(1, limit)
        self._vectors: Dict[str, Optional[Sequence[float]]] = {}
        self._embed_calls = 0
        # Items ohne Text koennen weder eingebettet noch klassifiziert
        # werden — sie fielen im Binder ohnehin durch ``continue``.
        self._items: List[tuple[Dict[str, Any], str]] = [
            (item, text)
            for item in items
            if (text := candidate_text(item))
        ]

    # -- Embedding ---------------------------------------------------------

    @property
    def embed(self) -> EmbedFn:
        """Memoisierter Embedder — auch an ``bind_evidence_to_claim`` geben."""
        return self._embed_cached

    def _embed_cached(self, text: str) -> Sequence[float]:
        key = text.strip()
        if key in self._vectors:
            cached = self._vectors[key]
            if cached is None:
                raise RuntimeError("embedding previously failed for this text")
            return cached
        self._embed_calls += 1
        try:
            vector = self._raw_embed(key)
        except Exception:
            # Der Fehlschlag gehoert genauso in den Cache wie der Erfolg.
            # Ein Kandidat, der deterministisch scheitert (etwa ein
            # web_fetch-Record, dessen ``raw.content`` das Kontextfenster
            # sprengt), wuerde sonst fuer jeden Claim der Section erneut
            # versucht — samt Provider-Retries und Timeouts.
            self._vectors[key] = None
            raise
        self._vectors[key] = vector
        return vector

    @property
    def embed_calls(self) -> int:
        """Zahl der tatsaechlich durchgereichten Embed-Aufrufe (fuer Tests)."""
        return self._embed_calls

    # -- Auswahl -----------------------------------------------------------

    def select(self, claim_text: str) -> List[Dict[str, Any]]:
        """Die dem Claim naechsten Kandidaten, absteigend nach Cosine.

        Kein Threshold: das Aussortieren ist Sache des Binders (Stufe 1) und
        des Entailments (Stufe 2). Hier wird nur die Reihenfolge hergestellt,
        in der ein knappes Budget sinnvoll ausgegeben wird.

        Embedder-Fehler am Claim werden hochgereicht — der Caller faellt
        dann auf seinen generischen Pfad zurueck. Fehler an einem einzelnen
        Kandidaten kosten nur diesen Kandidaten seinen Rang, nicht die
        Section.
        """
        claim = (claim_text or "").strip()
        if not claim or not self._items:
            return []

        claim_vector = self._embed_cached(claim)
        scored: List[tuple[float, int, Dict[str, Any]]] = []
        for position, (item, text) in enumerate(self._items):
            try:
                score = _cosine(claim_vector, self._embed_cached(text))
            except Exception:  # noqa: BLE001 — ein defektes Item darf die Section nicht kippen
                score = 0.0
            # position als Tiebreaker: gleiche Scores behalten die
            # Erhebungsreihenfolge, damit die Auswahl deterministisch ist.
            scored.append((-score, position, item))

        scored.sort(key=lambda entry: (entry[0], entry[1]))
        return [item for _, _, item in scored[: self._limit]]


__all__ = ["DEFAULT_CANDIDATE_LIMIT", "EvidenceCandidatePool"]
