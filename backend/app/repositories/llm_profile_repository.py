"""Port fuer LLM-Profil-Metadaten (docs/plans/supabase.md §10, PR 3).

Die Semantik ist die des heutigen SQLite-Stores und wird hier festgeschrieben,
damit ein zweiter Adapter sie nicht versehentlich anders auslegt. Drei Punkte
sind dabei keine Geschmacksfrage:

``get`` gibt ``None`` zurueck, wenn es das Profil nicht gibt — es wirft nicht.
Ein fehlendes Profil ist bei der Aufloesung einer Route ein erwarteter Fall,
kein Fehler, und die Aufrufer pruefen entsprechend auf ``None``.

``api_key`` verlaesst das Repository nur, wenn ein Aufrufer ihn ausdruecklich
mit ``include_api_key=True`` anfordert. Das ist der Pfad fuer den
Laufzeit-Resolver, der den Schluessel braucht, um einen Provider zu erreichen.
Jede API-Antwort nimmt den Vorgabewert und bekommt den Schluessel damit nie zu
sehen.

``list`` darf beim ersten Aufruf ein Bootstrap-Profil aus den ``LLM_*``-Env-
Variablen anlegen. Das ist Erstinbetriebnahme, kein Nebeneffekt, den ein
Adapter weglassen darf: ohne es steht eine frische Installation ohne jede
Route da.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ..config import Config, LLM_PROFILE_BACKENDS_NOT_YET_AVAILABLE
from ..contracts import LlmProfile, LlmProfileCreateRequest


class LlmProfileBackendUnavailable(RuntimeError):
    """Der konfigurierte Backend-Wert ist gültig, aber es gibt keinen Adapter.

    Kein `ValueError`: der Wert ist nicht falsch, er ist noch nicht bedient.
    Der Unterschied steht in der Meldung, damit niemand nach einem Tippfehler
    sucht, den es nicht gibt.
    """


@runtime_checkable
class LlmProfileRepository(Protocol):
    """Lesen und Schreiben von LLM-Profilen, unabhaengig von der Ablage."""

    def list(self) -> list[LlmProfile]:
        """Alle Profile, neuestes zuerst. Legt bei leerer Ablage das
        Bootstrap-Profil aus den ``LLM_*``-Env-Variablen an, sofern eines
        daraus ableitbar ist. Nie mit ``api_key``."""
        ...

    def get(self, profile_id: str, include_api_key: bool = False) -> Optional[LlmProfile]:
        """Ein Profil oder ``None``. ``include_api_key`` ist der einzige Weg,
        auf dem der Schluessel das Repository verlaesst."""
        ...

    def create(self, req: LlmProfileCreateRequest) -> LlmProfile:
        """Legt ein Profil an. Ist ``req.is_default`` gesetzt, verlieren alle
        anderen ihr Default-Flag — genau ein Profil ist Default."""
        ...

    def update(
        self, profile_id: str, req: LlmProfileCreateRequest
    ) -> Optional[LlmProfile]:
        """Aktualisiert ein Profil, oder ``None`` wenn es das nicht gibt.

        Fuer ``api_key`` gilt eine Dreiteilung, die ein Adapter genau so
        abbilden muss: ``None`` heisst „nicht mitgeschickt" und laesst den
        gespeicherten Schluessel unberuehrt, ``""`` heisst „ausdruecklich
        leeren", jeder andere Wert ersetzt ihn. Ohne die Unterscheidung
        loeschte jedes Speichern aus der Oberflaeche den Schluessel, denn die
        API gibt ihn nie aus und ein Formular schickt ihn leer zurueck.
        """
        ...

    def delete(self, profile_id: str) -> bool:
        """``True``, wenn etwas geloescht wurde."""
        ...

    def set_default(self, profile_id: str) -> Optional[LlmProfile]:
        """Macht ein Profil zum Default und nimmt das Flag allen anderen, oder
        ``None`` wenn es das Profil nicht gibt."""
        ...


def get_llm_profile_repository() -> LlmProfileRepository:
    """Die einzige Stelle, an der ein Consumer an ein Profil-Repository kommt.

    Der Import des Adapters steht bewusst in der Funktion: er zieht ``sqlite3``
    und das Schema nach sich, und ein Modul, das nur den Port braucht, soll das
    nicht mitladen.
    """
    backend = Config.LLM_PROFILE_BACKEND
    if backend in LLM_PROFILE_BACKENDS_NOT_YET_AVAILABLE:
        # Dieselbe Aussage wie in Config.validate(), für den Fall, dass jemand
        # das Repository ohne vorherige Validierung erreicht — ein Test, ein
        # Skript, ein künftiger Aufrufer.
        raise LlmProfileBackendUnavailable(
            f"AGORA_LLM_PROFILE_BACKEND={backend} has no adapter yet; "
            "it arrives with PR 4 (docs/plans/supabase.md §10)"
        )
    from ..services.llm_profiles_store import get_llm_profiles_store

    return get_llm_profiles_store()
