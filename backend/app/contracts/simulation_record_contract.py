"""Vertrag fuer Simulationsmetadaten (Issue #1578).

Dieser Vertrag beschreibt ausschliesslich die Metadaten einer Simulation —
den Inhalt von ``state.json``. Die Laufzeit-Artefakte daneben
(``simulation_config.json``, ``reddit_profiles.json``, ``run_state.json``,
Logs, IPC-Nachrichten) sind keine Metadaten und tauchen hier bewusst nicht
auf: sie wandern in keiner Phase dieses Plans in eine Datenbank, und ein
Vertrag, der sie mitfuehrte, muesste von jedem Adapter beantwortet werden,
der sie gar nicht hat.

Der Vertrag liest und schreibt die heutige Ablage verlustfrei. Alle Felder,
die ``SimulationState.to_dict()`` heute ausgibt, sind hier als Felder mit
demselben Schluessel vertreten. ``from_dict``/``to_dict`` halten das Format
von ``state.json`` unveraendert, damit eine bestehende Installation nach
diesem Umbau dieselbe Datei liest und schreibt wie davor.

``extra="ignore"`` ist hier aus denselben Gruenden wie in
``project_contract.py`` gewaehlt: ``state.json``-Dateien aus frueheren
Programmstaenden koennen Felder tragen, die spaeter entfernt wurden. Ein
``forbid`` wuerde aus jedem solchen Altbestand einen Ladefehler machen.

Der Vertrag ist ein interner Persistenzvertrag, kein API-Vertrag. Er wird
nicht in ``dump_schemas`` aufgenommen und hat kein ``schemas/``-Gegenstueck.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SimulationRecord(BaseModel):
    """Metadaten einer Simulation.

    ``created_at`` und ``updated_at`` sind ISO-8601-Zeichenketten, keine
    ``datetime``-Objekte: so stehen sie in der Ablage, und die Sortierung in
    ``list`` laeuft lexikografisch darueber. Eine Umstellung auf ``datetime``
    gehoert zur PostgreSQL-Tabelle, nicht hierher.
    """

    model_config = ConfigDict(extra='ignore', use_enum_values=False)

    simulation_id: str = Field(..., min_length=1)
    project_id: str = ''
    graph_id: str = ''

    # Plattform-Aktivierung
    enable_twitter: bool = True
    enable_reddit: bool = True

    # Simulationsstatus (als Zeichenkette — kein Import von SimulationStatus
    # hier, damit dieser Vertrag keine Laufzeit-Abhaengigkeit traegt)
    status: str = 'created'

    # Zustand der Vorbereitung
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: list[str] = Field(default_factory=list)

    # Konfigurationserzeugung
    config_generated: bool = False
    config_reasoning: str = ''

    # Laufzeit-Zaehler
    current_round: int = 0
    twitter_status: str = 'not_started'
    reddit_status: str = 'not_started'

    # Zeitstempel
    # Fehlt der Zeitstempel im Altbestand, gilt wie im frueheren Ladepfad
    # "jetzt" — nicht die leere Zeichenkette.
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Fehlermeldung
    error: Optional[str] = None

    # Szenario-Verzweigung
    source_simulation_id: Optional[str] = None
    root_simulation_id: Optional[str] = None
    branch_name: Optional[str] = None
    branch_depth: int = 0

    # Effektiver Persona-Floor der Preparation.
    # ``None`` = Legacy-State ohne Wert.
    persona_floor: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert fuer ``state.json``.

        Ausdruecklich handgeschrieben statt ``model_dump()``: Schluessel und
        Reihenfolge entsprechen ``SimulationState.to_dict()``, damit eine
        bestehende Ablage nach dem Umbau identisch aussieht.
        """
        return {
            'simulation_id': self.simulation_id,
            'project_id': self.project_id,
            'graph_id': self.graph_id,
            'enable_twitter': self.enable_twitter,
            'enable_reddit': self.enable_reddit,
            'status': self.status,
            'entities_count': self.entities_count,
            'profiles_count': self.profiles_count,
            'entity_types': self.entity_types,
            'config_generated': self.config_generated,
            'config_reasoning': self.config_reasoning,
            'current_round': self.current_round,
            'twitter_status': self.twitter_status,
            'reddit_status': self.reddit_status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'error': self.error,
            'source_simulation_id': self.source_simulation_id,
            'root_simulation_id': self.root_simulation_id,
            'branch_name': self.branch_name,
            'branch_depth': self.branch_depth,
            'persona_floor': self.persona_floor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'SimulationRecord':
        """Liest einen Datensatz aus der Ablage.

        ``simulation_id`` ist Pflicht und wirft bei Abwesenheit — ein
        Datensatz ohne Kennung ist keiner. Alle uebrigen Felder fallen auf
        ihre Vorgabewerte zurueck, unbekannte Schluessel werden verworfen.
        """
        _ = data['simulation_id']
        # Der fruehere Ladepfad war nachsichtig: ``null`` in einem Feld mit
        # Vorgabewert (``branch_depth``, ``entity_types`` …) fiel auf den
        # Vorgabewert zurueck, statt den Datensatz unlesbar zu machen.
        # Dieselbe Nachsicht hier, sonst wird ein Altbestand zum Ladefehler.
        cleaned = {
            key: value
            for key, value in data.items()
            if value is not None or key in _NULLABLE_FIELDS
        }
        return cls.model_validate(cleaned)


#: Felder, fuer die ``None`` ein gueltiger, gespeicherter Wert ist.
_NULLABLE_FIELDS = frozenset({
    'error',
    'source_simulation_id',
    'root_simulation_id',
    'branch_name',
    'persona_floor',
})
