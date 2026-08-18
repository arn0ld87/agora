"""Buchführung darüber, was aus jedem quantitativen Tool-Fakt geworden ist.

Im Referenzlauf ``report_cc2ef45da5e9`` standen 31 %, 67 %, 83 %, 91 %, 6 %
und "sieben Fälle" in den Retrieval-Ergebnissen und fehlten anschließend im
kanonischen Evidence-Index. Kein Log, keine Meldung. Der Bericht führte die
Zahlen daraufhin als unbelegt — was aus seiner Sicht stimmte und aus Sicht
der Quellenlage falsch war.

Der Verlust selbst ist nicht immer ein Fehler: ein Dedup-Treffer ist gewollt,
ein Item ohne Producer-Schlüssel ist unbrauchbar. Der Fehler ist, dass sich
beides hinterher nicht auseinanderhalten ließ. Dieses Modul erzwingt die
Unterscheidung an der einen Stelle, an der jeder Fakt vorbeikommt: entweder
er trägt eine kanonische Evidence-ID, oder er trägt einen Grund.

Bewusst kein Ersatz für ``degradation_log``. Der protokolliert Entscheidungen
über *Claims* im fertigen Bericht; hier geht es um den Weg eines Fakts von
der Tool-Antwort in den Index, lange davor.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...contracts.report_contract import EvidenceCoverageEntry
from ..evidence_entailment import extract_numeric_facts

#: Wie viel Text ein Ledger-Eintrag vom Fakt behält. Lang genug, um den Fakt
#: wiederzuerkennen, kurz genug, dass ein Lauf mit hunderten Items die
#: persistierte Map nicht sprengt.
_FACT_TEXT_LIMIT = 300


class EvidenceCoverageLedger:
    """Sammelt den Verbleib quantitativer Fakten eines Report-Laufs.

    Nicht thread-safe und muss es nicht sein: die Evidence-Registrierung läuft
    im Report-Thread sequentiell. Ein Lock hier würde eine Nebenläufigkeit
    suggerieren, die es an dieser Stelle nicht gibt.
    """

    def __init__(self) -> None:
        self._entries: List[EvidenceCoverageEntry] = []

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    @property
    def entries(self) -> List[EvidenceCoverageEntry]:
        return list(self._entries)

    def as_payload(self) -> List[Dict[str, Any]]:
        """Serialisierte Form für die persistierte Evidence-Map."""
        return [entry.model_dump(mode="json") for entry in self._entries]

    def record(
        self,
        item: Dict[str, Any],
        *,
        status: str,
        canonical_evidence_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Bucht ein Evidence-Item — einen Eintrag je enthaltenem Zahlenfakt.

        Items ohne Zahl bleiben außen vor. Das Ledger beantwortet die Frage
        "ist ein quantitativer Fakt verlorengegangen?"; ein qualitatives
        Snippet trägt dazu nichts bei und würde die Buchführung mit dem
        gesamten Textverkehr des Laufs fluten.
        """
        text = _item_text(item)
        if not text:
            return
        facts = extract_numeric_facts(text)
        if not facts:
            return

        source_result_id = _source_result_id(item)
        for fact in facts:
            self._entries.append(
                EvidenceCoverageEntry(
                    source_result_id=source_result_id,
                    fact=(fact.raw or text)[:_FACT_TEXT_LIMIT],
                    status="canonicalized" if status == "canonicalized" else "dropped",
                    normalized_value=fact.value,
                    unit=fact.unit,
                    canonical_evidence_id=canonical_evidence_id,
                    reason=reason,
                )
            )

    def canonicalized(self, item: Dict[str, Any], evidence_id: str) -> None:
        self.record(item, status="canonicalized", canonical_evidence_id=evidence_id)

    def dropped(self, item: Dict[str, Any], reason: str) -> None:
        self.record(item, status="dropped", reason=reason)


def _item_text(item: Dict[str, Any]) -> str:
    if not isinstance(item, dict):
        return ""
    parts = [
        str(item.get(key) or "")
        for key in ("snippet", "quote", "value", "content", "text")
    ]
    return " ".join(part for part in parts if part).strip()


def _source_result_id(item: Dict[str, Any]) -> str:
    """Woher der Fakt kam.

    Der ``producer_key`` ist die genaueste Angabe, kann aber fehlen — sein
    Fehlen ist ja einer der Verwerfungsgründe. Dann tritt der Item-Typ an
    seine Stelle, damit der Eintrag trotzdem zuordenbar bleibt.
    """
    for key in ("producer_key", "source_id_anchor", "type", "source_kind"):
        value = str(item.get(key) or "").strip()
        if value:
            return value[:200]
    return "unknown"


def ledger_for(agent: Any) -> EvidenceCoverageLedger:
    """Der Ledger dieses Report-Laufs, bei Bedarf angelegt.

    Bewusst eine freie Funktion und keine Property auf ``ReportAgent``: mehrere
    Aufrufer reichen ein fremdes Objekt als ``self`` in die Agent-Methoden
    (Rehydrierung, Test-Doubles). Eine Property wäre dort schlicht nicht
    vorhanden und ließe die Buchführung an genau den Stellen abstürzen, an
    denen sie nichts zu suchen hat.
    """
    ledger = getattr(agent, "_evidence_coverage_ledger", None)
    if isinstance(ledger, EvidenceCoverageLedger):
        return ledger
    ledger = EvidenceCoverageLedger()
    try:
        agent._evidence_coverage_ledger = ledger
    except AttributeError:  # pragma: no cover — __slots__-Objekte
        pass
    return ledger


__all__ = ["EvidenceCoverageLedger", "ledger_for"]
