"""Port fuer Personasaetze (Issue #1807, Etappe 7).

Ein Personasatz ist eine benannte Sammlung synthetischer Personas, die in
mehreren Laeufen verwendet werden kann (siehe
``app/contracts/persona_set_contract.py``). Der Port beschreibt ausschliesslich
die **Ablage** der Saetze; Regeln wie "ein gesperrter Satz ist nicht
aenderbar" setzt der Service durch, nicht der Port.

Die Semantik ist die der bestehenden Metadaten-Ports und wird hier
festgeschrieben, damit ein zweiter Adapter sie nicht anders auslegt:

``get`` gibt ``None`` zurueck, wenn es den Satz nicht gibt — es wirft nicht.

``list`` liefert alle Saetze, neuester zuerst (``created_at`` absteigend, bei
Gleichstand ``id`` absteigend). Die Reihenfolge ist Teil der Zusage: die
Bibliothek zeigt das Neueste oben.

``save`` schreibt den Datensatz, setzt ``updated_at`` auf jetzt und legt einen
noch unbekannten Satz an — der Port hat keinen eigenen Anlegepfad. **Die
Sperre bleibt unberuehrt:** ``locked_at`` und ``used_by_simulation_ids`` eines
bestehenden Satzes aendert nur ``mark_used``. Ein ``save`` mit einem aelteren
Stand des Satzes kann eine inzwischen gesetzte Sperre also nicht aufheben; der
uebergebene Datensatz wird dafuer an den gespeicherten Stand angeglichen.

``mark_used`` ist **atomar** und **idempotent**: es ergaenzt
``used_by_simulation_ids`` um die Simulation und setzt ``locked_at`` beim
ersten Mal. Dieselbe Simulation ein zweites Mal aendert nichts (auch nicht
``updated_at``). Gibt es den Satz nicht, ist das Ergebnis ``None``.

``delete`` entfernt den Satz und sagt, ob es einen gab. Ob ein gesperrter Satz
geloescht werden darf, entscheidet der Service.

Die Fabrik ``get_persona_set_repository`` ist die einzige Stelle, an der ein
Consumer an ein Repository kommt. ``AGORA_PERSONA_SET_BACKEND`` waehlt
zwischen Dateiadapter (Default ``file``) und PostgreSQL-Adapter.
"""

from __future__ import annotations

import uuid
from typing import List, Optional, Protocol, runtime_checkable

from ..config import PERSONA_SET_BACKENDS, Config
from ..contracts.persona_set_contract import PersonaSetRecord

#: Praefixe und Laenge der serverseitig vergebenen Kennungen. Sie stehen hier
#: und nicht in einem Adapter, weil jeder Adapter und der Service dieselbe Form
#: erzeugen muessen; die Satzkennung ist beim Dateiadapter zugleich der
#: Dateiname.
PERSONA_SET_ID_PREFIX = 'pset_'
PERSONA_SET_ENTRY_ID_PREFIX = 'pent_'
PERSONA_SET_ID_HEX_LENGTH = 12


def new_persona_set_id() -> str:
    """Erzeugt eine Satzkennung der Form ``pset_<12 Hexstellen>``."""
    return f'{PERSONA_SET_ID_PREFIX}{uuid.uuid4().hex[:PERSONA_SET_ID_HEX_LENGTH]}'


def new_persona_set_entry_id() -> str:
    """Erzeugt eine Eintragskennung der Form ``pent_<12 Hexstellen>``."""
    return (
        f'{PERSONA_SET_ENTRY_ID_PREFIX}{uuid.uuid4().hex[:PERSONA_SET_ID_HEX_LENGTH]}'
    )


class PersonaSetBackendUnavailable(RuntimeError):
    """``AGORA_PERSONA_SET_BACKEND`` traegt einen Wert, den keine Ablage bedient.

    ``Config.validate()`` lehnt ihn beim Start ab; dieser Fehler faengt den
    Weg ohne Validierung ab (Test, Skript), statt still auf die Datei
    zurueckzufallen.
    """


@runtime_checkable
class PersonaSetRepository(Protocol):
    """Lesen und Schreiben von Personasaetzen, unabhaengig von der Ablage."""

    def save(self, record: PersonaSetRecord) -> None:
        """Schreibt den Datensatz und setzt ``updated_at`` auf jetzt.

        Legt einen unbekannten Satz an. Bei einem bestehenden Satz bleiben
        ``locked_at`` und ``used_by_simulation_ids`` wie gespeichert — siehe
        Modul-Docstring; ``record`` wird darauf angeglichen.
        """
        ...

    def get(self, set_id: str) -> Optional[PersonaSetRecord]:
        """Ein Satz oder ``None``, wenn es ihn nicht gibt."""
        ...

    def list(self) -> List[PersonaSetRecord]:
        """Alle Saetze, neuester zuerst (``created_at``, dann ``id``, absteigend)."""
        ...

    def delete(self, set_id: str) -> bool:
        """Entfernt den Satz. ``True``, wenn es einen gab."""
        ...

    def mark_used(
        self, set_id: str, simulation_id: str
    ) -> Optional[PersonaSetRecord]:
        """Vermerkt, dass ``simulation_id`` aus dem Satz entstanden ist.

        Atomar und idempotent. Setzt ``locked_at`` beim ersten Mal und haengt
        die Simulation an ``used_by_simulation_ids`` an, falls sie dort noch
        nicht steht. Gibt den gespeicherten Satz zurueck, ``None`` wenn es den
        Satz nicht gibt.
        """
        ...


def get_persona_set_repository(storage_root: Optional[str] = None) -> PersonaSetRepository:
    """Die einzige Stelle, an der ein Consumer an ein Personasatz-Repository kommt.

    Der Import des Adapters steht bewusst in der Funktion: ein Modul, das nur
    den Port braucht, soll die Ablage nicht mitladen.

    ``storage_root`` ist der Ort der dateibasierten Ablage (Vorgabe:
    ``<UPLOAD_FOLDER>/persona_sets``). Ein Adapter ohne Dateiablage ignoriert
    den Wert.
    """
    backend = Config.PERSONA_SET_BACKEND
    if backend not in PERSONA_SET_BACKENDS:
        # Ein Tippfehler darf nicht still auf den Dateiadapter zurueckfallen.
        raise PersonaSetBackendUnavailable(
            f"AGORA_PERSONA_SET_BACKEND has unknown value '{backend}' "
            f'(expected one of: {", ".join(sorted(PERSONA_SET_BACKENDS))})'
        )
    if backend == 'postgres':
        from ..infrastructure.postgres.repositories import PostgresPersonaSetRepository

        return PostgresPersonaSetRepository()

    from ..services.file_persona_set_store import get_file_persona_set_repository

    return get_file_persona_set_repository(storage_root)
